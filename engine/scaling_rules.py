"""Scaling Rules Engine — deterministic projection for multi-subscription scenarios.

Every projection is driven by an explicit rule_id.  No open-ended language.
If a condition is not in the ruleset, it MUST NOT be claimed.

Layer: Simulations (rule-based projection with explicit assumptions).
"""
from __future__ import annotations

from typing import Any

from engine.guardrails import empty_evidence_refs, merge_evidence_refs


# ── Rule definitions ──────────────────────────────────────────────

SCALING_RULES: dict[str, dict[str, Any]] = {
    "RULE-MG-001": {
        "condition": "missing_mg_hierarchy",
        "impact_template": (
            "Without a management group hierarchy, Azure Policy and RBAC "
            "inheritance cannot propagate to {n} subscriptions. Each subscription "
            "requires individual policy assignments, creating O(n) management overhead."
        ),
        "signal_key": "mg_hierarchy",
        "check_field": "management_group_access",
    },
    "RULE-LOG-001": {
        "condition": "no_central_logging",
        "impact_template": (
            "SOC visibility gap scales linearly: with {n} subscriptions and no "
            "centralised Log Analytics workspace, security events are siloed across "
            "{n} independent diagnostic configurations."
        ),
        "signal_key": "diag_coverage_sample",
        "check_field": "diagnostic_coverage_pct",
    },
    "RULE-FW-001": {
        "condition": "no_hub_firewall",
        "impact_template": (
            "Without a central Azure Firewall or NVA, egress control inconsistency "
            "risk grows with each spoke. At {n} subscriptions, {n} independent "
            "egress paths must be individually governed."
        ),
        "signal_key": "azure_firewall",
        "check_field": "has_azure_firewall",
    },
    "RULE-POLICY-001": {
        "condition": "no_root_policy",
        "impact_template": (
            "Without root-level policy assignments, policy drift grows "
            "exponentially with MG depth. At {n} subscriptions, manual policy "
            "alignment becomes untenable."
        ),
        "signal_key": "assignments",
        "check_field": "root_policy_count",
    },
    "RULE-RBAC-001": {
        "condition": "no_pim_custom_roles",
        "impact_template": (
            "Without PIM or custom RBAC roles, privilege creep risk scales "
            "with team count. At {n} subscriptions, standing Owner/Contributor "
            "assignments create an expanding attack surface."
        ),
        "signal_key": "rbac_hygiene",
        "check_field": "has_pim_or_custom_roles",
    },
    "RULE-NET-001": {
        "condition": "no_hub_spoke",
        "impact_template": (
            "Without a hub-spoke or Virtual WAN topology, network segmentation "
            "is impossible at scale. {n} subscriptions each route independently, "
            "preventing centralized inspection."
        ),
        "signal_key": "vnets",
        "check_field": "has_hub_spoke",
    },
    "RULE-DDP-001": {
        "condition": "no_ddos_protection",
        "impact_template": (
            "Public-facing workloads across {n} subscriptions lack DDoS Protection. "
            "Volumetric attacks against any public endpoint can impact availability "
            "and generate unexpected bandwidth costs."
        ),
        "signal_key": "pricings",
        "check_field": "ddos_enabled",
    },
    "RULE-DEFENDER-001": {
        "condition": "no_defender",
        "impact_template": (
            "With Defender for Cloud disabled, threat visibility gap scales "
            "linearly. At {n} subscriptions, runtime threats across compute, "
            "storage, and SQL resources go undetected."
        ),
        "signal_key": "pricings",
        "check_field": "defender_enabled",
    },
    "RULE-BACKUP-001": {
        "condition": "no_backup",
        "impact_template": (
            "Without backup coverage, data loss risk exists per workload. "
            "At {n} subscriptions, recovery point gaps multiply across "
            "all unprotected VMs and databases."
        ),
        "signal_key": "backup_coverage",
        "check_field": "backup_coverage_pct",
    },
    "RULE-LOCK-001": {
        "condition": "no_resource_locks",
        "impact_template": (
            "Without resource locks on critical infrastructure, accidental "
            "deletion risk exists. At {n} subscriptions, the blast radius "
            "of a single misoperation grows proportionally."
        ),
        "signal_key": "resource_locks",
        "check_field": "has_resource_locks",
    },
}

