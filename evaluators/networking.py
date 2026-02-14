"""Networking evaluators — firewall, hub-spoke, public IPs, IP SKU, DDoS."""
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


# ── Azure Firewall ───────────────────────────────────────────────
@dataclass
class AzureFirewallEvaluator:
    control_id: str = "e6c4cfd3-e504-4547-a244-7ec66138a720"
    required_signals: list[str] = field(
        default_factory=lambda: ["resource_graph:azure_firewall"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        fw = signals["resource_graph:azure_firewall"]

        if fw.status != SignalStatus.OK:
            return ControlResult(
                status="Error", confidence="Low",
                reason=fw.error_msg or "Firewall signal unavailable",
                signals_used=self.required_signals,
            )

        if len(fw.items) == 0:
            return ControlResult(
                status="Fail", severity="High", confidence="High",
                reason="No Azure Firewall resources detected in visible subscriptions.",
                signals_used=self.required_signals,
                next_checks=[{
                    "signal": "resource_graph:route_tables",
                    "why": "Check if centralized egress routing exists without Azure Firewall (NVA scenario)",
                }],
            )

        return ControlResult(
            status="Pass", severity="High", confidence="High",
            reason=f"{len(fw.items)} Azure Firewall(s) detected.",
            evidence=[_to_evidence(x) for x in fw.items[:10]],
            signals_used=self.required_signals,
        )


register_evaluator(AzureFirewallEvaluator())


# ── Hub-Spoke Topology ───────────────────────────────────────────
@dataclass
class HubSpokeEvaluator:
    control_id: str = "e8bbac75-7155-49ab-a153-e8908ae28c84"
    required_signals: list[str] = field(
        default_factory=lambda: ["resource_graph:vnets", "resource_graph:azure_firewall"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        vnets = signals["resource_graph:vnets"]
        fw = signals["resource_graph:azure_firewall"]

        if vnets.status != SignalStatus.OK:
            return ControlResult(
                status="Error", confidence="Low",
                reason=vnets.error_msg or "VNet signal unavailable",
                signals_used=self.required_signals,
            )

        hub_candidates = [
            v for v in vnets.items
            if "hub" in (v.get("name", "") or "").lower()
            or (v.get("peerings", 0) or 0) > 2
        ]

        has_firewall = fw.status == SignalStatus.OK and len(fw.items) > 0

        if not hub_candidates and not has_firewall:
            return ControlResult(
                status="Fail", severity="High", confidence="High",
                reason="No hub VNet or Azure Firewall detected. Hub-spoke topology may not be implemented.",
                signals_used=self.required_signals,
                next_checks=[{
                    "signal": "resource_graph:route_tables",
                    "why": "Validate if UDRs route through a centralized NVA",
                }],
            )

        if hub_candidates:
            return ControlResult(
                status="Pass", severity="High", confidence="High",
                reason=f"Hub VNet(s) detected: {', '.join(v['name'] for v in hub_candidates)}.",
                evidence=[_to_evidence(v) for v in hub_candidates[:5]],
                signals_used=self.required_signals,
            )

        return ControlResult(
            status="Partial", severity="High", confidence="Medium",
            reason="Azure Firewall present but no VNet with hub naming pattern. "
                   "Topology may use Virtual WAN or non-standard naming.",
            evidence=[_to_evidence(f) for f in fw.items[:3]],
            signals_used=self.required_signals,
        )


register_evaluator(HubSpokeEvaluator())


# ── Public IP Addresses ──────────────────────────────────────────
@dataclass
class PublicIPEvaluator:
    control_id: str = "3c5a808d-c695-4c14-a63c-c7ab7a510e41"
    required_signals: list[str] = field(
        default_factory=lambda: ["resource_graph:public_ips"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        pips = signals["resource_graph:public_ips"]

        if pips.status != SignalStatus.OK:
            return ControlResult(
                status="Error", confidence="Low",
                reason=pips.error_msg or "Public IP signal unavailable",
                signals_used=self.required_signals,
            )

        if len(pips.items) == 0:
            return ControlResult(
                status="Pass", severity="Medium", confidence="High",
                reason="No public IP addresses detected.",
                signals_used=self.required_signals,
            )

        # PIs not associated to a load balancer or firewall are higher risk
        unassociated = [p for p in pips.items if not p.get("associatedTo")]
        if unassociated:
            return ControlResult(
                status="Fail", severity="Medium", confidence="High",
                reason=f"{len(pips.items)} public IP(s) detected, {len(unassociated)} unassociated. "
                       "Review for business justification.",
                evidence=[_to_evidence(p) for p in pips.items[:10]],
                signals_used=self.required_signals,
            )

        return ControlResult(
            status="Fail", severity="Medium", confidence="High",
            reason=f"{len(pips.items)} public IP(s) detected. Review for policy alignment.",
            evidence=[_to_evidence(p) for p in pips.items[:10]],
            signals_used=self.required_signals,
        )


register_evaluator(PublicIPEvaluator())


# ── Public IP SKU ─────────────────────────────────────────────────
@dataclass
class PublicIPSkuEvaluator:
    control_id: str = "0c47f486-656d-4699-8c30-edef5b8a93c4"
    required_signals: list[str] = field(
        default_factory=lambda: ["resource_graph:public_ips"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        pips = signals["resource_graph:public_ips"]

        if pips.status != SignalStatus.OK:
            return ControlResult(
                status="Error", confidence="Low",
                reason=pips.error_msg or "Public IP signal unavailable",
                signals_used=self.required_signals,
            )

        if len(pips.items) == 0:
            return ControlResult(
                status="Pass", severity="Medium", confidence="High",
                reason="No public IPs to evaluate.",
                signals_used=self.required_signals,
            )

        non_standard = [
            p for p in pips.items
            if (p.get("sku", "") or "").lower() != "standard"
        ]

        if non_standard:
            return ControlResult(
                status="Fail", severity="Medium", confidence="High",
                reason=f"{len(non_standard)} public IP(s) not using Standard SKU.",
                evidence=[_to_evidence(p) for p in non_standard[:10]],
                signals_used=self.required_signals,
            )

        return ControlResult(
            status="Pass", severity="Medium", confidence="High",
            reason="All public IPs use Standard SKU.",
            evidence=[_to_evidence(p) for p in pips.items[:5]],
            signals_used=self.required_signals,
        )


register_evaluator(PublicIPSkuEvaluator())


# ── DDoS Protection ──────────────────────────────────────────────
@dataclass
class DDoSEvaluator:
    control_id: str = "088137f5-e6c4-4cfd-9e50-4547c2447ec6"
    required_signals: list[str] = field(
        default_factory=lambda: ["resource_graph:vnets"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        vnets = signals["resource_graph:vnets"]

        if vnets.status != SignalStatus.OK:
            return ControlResult(
                status="Error", confidence="Low",
                reason=vnets.error_msg or "VNet signal unavailable",
                signals_used=self.required_signals,
            )

        if len(vnets.items) == 0:
            return ControlResult(
                status="Pass", severity="High", confidence="High",
                reason="No VNets to evaluate.",
                signals_used=self.required_signals,
            )

        unprotected = [v for v in vnets.items if not v.get("ddosProtectionPlan")]
        if unprotected:
            return ControlResult(
                status="Fail", severity="High", confidence="High",
                reason=f"{len(unprotected)} VNet(s) without DDoS Protection.",
                evidence=[_to_evidence(v) for v in unprotected[:10]],
                signals_used=self.required_signals,
                next_checks=[{
                    "signal": "resource_graph:public_ips",
                    "why": "Assess exposure — DDoS matters most when public IPs exist",
                }],
            )

        return ControlResult(
            status="Pass", severity="High", confidence="High",
            reason="All VNets have DDoS Protection enabled.",
            evidence=[_to_evidence(v) for v in vnets.items[:5]],
            signals_used=self.required_signals,
        )


register_evaluator(DDoSEvaluator())
