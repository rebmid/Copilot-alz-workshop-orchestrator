"""Anti-Drift Guardrails — validators that enforce evidence grounding.

Every derived conclusion, simulation, or projection must carry an
``evidence_refs`` dict and an ``assumptions`` list.  These validators
run **after** all derived models are assembled and reject any object
that violates the anti-drift contract.

Layers enforced:
  1. Signals       (facts from collectors / MCP)
  2. Control eval  (results[].status + evidence)
  3. Scoring       (untouched deterministic formulas)
  4. Derived models(deterministic joins only)
  5. Simulations   (rule-based projection with explicit assumptions)
  6. Narrative text (generated from structured objects, never raw)
"""
from __future__ import annotations

import re
from typing import Any


# ── Evidence-ref schema helpers ───────────────────────────────────

def empty_evidence_refs() -> dict[str, list[str]]:
    """Return a blank evidence_refs scaffold."""
    return {
        "controls": [],
        "risks": [],
        "blockers": [],
        "signals": [],
        "mcp_queries": [],
    }


def merge_evidence_refs(*refs: dict) -> dict[str, list[str]]:
    """Merge multiple evidence_refs dicts, deduplicating values."""
    merged = empty_evidence_refs()
    for ref in refs:
        if not ref:
            continue
        for key in merged:
            for val in ref.get(key, []):
                if val and val not in merged[key]:
                    merged[key].append(val)
    return merged


def evidence_is_empty(refs: dict | None) -> bool:
    """True when every evidence_refs bucket is empty."""
    if not refs:
        return True
    return all(len(refs.get(k, [])) == 0 for k in ("controls", "risks", "blockers", "signals", "mcp_queries"))


def insufficient_evidence_marker() -> str:
    """Canonical string for objects that lack evidence."""
    return "Insufficient evidence (needs customer confirmation)"


# ── Confidence computation ────────────────────────────────────────

def compute_derived_confidence(
    control_confidences: list[float],
    signal_coverage_pct: float,
) -> dict:
    """
    Compute a confidence value + basis for a derived object.

    Parameters
    ----------
    control_confidences : list[float]
        The confidence_score (0-1) of each underlying control.
    signal_coverage_pct : float
        Percentage of relevant signals that were available (0-100).

    Returns
    -------
    dict with ``value`` (float 0-1), ``basis`` (str), ``label`` (str).
    """
    if not control_confidences:
        return {
            "value": 0.0,
            "basis": "No underlying controls",
            "label": "None",
        }

    avg_ctrl = sum(control_confidences) / len(control_confidences)
    signal_factor = signal_coverage_pct / 100.0
    combined = round(avg_ctrl * 0.7 + signal_factor * 0.3, 3)

    if combined >= 0.75:
        label = "High"
    elif combined >= 0.45:
        label = "Medium"
    else:
        label = "Low"

    return {
        "value": combined,
        "basis": (
            f"avg_control_confidence={avg_ctrl:.2f} ({len(control_confidences)} controls), "
            f"signal_coverage={signal_coverage_pct:.0f}%"
        ),
        "label": label,
    }


# ── Compliance language guardrail ─────────────────────────────────

_COMPLIANCE_PASS_FAIL_RE = re.compile(
    r"\b(fails?|passes?|violates?|compliant with|non-compliant with)"
    r"\s+(PCI[\s-]?DSS|HIPAA|SOC[\s-]?[12]|GDPR|FedRAMP|NIST|ISO[\s-]?27001|HITRUST)",
    re.IGNORECASE,
)


def check_no_compliance_claims(text: str) -> list[str]:
    """
    Return a list of violations if the text contains pass/fail compliance claims.

    Allowed: "commonly required in regulated environments."
    Banned:  "fails PCI-DSS", "passes HIPAA".
    """
    violations: list[str] = []
    for m in _COMPLIANCE_PASS_FAIL_RE.finditer(text):
        violations.append(
            f"Compliance pass/fail claim detected: '{m.group(0)}' — "
            "must use 'commonly required in regulated environments' language instead."
        )
    return violations


# ── Cost guardrail ────────────────────────────────────────────────

_COST_NUMBER_RE = re.compile(
    r"\$\s?\d[\d,]*\.?\d*\s*/?\s*(month|year|hour|day|GB|TB|unit)?",
    re.IGNORECASE,
)


