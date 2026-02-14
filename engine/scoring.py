# engine/scoring.py
from __future__ import annotations
from collections import defaultdict
from typing import Any, Dict, List, Optional

DOMAIN_WEIGHTS = {
    "Security": 1.5,
    "Networking": 1.4,
    "Governance": 1.3,
    "Identity": 1.4,
    "Platform": 1.2,
    "Management": 1.1
}

STATUS_MULTIPLIER = {
    "Fail": 1.0,
    "Partial": 0.6,
    "Pass": 0,
    "Manual": 0
}

SEVERITY_WEIGHTS = {
    "Critical": 6,
    "High": 5,
    "Medium": 3,
    "Low": 1,
    "Info": 0,
    None: 0
}

PASS_STATUSES = {"Pass"}
FAIL_STATUSES = {"Fail"}
AUTO_STATUSES = {"Pass", "Fail", "Partial", "Info"}  # anything not Manual is "automated evidence"
MANUAL_STATUSES = {"Manual"}

def automation_coverage(results: List[Dict[str, Any]], total_controls: int) -> Dict[str, Any]:
    automated = sum(1 for r in results if (r.get("status") in AUTO_STATUSES))
    manual = sum(1 for r in results if (r.get("status") in MANUAL_STATUSES))
    pct = round((automated / total_controls) * 100.0, 1) if total_controls else 0.0
    return {
        "total_controls": total_controls,
        "automated_controls": automated,
        "manual_controls": manual,
        "automation_percent": pct,
        # Assessment coverage: conversation-guide framing
        "data_driven": automated,
        "requires_customer_input": manual,
    }

def section_scores(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # Group by section
    by_section = defaultdict(list)
    for r in results:
        by_section[r.get("section") or r.get("category") or "Unknown"].append(r)

    out = []
    for section, items in by_section.items():
        counts = defaultdict(int)
        for r in items:
            counts[r.get("status") or "Unknown"] += 1

        automated_items = [r for r in items if r.get("status") in AUTO_STATUSES]
        auto_total = len(automated_items)
        auto_pass = sum(1 for r in automated_items if r.get("status") == "Pass")
        auto_fail = sum(1 for r in automated_items if r.get("status") == "Fail")

        # Maturity is ONLY based on automated evidence
        maturity = None
        if auto_total > 0:
            maturity = round((auto_pass / auto_total) * 100.0, 1)

        out.append({
            "section": section,
            "counts": dict(counts),
            "automated_controls": auto_total,
            "automated_pass": auto_pass,
            "automated_fail": auto_fail,
            "total_controls": len(items),
            "maturity_percent": maturity
        })

    # sort: lowest maturity first, None at end
    out.sort(key=lambda x: (x["maturity_percent"] is None, x["maturity_percent"] if x["maturity_percent"] is not None else 9999))
    return out

def overall_maturity(sections: List[Dict[str, Any]]) -> float:
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
        domain_weight = DOMAIN_WEIGHTS.get(r.get("section", "Unknown"), 1.0)
        status_multiplier = STATUS_MULTIPLIER.get(status, 0)
        evidence_factor = 1 + min(evidence_count, 50) / 20

        risk_score = severity_weight * domain_weight * status_multiplier * evidence_factor

        gaps.append({
            "control_id": r.get("control_id"),
            "section": r.get("section"),
            "question": r.get("question"),
            "status": status,
            "severity": severity,
            "evidence_count": evidence_count,
            "risk_score": round(risk_score, 2),
            "notes": r.get("notes")
        })

    gaps.sort(key=lambda g: g["risk_score"], reverse=True)
    return gaps[:top_n]

def compute_scoring(results: list[dict]) -> dict:
    """
    Accepts either:
      - a list of result dicts (backwards compatible)
      - a run dict with 'results' and 'meta' keys
    Computes maturity ONLY from automated controls (excludes Manual).
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