SCALING_SCENARIOS = [
    {"scenario": "5_subscriptions", "n": 5},
    {"scenario": "10_subscriptions", "n": 10},
    {"scenario": "50_subscriptions", "n": 50},
]


# ── Signal condition extraction ───────────────────────────────────

def _extract_conditions(results: list[dict], signals: dict) -> dict[str, bool]:
    """
    Extract boolean conditions from assessment results and signal data.

    Returns a dict of condition_name → True/False indicating whether
    the risk condition IS PRESENT (True = the gap exists).
    """
    conditions: dict[str, bool] = {}

    # MG hierarchy: check if management_group_access is False or mg_hierarchy signal missing
    mg_signal = signals.get("mg_hierarchy")
    conditions["missing_mg_hierarchy"] = (
        mg_signal is None
        or mg_signal.get("status") == "error"
        or not mg_signal.get("data")
    )

    # Central logging: check diagnostic coverage
    diag_signal = signals.get("diag_coverage_sample")
    if diag_signal and diag_signal.get("data"):
        coverage = diag_signal["data"].get("coverage_pct", 0)
        conditions["no_central_logging"] = coverage < 50
    else:
        conditions["no_central_logging"] = True  # unknown = assume gap

    # Firewall presence
    fw_signal = signals.get("azure_firewall")
    if fw_signal and fw_signal.get("data"):
        fw_count = fw_signal["data"].get("count", 0)
        conditions["no_hub_firewall"] = fw_count == 0
    else:
        conditions["no_hub_firewall"] = True

    # Root-level policy assignments
    policy_signal = signals.get("assignments")
    if policy_signal and policy_signal.get("data"):
        # Check for MG-scoped assignments
        assignments = policy_signal["data"]
        mg_assignments = [
            a for a in (assignments if isinstance(assignments, list) else [])
            if "/providers/Microsoft.Management/" in (a.get("scope", "") or "")
        ]
        conditions["no_root_policy"] = len(mg_assignments) == 0
    else:
        conditions["no_root_policy"] = True

    # PIM / custom RBAC
    rbac_signal = signals.get("rbac_hygiene")
    if rbac_signal and rbac_signal.get("data"):
        data = rbac_signal["data"]
        has_custom = data.get("custom_role_count", 0) > 0
        # PIM detection not always available, check for elevated assignments
        conditions["no_pim_custom_roles"] = not has_custom
    else:
        conditions["no_pim_custom_roles"] = True

    # Hub-spoke topology
    vnet_signal = signals.get("vnets")
    if vnet_signal and vnet_signal.get("data"):
        data = vnet_signal["data"]
        vnet_count = data.get("count", 0)
        peered = data.get("peered_count", 0)
        # Hub-spoke inferred if there are peerings
        conditions["no_hub_spoke"] = peered == 0 and vnet_count > 0
    else:
        conditions["no_hub_spoke"] = True

    # DDoS Protection
    pricing_signal = signals.get("pricings")
    if pricing_signal and pricing_signal.get("data"):
        data = pricing_signal["data"]
        plans = data if isinstance(data, list) else data.get("plans", [])
        ddos_on = any(
            p.get("name", "").lower() == "ddosprotection"
            and p.get("pricingTier", "").lower() == "standard"
            for p in plans
        ) if plans else False
        conditions["ddos_enabled"] = ddos_on
        conditions["no_ddos_protection"] = not ddos_on
    else:
        conditions["no_ddos_protection"] = True

    # Defender for Cloud
    if pricing_signal and pricing_signal.get("data"):
        data = pricing_signal["data"]
        plans = data if isinstance(data, list) else data.get("plans", [])
        defender_on = any(
            p.get("pricingTier", "").lower() == "standard"
            and p.get("name", "").lower() != "ddosprotection"
            for p in plans
        ) if plans else False
        conditions["no_defender"] = not defender_on
    else:
        conditions["no_defender"] = True

    # Backup coverage
    backup_signal = signals.get("backup_coverage")
    if backup_signal and backup_signal.get("data"):
        data = backup_signal["data"]
        coverage_pct = data.get("coverage_pct", 0)
        conditions["no_backup"] = coverage_pct < 50
    else:
        conditions["no_backup"] = True

    # Resource locks
    lock_signal = signals.get("resource_locks")
    if lock_signal and lock_signal.get("data"):
        data = lock_signal["data"]
        lock_count = data.get("lock_count", 0) if isinstance(data, dict) else 0
        conditions["no_resource_locks"] = lock_count == 0
    else:
        conditions["no_resource_locks"] = True

    return conditions


