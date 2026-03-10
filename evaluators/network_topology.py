"""Network Topology & Connectivity evaluators — ALZ checklist section.

Evaluates controls from the official 'Network Topology and Connectivity'
design area using Resource Graph signals.  Each evaluator maps to one
checklist GUID from the Azure Review Checklist.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from signals.types import ControlResult, EvalContext, SignalResult, SignalStatus
from evaluators.registry import register_evaluator


def _to_evidence(item: dict) -> dict:
    return {
        "type": "resource",
        "resource_id": item.get("id", ""),
        "summary": item.get("name", ""),
        "properties": {k: v for k, v in item.items() if k not in ("id", "name")},
    }


# ── Standard Load Balancer SKU ───────────────────────────────────
# Checklist: "Use Standard Load Balancer SKU with a zone-redundant deployment"
@dataclass
class StandardLBSKUEvaluator:
    control_id: str = "9dcd6250-9c4a-4382-aa9b-5b84c64fc1fe"
    required_signals: list[str] = field(
        default_factory=lambda: ["resource_graph:load_balancers"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        sig = signals["resource_graph:load_balancers"]
        if sig.status != SignalStatus.OK:
            return ControlResult(status="Error", confidence="Low",
                                 reason=sig.error_msg or "Load balancer signal unavailable",
                                 signals_used=self.required_signals)

        items = sig.items or []
        if not items:
            return ControlResult(status="NotApplicable", severity="High", confidence="High",
                                 reason="No load balancers found in scope.",
                                 signals_used=self.required_signals)

        non_standard = [lb for lb in items if (lb.get("skuName") or "").lower() != "standard"]
        if non_standard:
            return ControlResult(
                status="Fail", severity="High", confidence="High",
                reason=f"{len(non_standard)} load balancer(s) not using Standard SKU.",
                evidence=[_to_evidence(lb) for lb in non_standard[:10]],
                signals_used=self.required_signals,
            )
        return ControlResult(
            status="Pass", severity="High", confidence="High",
            reason=f"All {len(items)} load balancer(s) use Standard SKU.",
            signals_used=self.required_signals,
        )


register_evaluator(StandardLBSKUEvaluator())


# ── LB Backend Pool Instances ────────────────────────────────────
# Checklist: "Ensure load balancer backend pool(s) contains at least two instances"
@dataclass
class LBBackendPoolEvaluator:
    control_id: str = "48682fb1-1e86-4458-a686-518ebd47393d"
    required_signals: list[str] = field(
        default_factory=lambda: ["resource_graph:load_balancers"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        sig = signals["resource_graph:load_balancers"]
        if sig.status != SignalStatus.OK:
            return ControlResult(status="Error", confidence="Low",
                                 reason=sig.error_msg or "Load balancer signal unavailable",
                                 signals_used=self.required_signals)

        items = sig.items or []
        if not items:
            return ControlResult(status="NotApplicable", severity="High", confidence="High",
                                 reason="No load balancers found in scope.",
                                 signals_used=self.required_signals)

        # Backend pool count is a proxy — we can't see instance count via RG
        no_backend = [lb for lb in items if (lb.get("backendPools") or 0) == 0]
        if no_backend:
            return ControlResult(
                status="Fail", severity="High", confidence="Medium",
                reason=f"{len(no_backend)} load balancer(s) have no backend pools configured.",
                evidence=[_to_evidence(lb) for lb in no_backend[:10]],
                signals_used=self.required_signals,
            )
        return ControlResult(
            status="Pass", severity="High", confidence="Medium",
            reason=f"All {len(items)} load balancer(s) have backend pools configured.",
            signals_used=self.required_signals,
        )


register_evaluator(LBBackendPoolEvaluator())


# ── VNet Peering — Allow Traffic to Remote VNet ──────────────────
# Checklist: "Use the setting 'Allow traffic to remote virtual network'"
@dataclass
class VNetPeeringTrafficEvaluator:
    control_id: str = "c76cb5a2-abe2-11ed-afa1-0242ac120002"
    required_signals: list[str] = field(
        default_factory=lambda: ["resource_graph:vnet_peerings"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        sig = signals["resource_graph:vnet_peerings"]
        if sig.status != SignalStatus.OK:
            return ControlResult(status="Error", confidence="Low",
                                 reason=sig.error_msg or "VNet peering signal unavailable",
                                 signals_used=self.required_signals)

        items = sig.items or []
        if not items:
            return ControlResult(status="NotApplicable", severity="High", confidence="High",
                                 reason="No VNet peerings found in scope.",
                                 signals_used=self.required_signals)

        blocked = [p for p in items
                   if (p.get("allowVnetAccess") or "").lower() not in ("true", "1")]
        if blocked:
            return ControlResult(
                status="Fail", severity="High", confidence="High",
                reason=f"{len(blocked)} VNet peering(s) do not allow traffic to remote VNet.",
                evidence=[_to_evidence(p) for p in blocked[:10]],
                signals_used=self.required_signals,
            )
        return ControlResult(
            status="Pass", severity="High", confidence="High",
            reason=f"All {len(items)} VNet peering(s) allow traffic to remote virtual network.",
            signals_used=self.required_signals,
        )


register_evaluator(VNetPeeringTrafficEvaluator())


# ── Azure Bastion Deployed ───────────────────────────────────────
# Checklist: "Use Azure Bastion to securely connect to your network"
@dataclass
class BastionDeployedEvaluator:
    control_id: str = "ee1ac551-c4d5-46cf-b035-d0a3c50d87ad"
    required_signals: list[str] = field(
        default_factory=lambda: ["resource_graph:bastion_hosts"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        sig = signals["resource_graph:bastion_hosts"]
        if sig.status != SignalStatus.OK:
            return ControlResult(status="Error", confidence="Low",
                                 reason=sig.error_msg or "Bastion signal unavailable",
                                 signals_used=self.required_signals)

        items = sig.items or []
        if not items:
            return ControlResult(
                status="Fail", severity="Medium", confidence="High",
                reason="No Azure Bastion hosts detected. Deploy Bastion for secure VM access.",
                signals_used=self.required_signals,
            )
        return ControlResult(
            status="Pass", severity="Medium", confidence="High",
            reason=f"{len(items)} Azure Bastion host(s) detected.",
            evidence=[_to_evidence(b) for b in items[:10]],
            signals_used=self.required_signals,
        )


register_evaluator(BastionDeployedEvaluator())


# ── Azure Front Door with WAF ────────────────────────────────────
# Checklist: "Use Azure Front Door and WAF policies to provide global protection"
@dataclass
class FrontDoorWAFEvaluator:
    control_id: str = "1d7aa9b6-4704-4489-a804-2d88e79d17b7"
    required_signals: list[str] = field(
        default_factory=lambda: ["resource_graph:front_doors"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        sig = signals["resource_graph:front_doors"]
        if sig.status != SignalStatus.OK:
            return ControlResult(status="Error", confidence="Low",
                                 reason=sig.error_msg or "Front Door signal unavailable",
                                 signals_used=self.required_signals)

        items = sig.items or []
        if not items:
            return ControlResult(
                status="Fail", severity="Medium", confidence="Medium",
                reason="No Azure Front Door or CDN profiles detected for global HTTP/S protection.",
                signals_used=self.required_signals,
            )
        return ControlResult(
            status="Pass", severity="Medium", confidence="High",
            reason=f"{len(items)} Azure Front Door / CDN profile(s) detected.",
            evidence=[_to_evidence(fd) for fd in items[:10]],
            signals_used=self.required_signals,
        )


register_evaluator(FrontDoorWAFEvaluator())


# ── Private DNS Zones ────────────────────────────────────────────
# Checklist: "Use Azure Private DNS for resolution with a delegated zone"
@dataclass
class PrivateDNSEvaluator:
    control_id: str = "153e8908-ae28-4c84-a33b-6b7808b9fe5c"
    required_signals: list[str] = field(
        default_factory=lambda: ["resource_graph:dns_zones"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        sig = signals["resource_graph:dns_zones"]
        if sig.status != SignalStatus.OK:
            return ControlResult(status="Error", confidence="Low",
                                 reason=sig.error_msg or "DNS zone signal unavailable",
                                 signals_used=self.required_signals)

        raw = sig.raw or {}
        private_count = raw.get("private_zones", 0)
        total = raw.get("count", 0)

        if total == 0:
            return ControlResult(
                status="Fail", severity="Medium", confidence="Medium",
                reason="No DNS zones found. Azure Private DNS is recommended for internal resolution.",
                signals_used=self.required_signals,
            )
        if private_count == 0:
            return ControlResult(
                status="Fail", severity="Medium", confidence="High",
                reason=f"{total} DNS zone(s) found but none are private. Deploy Azure Private DNS zones.",
                signals_used=self.required_signals,
            )
        return ControlResult(
            status="Pass", severity="Medium", confidence="High",
            reason=f"{private_count} Azure Private DNS zone(s) detected (of {total} total).",
            signals_used=self.required_signals,
        )


register_evaluator(PrivateDNSEvaluator())


# ── DNS Auto-Registration ────────────────────────────────────────
# Checklist: "Enable auto-registration for Azure DNS to manage lifecycle of DNS records"
@dataclass
class DNSAutoRegistrationEvaluator:
    control_id: str = "614658d3-558f-4d77-849b-821112df27ee"
    required_signals: list[str] = field(
        default_factory=lambda: ["resource_graph:dns_zones"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        sig = signals["resource_graph:dns_zones"]
        if sig.status != SignalStatus.OK:
            return ControlResult(status="Error", confidence="Low",
                                 reason=sig.error_msg or "DNS zone signal unavailable",
                                 signals_used=self.required_signals)

        raw = sig.raw or {}
        private_count = raw.get("private_zones", 0)
        if private_count == 0:
            return ControlResult(
                status="Fail", severity="High", confidence="Medium",
                reason="No Private DNS zones found. Auto-registration requires Private DNS zones.",
                signals_used=self.required_signals,
            )
        return ControlResult(
            status="Partial", severity="High", confidence="Medium",
            reason=f"{private_count} Private DNS zone(s) exist. Verify auto-registration is enabled on VNet links.",
            signals_used=self.required_signals,
        )


register_evaluator(DNSAutoRegistrationEvaluator())


# ── Gateway Subnet Size (/27 or larger) ──────────────────────────
# Checklist: "Use at least a /27 prefix for your Gateway subnets"
@dataclass
class GatewaySubnetSizeEvaluator:
    control_id: str = "f2aad7e3-bb03-4adc-8606-4123d342a917"
    required_signals: list[str] = field(
        default_factory=lambda: ["resource_graph:gateway_subnets"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        sig = signals["resource_graph:gateway_subnets"]
        if sig.status != SignalStatus.OK:
            return ControlResult(status="Error", confidence="Low",
                                 reason=sig.error_msg or "Gateway subnet signal unavailable",
                                 signals_used=self.required_signals)

        items = sig.items or []
        if not items:
            return ControlResult(status="NotApplicable", severity="High", confidence="High",
                                 reason="No GatewaySubnets found in scope.",
                                 signals_used=self.required_signals)

        raw = sig.raw or {}
        compliant = raw.get("compliant_count", 0)
        total = raw.get("count", len(items))
        non_compliant = total - compliant

        if non_compliant > 0:
            return ControlResult(
                status="Fail", severity="High", confidence="High",
                reason=f"{non_compliant} GatewaySubnet(s) smaller than /27.",
                evidence=[_to_evidence(s) for s in items[:10]],
                signals_used=self.required_signals,
            )
        return ControlResult(
            status="Pass", severity="High", confidence="High",
            reason=f"All {total} GatewaySubnet(s) are /27 or larger.",
            signals_used=self.required_signals,
        )


register_evaluator(GatewaySubnetSizeEvaluator())


# ── DDoS Logs for Protected IPs ─────────────────────────────────
# Checklist: "Add diagnostic settings to save DDoS related logs for all protected public IPs"
@dataclass
class DDoSLogsEvaluator:
    control_id: str = "b1c82a3f-2320-4dfa-8972-7ae4823c8930"
    required_signals: list[str] = field(
        default_factory=lambda: ["resource_graph:vnets", "monitor:diag_coverage_sample"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        vnets = signals["resource_graph:vnets"]
        diag = signals["monitor:diag_coverage_sample"]

        if vnets.status != SignalStatus.OK:
            return ControlResult(status="Error", confidence="Low",
                                 reason="VNet signal unavailable.",
                                 signals_used=self.required_signals)

        ddos_enabled = [v for v in (vnets.items or [])
                        if v.get("ddosProtectionPlan") is True
                        or str(v.get("ddosProtectionPlan")).lower() == "true"]

        if not ddos_enabled:
            return ControlResult(
                status="Fail", severity="High", confidence="High",
                reason="No VNets with DDoS Protection enabled — cannot verify DDoS log configuration.",
                signals_used=self.required_signals,
            )

        diag_pct = (diag.raw or {}).get("diag_coverage_percent", 0) if diag.status == SignalStatus.OK else 0
        if diag_pct < 50:
            return ControlResult(
                status="Partial", severity="High", confidence="Medium",
                reason=f"{len(ddos_enabled)} VNet(s) have DDoS Protection, but overall diagnostic coverage is {diag_pct}%.",
                signals_used=self.required_signals,
            )
        return ControlResult(
            status="Pass", severity="High", confidence="Medium",
            reason=f"{len(ddos_enabled)} VNet(s) with DDoS Protection and {diag_pct}% diagnostic coverage.",
            signals_used=self.required_signals,
        )


register_evaluator(DDoSLogsEvaluator())


# ── ExpressRoute Gateway Deployed ────────────────────────────────
# Checklist: "Deploy shared networking services, including ExpressRoute gateways, VPN gateways, and Azure Firewall"
@dataclass
class SharedNetworkingServicesEvaluator:
    control_id: str = "7dd61623-a364-4a90-9eca-e48ebd54cd7d"
    required_signals: list[str] = field(
        default_factory=lambda: ["resource_graph:vnet_gateways", "resource_graph:azure_firewall"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        gw = signals["resource_graph:vnet_gateways"]
        fw = signals["resource_graph:azure_firewall"]
        if gw.status != SignalStatus.OK:
            return ControlResult(status="Error", confidence="Low",
                                 reason=gw.error_msg or "VNet gateway signal unavailable",
                                 signals_used=self.required_signals)

        raw = gw.raw or {}
        er_count = raw.get("expressroute_count", 0)
        vpn_count = raw.get("vpn_count", 0)
        fw_count = len(fw.items or []) if fw.status == SignalStatus.OK else 0

        deployed = []
        if er_count > 0:
            deployed.append(f"{er_count} ExpressRoute GW")
        if vpn_count > 0:
            deployed.append(f"{vpn_count} VPN GW")
        if fw_count > 0:
            deployed.append(f"{fw_count} Azure Firewall")

        if not deployed:
            return ControlResult(
                status="Fail", severity="High", confidence="High",
                reason="No ExpressRoute gateways, VPN gateways, or Azure Firewalls detected.",
                signals_used=self.required_signals,
            )

        if er_count == 0 and vpn_count == 0:
            return ControlResult(
                status="Partial", severity="High", confidence="High",
                reason=f"Azure Firewall present but no gateways: {', '.join(deployed)}.",
                signals_used=self.required_signals,
            )

        return ControlResult(
            status="Pass", severity="High", confidence="High",
            reason=f"Shared networking services deployed: {', '.join(deployed)}.",
            signals_used=self.required_signals,
        )


register_evaluator(SharedNetworkingServicesEvaluator())


# ── Firewall Diagnostic Logs ────────────────────────────────────
# Checklist: "Add diagnostic settings to save logs for all Azure Firewall deployments"
@dataclass
class FirewallDiagLogsEvaluator:
    control_id: str = "715d833d-4708-4527-90ac-1b142c7045ba"
    required_signals: list[str] = field(
        default_factory=lambda: ["resource_graph:azure_firewall", "monitor:diag_coverage_sample"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        fw = signals["resource_graph:azure_firewall"]
        diag = signals["monitor:diag_coverage_sample"]
        if fw.status != SignalStatus.OK:
            return ControlResult(status="Error", confidence="Low",
                                 reason=fw.error_msg or "Firewall signal unavailable",
                                 signals_used=self.required_signals)

        fw_items = fw.items or []
        if not fw_items:
            return ControlResult(status="NotApplicable", severity="High", confidence="High",
                                 reason="No Azure Firewalls found.",
                                 signals_used=self.required_signals)

        diag_pct = (diag.raw or {}).get("diag_coverage_percent", 0) if diag.status == SignalStatus.OK else 0
        if diag_pct < 50:
            return ControlResult(
                status="Fail", severity="High", confidence="Medium",
                reason=f"{len(fw_items)} firewall(s) present but overall diagnostic coverage is {diag_pct}%. Enable diagnostic logs.",
                signals_used=self.required_signals,
            )
        return ControlResult(
            status="Pass", severity="High", confidence="Medium",
            reason=f"{len(fw_items)} firewall(s) present with {diag_pct}% diagnostic coverage.",
            signals_used=self.required_signals,
        )


register_evaluator(FirewallDiagLogsEvaluator())


# ── Firewall Subnet Size (/26) ──────────────────────────────────
# Checklist: "Use a /26 prefix for your Azure Firewall subnets"
@dataclass
class FirewallSubnetSizeEvaluator:
    control_id: str = "22d6419e-b627-4d95-9e7d-019fa759387f"
    required_signals: list[str] = field(
        default_factory=lambda: ["resource_graph:vnets"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        vnets = signals["resource_graph:vnets"]
        if vnets.status != SignalStatus.OK:
            return ControlResult(status="Error", confidence="Low",
                                 reason=vnets.error_msg or "VNet signal unavailable",
                                 signals_used=self.required_signals)

        # The vnet items don't have subnet detail — this is a lower-confidence check
        # We rely on the dedicated gateway_subnets signal if available.
        # For /26 check on AzureFirewallSubnet, we provide a Partial verdict
        # recommending manual verification.
        fw_vnets = [v for v in (vnets.items or [])
                    if "hub" in (v.get("name") or "").lower()
                    or "fw" in (v.get("name") or "").lower()]

        if not fw_vnets:
            return ControlResult(status="NotApplicable", severity="High", confidence="Medium",
                                 reason="No hub/firewall VNets detected.",
                                 signals_used=self.required_signals)

        return ControlResult(
            status="Partial", severity="High", confidence="Medium",
            reason=f"{len(fw_vnets)} hub/firewall VNet(s) found. Verify AzureFirewallSubnet uses /26 prefix.",
            signals_used=self.required_signals,
        )


register_evaluator(FirewallSubnetSizeEvaluator())


# ── DDoS Protection on Firewall VNet ─────────────────────────────
# Checklist: "Configure DDoS on the Azure Firewall VNet"
@dataclass
class DDoSFirewallVNetEvaluator:
    control_id: str = "e8143efa-0301-4d62-be54-ca7b5ce566dc"
    required_signals: list[str] = field(
        default_factory=lambda: ["resource_graph:vnets", "resource_graph:azure_firewall"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        vnets = signals["resource_graph:vnets"]
        fw = signals["resource_graph:azure_firewall"]
        if vnets.status != SignalStatus.OK:
            return ControlResult(status="Error", confidence="Low",
                                 reason=vnets.error_msg or "VNet signal unavailable",
                                 signals_used=self.required_signals)

        fw_items = (fw.items or []) if fw.status == SignalStatus.OK else []
        if not fw_items:
            return ControlResult(status="NotApplicable", severity="High", confidence="High",
                                 reason="No Azure Firewalls found.",
                                 signals_used=self.required_signals)

        # Check if hub VNets have DDoS enabled
        hub_vnets = [v for v in (vnets.items or [])
                     if "hub" in (v.get("name") or "").lower()
                     or "fw" in (v.get("name") or "").lower()]

        if not hub_vnets:
            hub_vnets = vnets.items or []

        no_ddos = [v for v in hub_vnets
                   if not v.get("ddosProtectionPlan")
                   or str(v.get("ddosProtectionPlan")).lower() != "true"]

        if no_ddos:
            return ControlResult(
                status="Fail", severity="High", confidence="High",
                reason=f"{len(no_ddos)} VNet(s) hosting firewall lack DDoS Protection.",
                evidence=[_to_evidence(v) for v in no_ddos[:10]],
                signals_used=self.required_signals,
            )
        return ControlResult(
            status="Pass", severity="High", confidence="High",
            reason=f"DDoS Protection enabled on {len(hub_vnets)} firewall VNet(s).",
            signals_used=self.required_signals,
        )


register_evaluator(DDoSFirewallVNetEvaluator())


# ── Azure Firewall Premium ───────────────────────────────────────
# Checklist: "Use Azure Firewall Premium to enable additional security features"
@dataclass
class FirewallPremiumEvaluator:
    control_id: str = "c10d51ef-f999-455d-bba0-5c90ece07447"
    required_signals: list[str] = field(
        default_factory=lambda: ["resource_graph:azure_firewall"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        fw = signals["resource_graph:azure_firewall"]
        if fw.status != SignalStatus.OK:
            return ControlResult(status="Error", confidence="Low",
                                 reason=fw.error_msg or "Firewall signal unavailable",
                                 signals_used=self.required_signals)

        items = fw.items or []
        if not items:
            return ControlResult(status="NotApplicable", severity="High", confidence="High",
                                 reason="No Azure Firewalls found.",
                                 signals_used=self.required_signals)

        premium = [f for f in items if (f.get("sku") or "").lower() == "azfw_vnet"
                   or "premium" in (f.get("sku") or "").lower()]
        non_premium = [f for f in items if f not in premium]

        if non_premium and not premium:
            return ControlResult(
                status="Fail", severity="High", confidence="Medium",
                reason=f"No Azure Firewall Premium instances detected. {len(items)} firewall(s) found.",
                signals_used=self.required_signals,
            )

        if non_premium:
            return ControlResult(
                status="Partial", severity="High", confidence="Medium",
                reason=f"{len(non_premium)} firewall(s) are not Premium tier.",
                signals_used=self.required_signals,
            )

        return ControlResult(
            status="Pass", severity="High", confidence="Medium",
            reason=f"All {len(items)} firewall(s) appear to use Premium SKU.",
            signals_used=self.required_signals,
        )


register_evaluator(FirewallPremiumEvaluator())


# ── Firewall Availability Zones ──────────────────────────────────
# Checklist: "Deploy Azure Firewall across multiple availability zones"
@dataclass
class FirewallAZEvaluator:
    control_id: str = "d38ad60c-bc9e-4d49-b699-97e5d4dcf707"
    required_signals: list[str] = field(
        default_factory=lambda: ["resource_graph:azure_firewall"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        fw = signals["resource_graph:azure_firewall"]
        if fw.status != SignalStatus.OK:
            return ControlResult(status="Error", confidence="Low",
                                 reason=fw.error_msg or "Firewall signal unavailable",
                                 signals_used=self.required_signals)

        items = fw.items or []
        if not items:
            return ControlResult(status="NotApplicable", severity="High", confidence="High",
                                 reason="No Azure Firewalls found.",
                                 signals_used=self.required_signals)

        # Azure Firewall zone data isn't always in the standard RG projection
        return ControlResult(
            status="Partial", severity="High", confidence="Medium",
            reason=f"{len(items)} Azure Firewall(s) found. Verify zone-redundant deployment.",
            signals_used=self.required_signals,
        )


register_evaluator(FirewallAZEvaluator())


# ── Private Link for PaaS from on-premises ──────────────────────
# Checklist: "Access Azure PaaS services from on-premises via private endpoints"
@dataclass
class OnPremPrivateEndpointEvaluator:
    control_id: str = "b3e4563a-4d87-4397-98b6-62d6d15f512a"
    required_signals: list[str] = field(
        default_factory=lambda: ["resource_graph:private_endpoints", "resource_graph:vnet_gateways"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        pe = signals["resource_graph:private_endpoints"]
        gw = signals["resource_graph:vnet_gateways"]

        if pe.status != SignalStatus.OK:
            return ControlResult(status="Error", confidence="Low",
                                 reason=pe.error_msg or "Private endpoint signal unavailable",
                                 signals_used=self.required_signals)

        pe_count = len(pe.items or [])
        has_gateway = bool(gw.items) if gw.status == SignalStatus.OK else False

        if pe_count == 0:
            return ControlResult(
                status="Fail", severity="Medium", confidence="High",
                reason="No private endpoints found. PaaS services are not accessible via Private Link.",
                signals_used=self.required_signals,
            )

        if not has_gateway:
            return ControlResult(
                status="Partial", severity="Medium", confidence="Medium",
                reason=f"{pe_count} private endpoint(s) found but no ExpressRoute/VPN gateway for on-premises connectivity.",
                signals_used=self.required_signals,
            )

        return ControlResult(
            status="Pass", severity="Medium", confidence="Medium",
            reason=f"{pe_count} private endpoint(s) with gateway connectivity for on-premises access.",
            signals_used=self.required_signals,
        )


register_evaluator(OnPremPrivateEndpointEvaluator())


# ── Application Gateway with WAF ─────────────────────────────────
# Checklist: "Deploy WAF within a landing-zone virtual network for inbound HTTP/S"
@dataclass
class AppGatewayWAFEvaluator:
    control_id: str = "2363cefe-179b-4599-be0d-5973cd4cd21b"
    required_signals: list[str] = field(
        default_factory=lambda: ["resource_graph:app_gateways"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        sig = signals["resource_graph:app_gateways"]
        if sig.status != SignalStatus.OK:
            return ControlResult(status="Error", confidence="Low",
                                 reason=sig.error_msg or "App Gateway signal unavailable",
                                 signals_used=self.required_signals)

        items = sig.items or []
        if not items:
            return ControlResult(
                status="Fail", severity="High", confidence="Medium",
                reason="No Application Gateways found. Deploy WAF for inbound HTTP/S protection.",
                signals_used=self.required_signals,
            )

        raw = sig.raw or {}
        waf_count = raw.get("waf_enabled_count", 0)
        no_waf = len(items) - waf_count

        if no_waf > 0:
            return ControlResult(
                status="Partial", severity="High", confidence="High",
                reason=f"{no_waf} Application Gateway(s) without WAF enabled (of {len(items)} total).",
                signals_used=self.required_signals,
            )

        return ControlResult(
            status="Pass", severity="High", confidence="High",
            reason=f"All {len(items)} Application Gateway(s) have WAF enabled.",
            signals_used=self.required_signals,
        )


register_evaluator(AppGatewayWAFEvaluator())


# ── ExpressRoute as Primary Connection ───────────────────────────
# Checklist: "Use ExpressRoute as the primary connection to Azure. Use VPNs as backup."
@dataclass
class ExpressRoutePrimaryEvaluator:
    control_id: str = "359c373e-7dd6-4162-9a36-4a907ecae48e"
    required_signals: list[str] = field(
        default_factory=lambda: ["resource_graph:vnet_gateways"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        gw = signals["resource_graph:vnet_gateways"]
        if gw.status != SignalStatus.OK:
            return ControlResult(status="Error", confidence="Low",
                                 reason=gw.error_msg or "Gateway signal unavailable",
                                 signals_used=self.required_signals)

        raw = gw.raw or {}
        er_count = raw.get("expressroute_count", 0)
        vpn_count = raw.get("vpn_count", 0)

        if er_count == 0 and vpn_count == 0:
            return ControlResult(
                status="NotApplicable", severity="Medium", confidence="High",
                reason="No VNet gateways found — hybrid connectivity not configured.",
                signals_used=self.required_signals,
            )

        if er_count == 0:
            return ControlResult(
                status="Fail", severity="Medium", confidence="High",
                reason=f"Only VPN gateway(s) detected ({vpn_count}). ExpressRoute recommended as primary connection.",
                signals_used=self.required_signals,
            )

        if vpn_count > 0:
            return ControlResult(
                status="Pass", severity="Medium", confidence="High",
                reason=f"ExpressRoute ({er_count}) with VPN backup ({vpn_count}) — best practice.",
                signals_used=self.required_signals,
            )

        return ControlResult(
            status="Pass", severity="Medium", confidence="High",
            reason=f"{er_count} ExpressRoute gateway(s) deployed as primary connection.",
            signals_used=self.required_signals,
        )


register_evaluator(ExpressRoutePrimaryEvaluator())
