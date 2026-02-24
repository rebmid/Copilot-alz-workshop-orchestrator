"""Risk Impact Layer — per-item risk/impact scoring for executive framing.

Layer 2 of the 3-layer deterministic decision engine.

This module computes risk reduction, blast radius, and control resolution
metrics per remediation item.  These metrics are for NARRATIVE and EXECUTIVE
FRAMING only — they MUST NOT influence sequencing.  Sequencing is owned
exclusively by the dependency engine (Layer 1).

Outputs:
  - critical_risks_reduced: count of top business risks whose affected
    controls overlap with the item's controls
  - fail_controls_resolved: count of Fail/Partial controls in the item
  - blast_radius_score: deterministic blast radius from control severity + count
  - maturity_lift: projected maturity improvement if item is implemented
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any


def build_risk_impact_model(
    items: list[dict],
    results: list[dict],
    top_risks: list[dict],
    section_scores: list[dict],
) -> dict[str, Any]:
    """
    Build the risk impact model: per-item risk/impact metrics.

    These metrics are for executive reporting ONLY.
    They MUST NOT be used to influence item ordering.

    Parameters
    ----------
    items : list[dict]
        Remediation items (each with checklist_id, controls, etc.).
    results : list[dict]
        Assessment control results.
    top_risks : list[dict]
        Top business risks from executive pass.
    section_scores : list[dict]
        Per-section maturity scores.

    Returns
    -------
    dict with:
      - items: list[dict]  — per-item impact metrics
      - summary: dict  — aggregate stats
    """
    results_by_id = {r.get("control_id", ""): r for r in results if r.get("control_id")}
    section_maturity = {
        s.get("section", ""): s.get("maturity_percent", 0) or 0
        for s in section_scores
    }
    total_fail_controls = sum(
        1 for r in results if r.get("status") in ("Fail", "Partial")
    )
    total_controls_assessed = sum(
        1 for r in results if r.get("status") in ("Pass", "Fail", "Partial")
    )

    items_out: list[dict] = []

    for item in items:
        cid = item.get("checklist_id", "")
        if not cid:
            continue

        item_controls = set(item.get("controls", []))

        # 1. Controls resolved (Fail + Partial in this item)
        fail_controls = []
        partial_controls = []
        for ctrl_id in item_controls:
            ctrl = results_by_id.get(ctrl_id, {})
            status = ctrl.get("status")
            if status == "Fail":
                fail_controls.append(ctrl_id)
            elif status == "Partial":
                partial_controls.append(ctrl_id)

        controls_resolved = len(fail_controls) + len(partial_controls)

        # 2. Risks reduced: count top_business_risks whose affected_controls
        #    overlap with this item's controls
        risks_reduced = 0
        risk_titles: list[str] = []
        for risk in top_risks:
            affected = set(risk.get("affected_controls", []))
            if affected & item_controls:
                risks_reduced += 1
                risk_titles.append(risk.get("title", "unnamed"))

        # 3. Blast radius score (deterministic)
        blast_score = _compute_blast_radius(item_controls, results_by_id)
        blast_label = _blast_label(blast_score)

        # 4. Maturity lift per affected section
        section_impact = _compute_section_impact(
            item_controls, results_by_id, section_maturity, total_controls_assessed
        )

        # 5. Aggregate maturity lift (weighted by controls in each section)
        total_lift = sum(s.get("maturity_lift_percent", 0) for s in section_impact)

        items_out.append({
            "checklist_id": cid,
            "title": item.get("title", item.get("checklist_title", "")),
            "controls_resolved": controls_resolved,
            "fail_controls": fail_controls,
            "partial_controls": partial_controls,
            "risks_reduced": risks_reduced,
            "risk_titles": risk_titles,
            "blast_radius_score": blast_score,
            "blast_radius_label": blast_label,
            "section_impact": section_impact,
            "total_maturity_lift_percent": round(total_lift, 1),
        })

    # Sort by impact (most impactful first) — but this is for display,
    # NOT for sequencing
    items_out.sort(key=lambda x: (
        -x["risks_reduced"],
        -x["controls_resolved"],
        -x["blast_radius_score"],
    ))

    return {
        "items": items_out,
        "summary": {
            "total_items": len(items_out),
            "total_controls_resolved": sum(i["controls_resolved"] for i in items_out),
            "total_risks_addressed": len(set(
                t for i in items_out for t in i["risk_titles"]
            )),
            "total_fail_controls": total_fail_controls,
        },
    }


# ── Internal helpers ──────────────────────────────────────────────

_SEVERITY_WEIGHT = {
    "Critical": 10,
    "High": 6,
    "Medium": 3,
    "Low": 1,
    "Info": 0,
}


def _compute_blast_radius(
    item_controls: set[str],
    results_by_id: dict[str, dict],
) -> float:
    """
    Compute blast radius score from control severity and count.

    Score = sum of severity weights for all Fail/Partial controls.
    """
    score = 0.0
    for ctrl_id in item_controls:
        ctrl = results_by_id.get(ctrl_id, {})
        status = ctrl.get("status")
        if status in ("Fail", "Partial"):
            sev = ctrl.get("severity", "Medium")
            weight = _SEVERITY_WEIGHT.get(sev, 3)
            multiplier = 1.0 if status == "Fail" else 0.6
            score += weight * multiplier
    return round(score, 1)


def _blast_label(score: float) -> str:
    """Convert blast radius score to High/Medium/Low label."""
    if score >= 15:
        return "High"
    if score >= 5:
        return "Medium"
    return "Low"


def _compute_section_impact(
    item_controls: set[str],
    results_by_id: dict[str, dict],
    section_maturity: dict[str, float | int],
    total_assessed: int,
) -> list[dict]:
    """
    Compute per-section maturity lift if this item is implemented.

    For each section touched by this item:
      - Count Fail controls that would become Pass
      - Compute new maturity = (current_pass + resolved) / total_in_section × 100
      - Lift = new_maturity - current_maturity
    """
    # Group item controls by section
    by_section: dict[str, list[str]] = defaultdict(list)
    for ctrl_id in item_controls:
        ctrl = results_by_id.get(ctrl_id, {})
        section = ctrl.get("section", "Unknown")
        if ctrl.get("status") in ("Fail", "Partial"):
            by_section[section].append(ctrl_id)

    impacts: list[dict] = []
    for section, ctrl_ids in sorted(by_section.items()):
        current_maturity = section_maturity.get(section, 0)
        resolved_count = len(ctrl_ids)

        # Approximate lift: each resolved control adds to the section pass count
        # This is an approximation — actual lift depends on total section controls
        # We estimate using the global ratio
        if total_assessed > 0:
            lift = (resolved_count / total_assessed) * 100
        else:
            lift = 0

        impacts.append({
            "section": section,
            "current_maturity_percent": current_maturity,
            "controls_resolved": resolved_count,
            "maturity_lift_percent": round(lift, 1),
        })

    return impacts
