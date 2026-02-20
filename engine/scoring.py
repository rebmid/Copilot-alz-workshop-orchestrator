# engine/scoring.py
"""Deterministic scoring — all status accounting imported from taxonomy.

Every control status is explicitly categorized in schemas/taxonomy.py.
This module NEVER defines its own status sets.  If a status is missing
from the taxonomy enum, the system refuses to start (compile-time assert).
"""
from __future__ import annotations
from collections import defaultdict
from typing import Any, Dict, List, Optional

from schemas.taxonomy import (
    DOMAIN_WEIGHTS,
    ALL_CONTROL_STATUSES,
    MATURITY_STATUSES,
    AUTO_STATUSES,
    NON_MATURITY_STATUSES,
    SIGNAL_ERROR_STATUSES,
    ERROR_STATUSES,
    MANUAL_STATUSES,
    NA_STATUSES,
)

# ── Status multiplier for gap scoring ─────────────────────────────
# Every canonical status MUST have an entry.  No implicit zeros.
STATUS_MULTIPLIER: dict[str, float] = {
    "Pass":             0,      # no risk
    "Fail":             1.0,    # full risk weight
    "Partial":          0.6,    # partial risk weight
    "Manual":           0,      # excluded — no automation evidence
    "NotApplicable":    0,      # excluded — does not apply
    "NotVerified":      0,      # excluded — could not verify
    "SignalError":      0,      # excluded — signal infra failure
    "EvaluationError":  0,      # excluded — evaluator crash
}

# Compile-time: every canonical status has a multiplier
assert set(STATUS_MULTIPLIER.keys()) == set(ALL_CONTROL_STATUSES), \
    f"STATUS_MULTIPLIER missing: {set(ALL_CONTROL_STATUSES) - set(STATUS_MULTIPLIER.keys())}"

SEVERITY_WEIGHTS = {
    "Critical": 6,
    "High": 5,
    "Medium": 3,
    "Low": 1,
    "Info": 0,
    None: 0
}

# Confidence scale: numeric 0-1 discount factor
# Higher confidence = more weight in scoring
CONFIDENCE_FLOOR = 0.3  # minimum weight even for low-confidence results

def automation_coverage(results: List[Dict[str, Any]], total_controls: int) -> Dict[str, Any]:
    automated = sum(1 for r in results if r.get("status") in AUTO_STATUSES)
    manual = sum(1 for r in results if r.get("status") in MANUAL_STATUSES)
    not_applicable = sum(1 for r in results if r.get("status") in NA_STATUSES)
    signal_errors = sum(1 for r in results if r.get("status") in SIGNAL_ERROR_STATUSES)
    eval_errors = sum(1 for r in results if r.get("status") == "EvaluationError")
    not_verified = sum(1 for r in results if r.get("status") == "NotVerified")
    pct = round((automated / total_controls) * 100.0, 1) if total_controls else 0.0

    # automation_integrity: what fraction of attempted automated controls
    # actually executed cleanly (no signal or eval failures).
    # "attempted" = controls that tried to run automation (succeeded + failed infra)
    attempted = automated + signal_errors + eval_errors
    automation_integrity = round(1.0 - ((signal_errors + eval_errors) / attempted), 4) if attempted else 1.0

    return {
        "total_controls": total_controls,
        "automated_controls": automated,
        "manual_controls": manual,
        "not_applicable_controls": not_applicable,
        "not_verified_controls": not_verified,
        "signal_error_controls": signal_errors,
        "evaluation_error_controls": eval_errors,
        "automation_percent": pct,
        "automation_integrity": automation_integrity,
        # Assessment coverage: conversation-guide framing
        "data_driven": automated,
        "requires_customer_input": manual,
    }