def check_no_cost_numbers(text: str, cost_mode: str) -> list[str]:
    """
    If cost_mode != 'tool_backed', flag any dollar amounts in text.
    """
    violations: list[str] = []
    if cost_mode == "tool_backed":
        return violations
    for m in _COST_NUMBER_RE.finditer(text):
        violations.append(
            f"Cost number '{m.group(0)}' found but cost_simulation.mode='{cost_mode}' "
            "(not tool_backed). Use category labels only (Low/Medium/High)."
        )
    return violations


# ── Confidence label guardrail ────────────────────────────────────

_HIGH_CONFIDENCE_RE = re.compile(
    r"\bhigh\s+confidence\b",
    re.IGNORECASE,
)


def check_confidence_has_basis(text: str, confidence_obj: dict | None) -> list[str]:
    """
    Flag 'high confidence' language that lacks a computed basis.
    """
    violations: list[str] = []
    if _HIGH_CONFIDENCE_RE.search(text):
        if not confidence_obj or "value" not in confidence_obj:
            violations.append(
                "'High confidence' label found in narrative without a computed "
                "confidence object (value + basis). Must include computed confidence."
            )
    return violations


# ── Evidence-refs enforcement ─────────────────────────────────────

def validate_evidence_refs(item: dict, item_label: str) -> list[str]:
    """
    Validate that a derived item has non-empty evidence_refs and assumptions.
    """
    violations: list[str] = []
    refs = item.get("evidence_refs")
    if evidence_is_empty(refs):
        violations.append(
            f"{item_label}: evidence_refs is empty — must link to controls, "
            "signals, risks, or blockers."
        )
    if "assumptions" not in item:
        violations.append(
            f"{item_label}: missing 'assumptions' field — every derived object "
            "must declare its assumptions (use [] if none)."
        )
    return violations


# ── Doc-ref enforcement ───────────────────────────────────────────

def validate_doc_refs(section_name: str, doc_refs: list[dict]) -> list[str]:
    """
    Every design-area recommendation must have at least one doc_ref.
    """
    violations: list[str] = []
    if not doc_refs:
        violations.append(
            f"{section_name}: no doc_refs found — architectural recommendations "
            "require at least one Microsoft Learn reference."
        )
    else:
        for i, ref in enumerate(doc_refs):
            if not ref.get("url"):
                violations.append(f"{section_name} doc_ref[{i}]: missing 'url'.")
            if not ref.get("title"):
                violations.append(f"{section_name} doc_ref[{i}]: missing 'title'.")
    return violations


# ── Master validator ──────────────────────────────────────────────

def validate_anti_drift(output: dict) -> list[str]:
    """
    Run all anti-drift checks on the complete AI + derived output.

    Returns a list of violation strings.  Empty list = all checks pass.
    """
    violations: list[str] = []

    # 1. Decision impact model items
    dim = output.get("decision_impact_model", {})
    for item in dim.get("items", []):
        label = f"decision_impact_model[{item.get('initiative_id', '?')}]"
        violations.extend(validate_evidence_refs(item, label))

    # 2. Scaling simulation impacts
    ss = output.get("scaling_simulation", {})
    for scenario in ss.get("scenarios", []):
        for impact in scenario.get("derived_impacts", []):
            label = f"scaling_simulation[{scenario.get('scenario', '?')}].{impact.get('rule_id', '?')}"
            violations.extend(validate_evidence_refs(impact, label))

    # 3. Drift model
    dm = output.get("drift_model", {})
    if dm:
        violations.extend(validate_evidence_refs(dm, "drift_model"))

    # 4. Cost simulation drivers
    cs = output.get("cost_simulation", {})
    cost_mode = cs.get("mode", "category_only")
    for driver in cs.get("drivers", []):
        label = f"cost_simulation[{driver.get('initiative_id', '?')}]"
        violations.extend(validate_evidence_refs(driver, label))
        # Check for cost numbers in driver text fields
        for field in ("estimated_monthly_category",):
            text = str(driver.get(field, ""))
            violations.extend(check_no_cost_numbers(text, cost_mode))

    # 5. Compliance language across all text fields
    _walk_strings(output, violations, _check_compliance)

    # 6. Confidence labels without basis
    # (checked at object level where confidence is expected)

    return violations


def _walk_strings(obj: Any, violations: list[str], check_fn) -> None:
    """Recursively walk a dict/list and apply check_fn to every string."""
    if isinstance(obj, str):
        violations.extend(check_fn(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            _walk_strings(v, violations, check_fn)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _walk_strings(v, violations, check_fn)


def _check_compliance(text: str) -> list[str]:
    return check_no_compliance_claims(text)
