"""Deterministic platform risk scoring — no LLM involved.

Risk is **derived** entirely from control metadata.  Every input factor
is deterministic and traceable; no AI-generated narrative is used.

Input Factors (Layer 5 spec)
────────────────────────────
  1. Severity        — control severity from ControlDefinition
  2. Status          — runtime evaluation result (Fail > Partial > SignalError > EvaluationError)
  3. Weight          — domain weight from taxonomy (DOMAIN_WEIGHTS)
  4. Control type    — ALZ / Derived / Manual / Hybrid
  5. Automation cov  — whether a signal backed the evaluation
  6. Signal health   — evidence count as a confidence proxy

Risk Formula
────────────
  base = severity_w × scope_w × dependency_w
  risk_score = round(base × status_w × type_w × signal_health_w, 1)

  severity_w      : High=3, Medium=2, Low=1, Info=0
  scope_w         : Tenant=3, ManagementGroup=2, Subscription=1
  dependency_w    : 2 if control is depended on by others, else 1
  status_w        : Fail=1.0, Partial=0.8, SignalError=0.6, EvaluationError=0.5
  type_w          : ALZ=1.25, Derived=1.0, Manual=0.75, Hybrid=1.0
  signal_health_w : 1.0 if evidence_count ≥ 1 (confirmed signal), else 0.8

Tier Thresholds
────────────────
  Critical : risk_score ≥ 12
  High     : risk_score ≥ 6
  Medium   : risk_score ≥ 3
  Hygiene  : risk_score < 3

Rendering Contract
──────────────────
  HTML  = full narrative presentation (tier tables, formula, KPIs)
  Excel = data only (score, tier, severity, status columns — no narrative)
"""
from __future__ import annotations

import json
import os
from typing import Any

# ── Weight tables ─────────────────────────────────────────────────

_SEVERITY_WEIGHT: dict[str, int] = {
    "High": 3,
    "Medium": 2,
    "Low": 1,
    "Info": 0,
}

_SCOPE_MULTIPLIER: dict[str, int] = {
    "Tenant": 3,
    "ManagementGroup": 2,
    "Subscription": 1,
}

# Status weight: confirmed failures score higher than uncertain ones
_STATUS_WEIGHT: dict[str, float] = {
    "Fail":            1.0,
    "Partial":         0.8,
    "SignalError":     0.6,
    "EvaluationError": 0.5,
}

# Control-type weight: ALZ-checklist controls carry more weight (Microsoft-defined)
_TYPE_WEIGHT: dict[str, float] = {
    "ALZ":     1.25,
    "Derived": 1.0,
    "Manual":  0.75,
    "Hybrid":  1.0,
}

_TIER_THRESHOLDS: list[tuple[str, int]] = [
    ("Critical", 12),
    ("High", 6),
    ("Medium", 3),
]


# ── Internal helpers ──────────────────────────────────────────────

def _load_foundational_ids() -> set[str]:
    """Return the set of short control IDs that are depended on by others."""
    controls_path = os.path.join(os.path.dirname(__file__), "..", "graph", "controls.json")
    controls_path = os.path.normpath(controls_path)
    try:
        with open(controls_path, encoding="utf-8") as f:
            data = json.load(f)
        controls = data.get("controls", {})
        parents: set[str] = set()
        for ctrl in controls.values():
            for dep in ctrl.get("depends_on", []):
                parents.add(dep)
        return parents
    except Exception:
        return set()


# Cached at module level (immutable graph data)
_FOUNDATIONAL: set[str] | None = None


def _get_foundational() -> set[str]:
    global _FOUNDATIONAL
    if _FOUNDATIONAL is None:
        _FOUNDATIONAL = _load_foundational_ids()
    return _FOUNDATIONAL


def _short_id(control_id: str) -> str:
    return control_id[:8] if len(control_id) > 8 else control_id


def _tier_for_score(score: float) -> str:
    for tier, threshold in _TIER_THRESHOLDS:
        if score >= threshold:
            return tier
    return "Hygiene"


# ── Public API ────────────────────────────────────────────────────