def _find_affected_controls(rule_id: str, rule: dict, results: list[dict]) -> list[str]:
    """Find control_ids affected by a scaling rule."""
    signal_key = rule["signal_key"]
    affected = []
    for r in results:
        signals_used = r.get("signals_used", [])
        # Controls that depend on the same signal
        if any(signal_key in s for s in signals_used):
            affected.append(r.get("control_id", ""))
        # Also include failing controls in related design areas
        if r.get("status") == "Fail":
            section = (r.get("section") or "").lower()
            condition = rule["condition"]
            if "mg" in condition and "governance" in section:
                affected.append(r.get("control_id", ""))
            elif "log" in condition and "management" in section:
                affected.append(r.get("control_id", ""))
            elif "fw" in condition and "network" in section:
                affected.append(r.get("control_id", ""))
    return list(set(c for c in affected if c))


# ── Public API ────────────────────────────────────────────────────

def build_scaling_simulation(
    results: list[dict],
    signals: dict,
    execution_context: dict | None = None,
) -> dict:
    """
    Build deterministic scaling simulation for 5/10/50 subscription scenarios.

    Every impact is backed by a rule_id, evidence_refs, and assumptions.
    No open-ended "it will break" language.

    Parameters
    ----------
    results : list[dict]
        Assessment control results.
    signals : dict
        Signal name → signal data dict.
    execution_context : dict
        Execution context (for current sub count).

    Returns
    -------
    dict conforming to scaling_simulation schema.
    """
    conditions = _extract_conditions(results, signals)
    current_subs = (execution_context or {}).get("subscription_count_visible", 1)

    scenarios = []
    for scenario_def in SCALING_SCENARIOS:
        scenario_name = scenario_def["scenario"]
        n = scenario_def["n"]

        if n <= current_subs:
            continue  # skip scenarios at or below current scale

        derived_impacts = []
        for rule_id, rule in SCALING_RULES.items():
            condition = rule["condition"]
            if conditions.get(condition, False):
                affected_controls = _find_affected_controls(rule_id, rule, results)
                impact = {
                    "impact_statement": rule["impact_template"].format(n=n),
                    "rule_id": rule_id,
                    "evidence_refs": {
                        "controls": affected_controls[:10],
                        "risks": [],
                        "blockers": [],
                        "signals": [f"signal:{rule['signal_key']}"],
                        "mcp_queries": [],
                    },
                    "assumptions": [
                        f"Organisation scales from {current_subs} to {n} subscriptions",
                        f"Current gap ({condition.replace('_', ' ')}) remains unresolved",
                    ],
                }
                derived_impacts.append(impact)

        scenarios.append({
            "scenario": scenario_name,
            "current_subscriptions": current_subs,
            "target_subscriptions": n,
            "derived_impacts": derived_impacts,
        })

    return {
        "scenarios": scenarios,
    }