def section_scores(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Compute tenant-wide maturity per ALZ design area.

    Groups controls by design area (section) and calculates a single
    maturity percentage for each.  This is tenant-wide — it is NOT
    per-subscription maturity.  Subscriptions are inputs; design areas
    are the evaluation dimension.

    Each section dict now includes:
      - automation_percent: % of total controls that are automated
      - critical_fail_count: # of controls with severity Critical/High
        AND status Fail
      - critical_partial_count: same for Partial
    """
    # Group by section — taxonomy-validated, section is always present
    by_section = defaultdict(list)
    for r in results:
        by_section[r["section"]].append(r)

    out = []
    for section, items in by_section.items():
        counts = defaultdict(int)
        for r in items:
            counts[r.get("status", "EvaluationError")] += 1

        # Maturity: only MATURITY_STATUSES (Pass, Fail, Partial)
        # Everything else is explicitly excluded — no implicit omission
        maturity_items = [r for r in items
                          if r.get("status") in MATURITY_STATUSES]
        auto_total = len(maturity_items)
        auto_pass = sum(1 for r in maturity_items if r.get("status") == "Pass")
        auto_fail = sum(1 for r in maturity_items if r.get("status") in ("Fail", "Partial"))

        # Confidence-weighted maturity
        maturity = None
        if auto_total > 0:
            total_weight = 0.0
            pass_weight = 0.0
            for r in maturity_items:
                conf = _effective_confidence(r)
                total_weight += conf
                if r.get("status") == "Pass":
                    pass_weight += conf
            maturity = round((pass_weight / total_weight) * 100.0, 1) if total_weight else 0.0

        # Coverage-based summary (from coverage evaluators)
        coverage_items = [r for r in items if r.get("coverage_ratio") is not None]
        avg_coverage = None
        if coverage_items:
            avg_coverage = round(
                sum(r["coverage_ratio"] for r in coverage_items) / len(coverage_items) * 100, 1
            )

        # ── Automation coverage % per section ─────────────────────
        total_ctrl = len(items)
        automation_pct = round((auto_total / total_ctrl) * 100) if total_ctrl else 0

        # ── Critical fail / partial counts (High + Critical severity) ─
        _high_sev = {"High", "Critical"}
        critical_fail = sum(
            1 for r in items
            if r.get("severity") in _high_sev and r.get("status") == "Fail"
        )
        critical_partial = sum(
            1 for r in items
            if r.get("severity") in _high_sev and r.get("status") == "Partial"
        )

        out.append({
            "section": section,
            "counts": dict(counts),
            "automated_controls": auto_total,
            "automated_pass": auto_pass,
            "automated_fail": auto_fail,
            "total_controls": total_ctrl,
            "maturity_percent": maturity,
            "avg_coverage_percent": avg_coverage,
            "automation_percent": automation_pct,
            "critical_fail_count": critical_fail,
            "critical_partial_count": critical_partial,
        })

    # sort: lowest maturity first, None at end
    out.sort(key=lambda x: (x["maturity_percent"] is None, x["maturity_percent"] if x["maturity_percent"] is not None else 9999))
    return out


def _effective_confidence(r: Dict[str, Any]) -> float:
    """Extract numeric confidence from a result dict, with floor."""
    cs = r.get("confidence_score")
    if cs is not None and isinstance(cs, (int, float)):
        return max(cs, CONFIDENCE_FLOOR)
    # Fall back to label mapping
    from signals.types import CONFIDENCE_LABEL
    label = r.get("confidence", "High")
    return max(CONFIDENCE_LABEL.get(label, 0.7), CONFIDENCE_FLOOR)

def overall_maturity(sections: List[Dict[str, Any]]) -> float:
    """Tenant-wide overall maturity across all design areas.

    Weighted by automated control count per section.  This is a single
    tenant-scoped metric — never computed per-subscription.
    """
    # Weighted by automated_controls
    total_auto = sum(s["automated_controls"] for s in sections)
    if total_auto == 0:
        return 0.0
    total_pass = sum(s["automated_pass"] for s in sections)
    return round((total_pass / total_auto) * 100.0, 1)

def top_failing_sections(sections: List[Dict[str, Any]], top_n: int = 5) -> List[Dict[str, Any]]:
    # Rank by automated_fail then maturity
    ranked = sorted(sections, key=lambda s: (s["automated_fail"], -(s["maturity_percent"] or 0)), reverse=True)
    return ranked[:top_n]

def most_impactful_gaps(results: List[Dict[str, Any]], top_n: int = 10) -> List[Dict[str, Any]]:
    gaps = []
    for r in results:
        status = r.get("status")
        if status not in ("Fail", "Partial"):
            continue

        severity = r.get("severity")
        evidence_count = r.get("evidence_count", 0) or 0

        severity_weight = SEVERITY_WEIGHTS.get(severity, 2)
        domain_weight = DOMAIN_WEIGHTS.get(r["section"], 1.0)
        status_multiplier = STATUS_MULTIPLIER.get(status, 0)
        evidence_factor = 1 + min(evidence_count, 50) / 20
        confidence = _effective_confidence(r)

        risk_score = severity_weight * domain_weight * status_multiplier * evidence_factor * confidence

        gaps.append({
            "control_id": r.get("control_id"),
            "section": r.get("section"),
            "question": r.get("question"),
            "status": status,
            "severity": severity,
            "evidence_count": evidence_count,
            "confidence_score": round(confidence, 2),
            "coverage_ratio": r.get("coverage_ratio"),
            "risk_score": round(risk_score, 2),
            "notes": r.get("notes")
        })

    gaps.sort(key=lambda g: g["risk_score"], reverse=True)
    return gaps[:top_n]

def compute_scoring(results: list[dict]) -> dict:
    """Compute tenant-wide scoring: maturity, section scores, gaps, coverage.

    Accepts either:
      - a list of result dicts (backwards compatible)
      - a run dict with 'results' and 'meta' keys

    All metrics are tenant-scoped.  Maturity is computed ONLY from
    automated controls (MATURITY_STATUSES).  There is no per-subscription
    scoring — subscriptions are inputs, not evaluation units.
    """
    # Support both call patterns
    if isinstance(results, dict):
        run = results
        result_list = run.get("results", []) or []
        total_controls = (run.get("meta", {}) or {}).get("total_controls", len(result_list))
    else:
        result_list = results
        total_controls = len(result_list)

    cov = automation_coverage(result_list, total_controls)
    sections = section_scores(result_list)
    overall = overall_maturity(sections)

    return {
        "automation_coverage": cov,
        "overall_maturity_percent": overall,
        "section_scores": sections,
        "top_failing_sections": top_failing_sections(sections),
        "most_impactful_gaps": most_impactful_gaps(result_list)
    }
