"""Data-driven evaluator engine — reads the ALZ checklist repo and
automatically evaluates every item it can against available signals.

Instead of hand-writing evaluator classes per control, this reads
the official checklist from Azure/review-checklists and registers
a ChecklistSignalEvaluator for each item whose text matches a signal.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from signals.types import ControlResult, EvalContext, SignalResult, SignalStatus
from evaluators.registry import register_evaluator, EVALUATORS

log = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────
#  Keyword → signal mapping (order matters: first match wins)
# ──────────────────────────────────────────────────────────────────

KEYWORD_TO_SIGNAL: list[tuple[str, str | None]] = [
    # Firewall
    ("azure firewall", "resource_graph:azure_firewall"),
    ("firewall policy", "resource_graph:azure_firewall"),
    ("firewall subnet", "resource_graph:vnets"),
    ("firewall dns proxy", "resource_graph:azure_firewall"),
    ("firewall threat intelligence", "resource_graph:azure_firewall"),
    ("firewall idps", "resource_graph:azure_firewall"),
    ("firewall premium", "resource_graph:azure_firewall"),
    ("firewall classic", "resource_graph:azure_firewall"),
    ("firewall rules", "resource_graph:azure_firewall"),
    ("tls inspection", "resource_graph:azure_firewall"),
    ("app gateway", "resource_graph:app_gateways"),
    # App Gateway / WAF
    ("application gateway", "resource_graph:app_gateways"),
    ("waf polic", "resource_graph:app_gateways"),
    ("waf log", "resource_graph:front_doors"),
    # Front Door
    ("front door", "resource_graph:front_doors"),
    # Load Balancer
    ("load balancer", "resource_graph:load_balancers"),
    # Bastion
    ("bastion", "resource_graph:bastion_hosts"),
    # Gateway (ER / VPN)
    ("expressroute", "resource_graph:vnet_gateways"),
    ("vpn gateway", "resource_graph:vnet_gateways"),
    ("vpn appliance", "resource_graph:vnet_gateways"),
    ("route server", "resource_graph:vnet_gateways"),
    ("gatewaysubnet", "resource_graph:gateway_subnets"),
    ("gateway subnet", "resource_graph:gateway_subnets"),
    # Route tables
    ("route table", "resource_graph:route_tables"),
    # Private endpoints / DNS
    ("private endpoint", "resource_graph:private_endpoints"),
    ("private link", "resource_graph:private_endpoints"),
    ("private dns", "resource_graph:dns_zones"),
    ("dns zone", "resource_graph:dns_zones"),
    ("auto-registration", "resource_graph:dns_zones"),
    ("dns resolution", "resource_graph:dns_zones"),
    ("port 65330", None),
    ("dns proxy", "resource_graph:azure_firewall"),
    # NSG
    ("nsg", "resource_graph:nsgs"),
    ("network security group", "resource_graph:nsgs"),
    # DDoS
    ("ddos", "resource_graph:vnets"),
    # Public IP
    ("public ip", "resource_graph:public_ips"),
    # VNet / Subnet / Peering
    ("vnet peering", "resource_graph:vnet_peerings"),
    ("virtual network peering", "resource_graph:vnet_peerings"),
    ("service endpoint", "resource_graph:vnets"),
    ("subnet creation", "resource_graph:vnets"),
    ("virtual network", "resource_graph:vnets"),
    ("vnet", "resource_graph:vnets"),
    ("ip address space", "resource_graph:vnets"),
    ("overlapping ip", "resource_graph:vnets"),
    ("address space", "resource_graph:vnets"),
    # Network flow / watcher
    ("flow log", "network:watcher_posture"),
    ("traffic analytics", "network:watcher_posture"),
    ("network watcher", "network:watcher_posture"),
    ("connection monitor", "network:watcher_posture"),
    # Virtual WAN — separate service, vnets signal can't verify
    ("virtual wan", None),
    ("secured hub", None),
    # MG / governance — only match when text is about MG structure itself
    ("management group", "arm:mg_hierarchy"),
    ("root management group", "arm:mg_hierarchy"),
    ("platform management group", "arm:mg_hierarchy"),
    ("sandbox management group", "arm:mg_hierarchy"),
    ("connectivity management group", "arm:mg_hierarchy"),
    ("landing zone management group", "arm:mg_hierarchy"),
    # "landing zone" alone is too broad — items about deploying resources
    # IN the landing zone should not match MG hierarchy signal
    ("landing zone", None),
    # Policy
    ("azure policy", "policy:assignments"),
    ("policy assignment", "policy:assignments"),
    ("policy definition", "policy:assignments"),
    ("policy initiative", "policy:assignments"),
    ("policy compliance", "policy:compliance_summary"),
    # Defender / Security
    ("defender", "defender:pricings"),
    ("secure score", "defender:secure_score"),
    ("microsoft sentinel", "monitor:workspace_topology"),
    ("sentinel", "monitor:workspace_topology"),
    # Diagnostics / Monitor
    ("diagnostic setting", "monitor:diag_coverage_sample"),
    ("diagnostic log", "monitor:diag_coverage_sample"),
    ("log analytics", "monitor:workspace_topology"),
    ("azure monitor", "monitor:workspace_topology"),
    ("monitor log", "monitor:workspace_topology"),
    ("action group", "monitor:action_group_coverage"),
    ("service health", "monitor:availability_signals"),
    ("alert", "monitor:alert_action_mapping"),
    # Identity / Entra
    ("conditional access", "identity:admin_ca_coverage"),
    ("multi-factor authentication", "identity:admin_ca_coverage"),
    ("mfa", "identity:admin_ca_coverage"),
    ("privileged identity management", "identity:pim_maturity"),
    ("pim", "identity:pim_maturity"),
    ("break-glass", "identity:breakglass_validation"),
    ("emergency access", "identity:breakglass_validation"),
    ("custom rbac", None),
    ("on-premises synced", None),
    ("synced accounts", None),
    ("data plane access", None),
    ("rbac", "identity:rbac_hygiene"),
    ("role assignment", "identity:rbac_hygiene"),
    ("managed identit", "resource_graph:managed_identities"),
    ("service principal", "identity:sp_owner_risk"),
    ("entra id log", "identity:entra_log_availability"),
    ("entra group", "identity:rbac_hygiene"),
    ("entra id only group", "identity:rbac_hygiene"),
    ("entra domain service", None),
    ("entra connect", None),
    ("entra id application proxy", None),
    ("entra", "identity:entra_log_availability"),
    # Cost / Billing
    ("budget", "cost:management_posture"),
    ("cost management", "cost:management_posture"),
    ("cost report", "cost:management_posture"),
    # Tags
    ("tag", "resource_graph:tag_coverage"),
    # Resource posture
    ("storage account", "resource_graph:storage_posture"),
    ("key vault", "resource_graph:keyvault_posture"),
    ("aks", "resource_graph:aks_posture"),
    ("container registr", "resource_graph:acr_posture"),
    ("backup", "resource_graph:backup_coverage"),
    ("site recovery", "resource_graph:backup_coverage"),
    ("resource lock", "resource_graph:resource_locks"),
    # Update Manager
    ("update manager", "manage:update_manager"),
    # Lighthouse — no signal available
    ("lighthouse", None),
    # Availability zones (only for actual LB/compute, not identity/AD)
    ("identity resources in multiple regions", None),
    ("identity services", None),
    ("domain controller", None),
    ("zone-redundant", "resource_graph:load_balancers"),
    # VM / compute
    ("virtual machine", "resource_graph:vnets"),
]


# ──────────────────────────────────────────────────────────────────
#  Exclusion logic — data-driven, not hard-coded patterns.
#  Subcategories that are purely organizational/process.
# ──────────────────────────────────────────────────────────────────

# Subcategories where items are about people/process, not infra.
# Derived from the checklist structure, not from item text.
PROCESS_SUBCATEGORIES: set[str] = {
    "DevOps Team Topologies",
    "Development Lifecycle",
    "Development Strategy",
    "Cloud Solution Provider",
    "Enterprise Agreement",
    "Microsoft Customer Agreement",
}


def _match_signal(text: str, subcategory: str = "") -> str | None:
    """Return the signal_bus_name for a checklist item, or None if manual.

    Uses the item's subcategory from the checklist repo to exclude
    process/organizational items that can't be verified by signals.
    """
    # Subcategory-based exclusion (from the checklist data, not hard-coded text)
    if subcategory in PROCESS_SUBCATEGORIES:
        return None

    text_lower = text.lower()
    for keyword, signal in KEYWORD_TO_SIGNAL:
        if keyword in text_lower:
            return signal  # None means explicit exclusion (keyword matched but no signal)
    return None


# ──────────────────────────────────────────────────────────────────
#  Generic evaluator — one class, many instances
# ──────────────────────────────────────────────────────────────────

@dataclass
class ChecklistSignalEvaluator:
    """Data-driven evaluator for an ALZ checklist item."""
    control_id: str
    required_signals: list[str] = field(default_factory=list)
    checklist_text: str = ""
    checklist_id: str = ""

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        sig_name = self.required_signals[0]
        sig = signals.get(sig_name)

        if sig is None or sig.status == SignalStatus.NOT_AVAILABLE:
            return ControlResult(
                status="Manual", confidence="Low",
                reason=f"Signal {sig_name} not available.",
                signals_used=self.required_signals,
            )

        if sig.status in (SignalStatus.ERROR, SignalStatus.SIGNAL_ERROR):
            return ControlResult(
                status="Error", confidence="Low",
                reason=sig.error_msg or f"Signal {sig_name} error.",
                signals_used=self.required_signals,
            )

        items = sig.items or []
        raw = sig.raw or {}
        item_count = len(items) if items else raw.get("count", 0)

        # Coverage-based signals
        coverage = raw.get("coverage", {})
        if isinstance(coverage, dict) and coverage.get("applicable", 0) > 0:
            ratio = coverage.get("ratio", 0)
            applicable = coverage.get("applicable", 0)
            compliant = coverage.get("compliant", 0)
            pct = round(ratio * 100, 1)
            if ratio >= 0.8:
                return ControlResult(
                    status="Pass", severity="Medium", confidence="High",
                    reason=f"Signal: {sig_name} · {compliant}/{applicable} compliant ({pct}%).",
                    signals_used=self.required_signals,
                )
            elif ratio >= 0.5:
                return ControlResult(
                    status="Partial", severity="Medium", confidence="High",
                    reason=f"Signal: {sig_name} · {compliant}/{applicable} compliant ({pct}%).",
                    signals_used=self.required_signals,
                )
            else:
                return ControlResult(
                    status="Fail", severity="Medium", confidence="High",
                    reason=f"Signal: {sig_name} · {compliant}/{applicable} compliant ({pct}%).",
                    signals_used=self.required_signals,
                )

        # MG hierarchy checks — MGs exist but can't verify specific MG-level config
        if raw.get("management_group_count", 0) > 1:
            return ControlResult(
                status="Partial", severity="Medium", confidence="Low",
                reason=f"Signal: {sig_name} · {raw['management_group_count']} management groups. Verify specific configuration.",
                signals_used=self.required_signals,
            )

        # Policy checks — policies exist but can't verify the specific policy
        if raw.get("total_assignments", 0) > 0 or raw.get("assignment_count", 0) > 0:
            count = raw.get("total_assignments", raw.get("assignment_count", 0))
            return ControlResult(
                status="Partial", severity="Medium", confidence="Low",
                reason=f"Signal: {sig_name} · {count} policy assignment(s). Verify specific policy.",
                signals_used=self.required_signals,
            )

        # Presence check — resource exists but we can't verify the SPECIFIC
        # configuration this checklist item asks about. Report Partial
        # so the CSA knows to verify the detail during the workshop.
        if item_count > 0:
            return ControlResult(
                status="Partial", severity="Medium", confidence="Low",
                reason=f"Signal: {sig_name} · {item_count} resource(s) detected. Verify specific configuration.",
                signals_used=self.required_signals,
            )

        return ControlResult(
            status="Fail", severity="Medium", confidence="Medium",
            reason=f"Signal: {sig_name} · No resources detected.",
            signals_used=self.required_signals,
        )


# ──────────────────────────────────────────────────────────────────
#  Registration API
# ──────────────────────────────────────────────────────────────────

CATEGORY_TO_DESIGN_AREA: dict[str, str] = {
    "Azure Billing and Microsoft Entra ID Tenants": "billing",
    "Identity and Access Management": "identity_access",
    "Resource Organization": "resource_org",
    "Network Topology and Connectivity": "network_topology",
    "Security": "security",
    "Management": "management",
    "Governance": "governance",
    "Platform Automation and DevOps": "platform_automation",
}


def register_checklist_evaluators(checklist_items: list[dict[str, Any]]) -> int:
    """Register evaluators for all automatable checklist items.

    Skips items that already have a hand-written evaluator.
    Returns count of newly registered evaluators.
    """
    registered = 0
    for item in checklist_items:
        guid = item.get("guid", "")
        if not guid or guid in EVALUATORS:
            continue

        text = item.get("text", "") or ""
        subcategory = item.get("subcategory", "")
        signal = _match_signal(text, subcategory)
        if signal is None:
            continue

        evaluator = ChecklistSignalEvaluator(
            control_id=guid,
            required_signals=[signal],
            checklist_text=text[:200],
            checklist_id=item.get("id", ""),
        )
        register_evaluator(evaluator)
        registered += 1

    return registered
