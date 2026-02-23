"""Drift Model — deterministic drift likelihood from signal gaps and activity log.

Two modes:
  - "static"             : derive drift likelihood from signal coverage gaps only
  - "activity_log_backed": enhance with activity log correlation (when signal available)

Layer: Derived models (deterministic joins only).
"""
from __future__ import annotations

from engine.guardrails import empty_evidence_refs, compute_derived_confidence


# ── Drift factor weights ──────────────────────────────────────────
# Each factor contributes to drift likelihood.  All are boolean conditions
# derived from signal/control data.

DRIFT_FACTORS: dict[str, dict] = {
    "no_policy_enforcement": {
        "weight": 0.25,
        "description": "No policy enforcement at MG/root scope — configuration drift unchecked",
        "signal_key": "assignments",
    },
    "no_change_tracking": {
        "weight": 0.20,
        "description": "No change tracking / analysis enabled — drift invisible",
        "signal_key": "change_tracking",
    },
    "no_activity_log_routing": {
        "weight": 0.15,
        "description": "Activity logs not routed to central workspace — operations unaudited",
        "signal_key": "diag_coverage_sample",
    },
    "no_resource_locks": {
        "weight": 0.10,
        "description": "No resource locks on critical infrastructure — accidental changes possible",
        "signal_key": "resource_locks",
    },
    "no_defender_monitoring": {
        "weight": 0.15,
        "description": "Defender for Cloud disabled — security drift undetected",
        "signal_key": "pricings",
    },
    "high_manual_control_ratio": {
        "weight": 0.15,
        "description": "High ratio of Manual controls — posture cannot be verified automatically",
        "signal_key": None,  # derived from results
    },
}


def _evaluate_factors(
    results: list[dict],
    signals: dict,
) -> list[dict]:
    """
    Evaluate each drift factor and return scored results.
    """
    evaluated = []

    # Policy enforcement
    policy_signal = signals.get("assignments")
    policy_present = bool(
        policy_signal
        and policy_signal.get("data")
        and (
            isinstance(policy_signal["data"], list)
            and len(policy_signal["data"]) > 0
        )
    )
    evaluated.append({
        "factor": "no_policy_enforcement",
        "active": not policy_present,
        **DRIFT_FACTORS["no_policy_enforcement"],
    })

    # Change tracking
    ct_signal = signals.get("change_tracking")
    ct_present = bool(ct_signal and ct_signal.get("data"))
    evaluated.append({
        "factor": "no_change_tracking",
        "active": not ct_present,
        **DRIFT_FACTORS["no_change_tracking"],
    })

    # Activity log routing
    diag_signal = signals.get("diag_coverage_sample")
    diag_ok = False
    if diag_signal and diag_signal.get("data"):
        coverage = diag_signal["data"].get("coverage_pct", 0)
        diag_ok = coverage >= 50
    evaluated.append({
        "factor": "no_activity_log_routing",
        "active": not diag_ok,
        **DRIFT_FACTORS["no_activity_log_routing"],
    })

    # Resource locks
    lock_signal = signals.get("resource_locks")
    locks_present = False
    if lock_signal and lock_signal.get("data"):
        data = lock_signal["data"]
        locks_present = (data.get("lock_count", 0) if isinstance(data, dict) else 0) > 0
    evaluated.append({
        "factor": "no_resource_locks",
        "active": not locks_present,
        **DRIFT_FACTORS["no_resource_locks"],
    })

    # Defender monitoring
    pricing_signal = signals.get("pricings")
    defender_on = False
    if pricing_signal and pricing_signal.get("data"):
        data = pricing_signal["data"]
        plans = data if isinstance(data, list) else data.get("plans", [])
        defender_on = any(
            p.get("pricingTier", "").lower() == "standard"
            and p.get("name", "").lower() != "ddosprotection"
            for p in (plans or [])
        )
    evaluated.append({
        "factor": "no_defender_monitoring",
        "active": not defender_on,
        **DRIFT_FACTORS["no_defender_monitoring"],
    })

    # Manual control ratio
    total = len(results)
    manual = sum(1 for r in results if r.get("status") == "Manual")
    manual_ratio = manual / max(total, 1)
    evaluated.append({
        "factor": "high_manual_control_ratio",
        "active": manual_ratio > 0.6,
        **DRIFT_FACTORS["high_manual_control_ratio"],
    })

    return evaluated


