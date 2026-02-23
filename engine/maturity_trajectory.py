"""Maturity Trajectory — deterministic maturity projections per phase.

Replaces LLM-generated trajectory with math:
  current = overall_maturity_percent (from scoring)
  post_N_day = current + (controls resolved in phases up to N / total assessed) × 100

Separate track for critical controls.
"""
from __future__ import annotations

from typing import Any


def compute_maturity_trajectory(
    initiatives: list[dict],
    results: list[dict],
    phase_assignment: dict[str, str],
    current_maturity_percent: float,
) -> dict[str, Any]:
    """
    Compute deterministic maturity trajectory from control resolution counts.

    Parameters
    ----------
    initiatives : list[dict]
        Initiative list with controls[].
    results : list[dict]
        Assessment control results.
    phase_assignment : dict[str, str]
        initiative_id → "30_days" | "60_days" | "90_days" from dependency engine.
    current_maturity_percent : float
        Current overall maturity (from scoring.py).

    Returns
    -------
    dict with current_percent, post_30_day_percent, post_60_day_percent,
    post_90_day_percent, critical_track, and assumptions.
    """
    results_by_id = {r.get("control_id", ""): r for r in results if r.get("control_id")}

    # Count total assessed controls (Pass + Fail + Partial)
    assessed = [
        r for r in results
        if r.get("status") in ("Pass", "Fail", "Partial")
    ]
    total_assessed = len(assessed)
    total_pass = sum(1 for r in assessed if r.get("status") == "Pass")

    # Count critical (High/Critical severity) assessed controls
    critical_assessed = [
        r for r in assessed
        if r.get("severity") in ("High", "Critical")
    ]
    total_critical = len(critical_assessed)
    critical_pass = sum(1 for r in critical_assessed if r.get("status") == "Pass")

    # Collect controls resolved per phase
    phase_controls: dict[str, set[str]] = {
        "30_days": set(),
        "60_days": set(),
        "90_days": set(),
    }

    for init in initiatives:
        iid = init.get("initiative_id", "")
        phase = phase_assignment.get(iid, "90_days")
        for ctrl_id in init.get("controls", []):
            ctrl = results_by_id.get(ctrl_id, {})
            if ctrl.get("status") in ("Fail", "Partial"):
                phase_controls[phase].add(ctrl_id)

    # Cumulative resolution counts
    resolved_by_30 = len(phase_controls["30_days"])
    resolved_by_60 = resolved_by_30 + len(phase_controls["60_days"])
    resolved_by_90 = resolved_by_60 + len(phase_controls["90_days"])

    # Compute projected maturity at each checkpoint
    if total_assessed > 0:
        post_30 = round(((total_pass + resolved_by_30) / total_assessed) * 100, 1)
        post_60 = round(((total_pass + resolved_by_60) / total_assessed) * 100, 1)
        post_90 = round(((total_pass + resolved_by_90) / total_assessed) * 100, 1)
    else:
        post_30 = post_60 = post_90 = current_maturity_percent

    # Critical controls track
    critical_resolved_by_phase: dict[str, int] = {"30_days": 0, "60_days": 0, "90_days": 0}
    for phase, ctrl_ids in phase_controls.items():
        for ctrl_id in ctrl_ids:
            ctrl = results_by_id.get(ctrl_id, {})
            if ctrl.get("severity") in ("High", "Critical"):
                critical_resolved_by_phase[phase] += 1

    crit_by_30 = critical_resolved_by_phase["30_days"]
    crit_by_60 = crit_by_30 + critical_resolved_by_phase["60_days"]
    crit_by_90 = crit_by_60 + critical_resolved_by_phase["90_days"]

    if total_critical > 0:
        crit_current = round((critical_pass / total_critical) * 100, 1)
        crit_post_30 = round(((critical_pass + crit_by_30) / total_critical) * 100, 1)
        crit_post_60 = round(((critical_pass + crit_by_60) / total_critical) * 100, 1)
        crit_post_90 = round(((critical_pass + crit_by_90) / total_critical) * 100, 1)
    else:
        crit_current = crit_post_30 = crit_post_60 = crit_post_90 = 100.0

    # Build assumptions from actual data
    assumptions = []
    if resolved_by_30 > 0:
        assumptions.append(
            f"{resolved_by_30} failing control(s) resolved in 30-day phase"
        )
    if len(phase_controls["60_days"]) > 0:
        assumptions.append(
            f"{len(phase_controls['60_days'])} additional control(s) resolved in 60-day phase"
        )
    if len(phase_controls["90_days"]) > 0:
        assumptions.append(
            f"{len(phase_controls['90_days'])} additional control(s) resolved in 90-day phase"
        )
    assumptions.append(
        f"Based on {total_assessed} assessed controls ({total_pass} currently passing)"
    )
    assumptions.append("Assumes all initiative controls resolve to Pass upon implementation")

    return {
        "current_percent": round(current_maturity_percent, 1),
        "post_30_day_percent": post_30,
        "post_60_day_percent": post_60,
        "post_90_day_percent": post_90,
        "controls_resolved_by_phase": {
            "30_days": resolved_by_30,
            "60_days": len(phase_controls["60_days"]),
            "90_days": len(phase_controls["90_days"]),
            "cumulative_90": resolved_by_90,
        },
        "critical_track": {
            "current_percent": crit_current,
            "post_30_day_percent": crit_post_30,
            "post_60_day_percent": crit_post_60,
            "post_90_day_percent": crit_post_90,
            "total_critical_controls": total_critical,
        },
        "assumptions": assumptions,
    }