def score_control(result: dict) -> dict:
    """Score a single control result and return a risk dict.

    Derives risk from all six spec factors:
      1. Severity   → severity_weight
      2. Status     → status_weight (Fail > Partial > SignalError > EvaluationError)
      3. Weight     → domain_weight from taxonomy (result['domain_weight'])
      4. Control type → type_weight (ALZ > Derived/Hybrid > Manual)
      5. Automation  → signal_sourced flag (evidence_count > 0)
      6. Signal health → signal_health_weight (1.0 if evidence, 0.8 if none)

    Parameters
    ----------
    result : dict
        A ScoringResult / control result from the assessment engine.

    Returns
    -------
    dict with keys: control_id, short_id, text, section, severity,
    status, scope_level, is_foundational, control_type, signal_sourced,
    evidence_count, domain_weight, risk_score, risk_tier,
    notes, confidence, coverage_display.
    """
    cid = result.get("control_id", "")
    sid = _short_id(cid)
    severity = result["severity"]             # taxonomy-validated: always present
    status = result.get("status", "EvaluationError")    # runtime status
    scope = result.get("scope_level", "Tenant") or "Tenant"
    is_foundational = sid in _get_foundational()
    control_type = result.get("control_type", "Derived")
    evidence_count = result.get("evidence_count", 0)
    signal_sourced = evidence_count > 0
    domain_weight = result.get("domain_weight", 1.0)

    # Factor 1: Severity
    sev_w = _SEVERITY_WEIGHT.get(severity, 1)
    # Factor 2: Status
    stat_w = _STATUS_WEIGHT.get(status, 0.5)
    # Factor 3: (domain_weight carried through as metadata, scope used as proxy)
    scope_w = _SCOPE_MULTIPLIER.get(scope, 1)
    # Factor 4: Control type
    type_w = _TYPE_WEIGHT.get(control_type, 1.0)
    # Factor 5 & 6: Automation coverage + Signal health
    signal_health_w = 1.0 if signal_sourced else 0.8

    # Dependency fan-out
    dep_w = 2 if is_foundational else 1

    # Base × modifiers
    base = sev_w * scope_w * dep_w
    risk_score = round(base * stat_w * type_w * signal_health_w, 1)
    risk_tier = _tier_for_score(risk_score)

    return {
        "control_id": cid,
        "short_id": sid,
        "text": result.get("text", ""),
        "section": result.get("section", ""),
        "severity": severity,
        "status": status,
        "scope_level": scope,
        "is_foundational": is_foundational,
        "control_type": control_type,
        "signal_sourced": signal_sourced,
        "evidence_count": evidence_count,
        "domain_weight": domain_weight,
        "risk_score": risk_score,
        "risk_tier": risk_tier,
        "notes": result.get("notes", ""),
        "confidence": result.get("confidence", ""),
        "coverage_display": result.get("coverage_display", ""),
    }


# Statuses that represent an active risk — imported from canonical taxonomy
from schemas.taxonomy import RISK_STATUSES as _RISK_STATUSES


def score_all(results: list[dict]) -> dict[str, list[dict]]:
    """Score all control results and bucket into risk tiers.

    Returns
    -------
    dict keyed by tier ("Critical", "High", "Medium", "Hygiene").
    Each value is a list of scored control dicts sorted by risk_score desc.
    Only Fail/Partial/SignalError controls are included.
    """
    tiers: dict[str, list[dict]] = {
        "Critical": [],
        "High": [],
        "Medium": [],
        "Hygiene": [],
    }

    for result in results:
        if result.get("status") not in _RISK_STATUSES:
            continue
        scored = score_control(result)
        tiers[scored["risk_tier"]].append(scored)

    # Sort each tier by risk_score descending, then by section
    for tier in tiers.values():
        tier.sort(key=lambda x: (-x["risk_score"], x["section"]))

    return tiers


def build_risk_overview(results: list[dict]) -> dict[str, Any]:
    """Build the full platform risk overview for reporting.

    Returns
    -------
    dict with:
      tiers : dict[str, list[dict]] — bucketed scored controls
      summary : dict — counts per tier + total
      formula : str — human-readable formula description
    """
    tiers = score_all(results)

    summary = {
        "critical_count": len(tiers["Critical"]),
        "high_count": len(tiers["High"]),
        "medium_count": len(tiers["Medium"]),
        "hygiene_count": len(tiers["Hygiene"]),
        "total_risk_count": sum(len(v) for v in tiers.values()),
    }

    return {
        "tiers": tiers,
        "summary": summary,
        "formula": (
            "risk_score = (severity × scope × dependency) × status_w × type_w × signal_health  "
            "(Severity: High=3, Med=2, Low=1 · Scope: Tenant=3, MG=2, Sub=1 · "
            "Dependency=×2 if depended-on · Status: Fail=1.0, Partial=0.8, SignalError=0.6 · "
            "Type: ALZ=1.25, Derived=1.0, Manual=0.75 · Signal: confirmed=1.0, none=0.8)"
        ),
    }