def build_drift_model(
    results: list[dict],
    signals: dict,
    activity_log_signal: dict | None = None,
) -> dict:
    """
    Build a deterministic drift model.

    Parameters
    ----------
    results : list[dict]
        Assessment control results.
    signals : dict
        Signal name → signal data dict.
    activity_log_signal : dict | None
        If available, the activity_log signal data for enhanced mode.

    Returns
    -------
    dict conforming to drift_model schema.
    """
    mode = "activity_log_backed" if activity_log_signal else "static"

    factors = _evaluate_factors(results, signals)
    active_factors = [f for f in factors if f["active"]]
    drift_score = sum(f["weight"] for f in active_factors)

    if drift_score >= 0.60:
        likelihood = "High"
    elif drift_score >= 0.30:
        likelihood = "Medium"
    else:
        likelihood = "Low"

    # Build evidence refs from active factors
    signal_refs = []
    for f in active_factors:
        if f.get("signal_key"):
            signal_refs.append(f"signal:{f['signal_key']}")

    # Control refs: failing controls related to drift
    drift_controls = []
    for r in results:
        if r.get("status") == "Fail":
            section = (r.get("section") or "").lower()
            if any(kw in section for kw in ("management", "governance", "security")):
                drift_controls.append(r.get("control_id", ""))
    drift_controls = list(set(c for c in drift_controls if c))[:15]

    # Confidence: based on signal coverage for drift-relevant signals
    covered_signals = sum(
        1 for f in factors
        if f.get("signal_key") and signals.get(f["signal_key"])
    )
    total_signal_factors = sum(1 for f in factors if f.get("signal_key"))
    signal_coverage_pct = (covered_signals / max(total_signal_factors, 1)) * 100

    ctrl_confidences = [
        r.get("confidence_score", 0.5)
        for r in results
        if r.get("control_id") in drift_controls
    ]
    confidence = compute_derived_confidence(ctrl_confidences, signal_coverage_pct)

    # Activity log enhancement
    activity_log_insights = []
    if activity_log_signal and activity_log_signal.get("data"):
        data = activity_log_signal["data"]
        # If we have change velocity data, use it
        if isinstance(data, dict):
            change_count = data.get("change_count_30d", 0)
            if change_count > 50:
                activity_log_insights.append(
                    f"{change_count} management plane changes in 30 days — "
                    "elevated configuration churn detected."
                )
                if likelihood == "Low":
                    likelihood = "Medium"
            elif change_count > 200:
                activity_log_insights.append(
                    f"{change_count} management plane changes in 30 days — "
                    "high configuration churn suggests active drift."
                )
                likelihood = "High"

    return {
        "mode": mode,
        "drift_likelihood": likelihood,
        "drift_score": round(drift_score, 3),
        "active_factors": [
            {
                "factor": f["factor"],
                "description": f["description"],
                "weight": f["weight"],
            }
            for f in active_factors
        ],
        "all_factors_evaluated": len(factors),
        "confidence": confidence,
        "evidence_refs": {
            "controls": drift_controls[:10],
            "risks": [],
            "blockers": [],
            "signals": signal_refs,
            "mcp_queries": [],
        },
        "assumptions": [
            "Drift likelihood computed from signal gap analysis",
            f"Mode: {mode}" + (
                " — activity log data available for change velocity"
                if mode == "activity_log_backed"
                else " — no activity log data; using signal gaps only"
            ),
        ],
        "activity_log_insights": activity_log_insights,
    }
