"""Resource Organization evaluators — ALZ checklist section.

Evaluates controls from the official 'Resource Organization' design area
using MG hierarchy, tag coverage, and resource distribution signals.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from signals.types import ControlResult, EvalContext, SignalResult, SignalStatus
from evaluators.registry import register_evaluator


def _mg_data(signals: dict[str, SignalResult]) -> dict | None:
    """Extract MG hierarchy dict from signals bundle."""
    sig = signals.get("arm:mg_hierarchy")
    if sig is None or sig.status != SignalStatus.OK:
        return None
    return sig.raw or (sig.items[0] if sig.items else None)


# ── Sandbox Management Group ─────────────────────────────────────
# Checklist: "Enforce a sandbox management group to allow users to immediately experiment with Azure"
@dataclass
class SandboxMGEvaluator:
    control_id: str = "667313b4-f566-44b5-b984-a859c773e7d2"
    required_signals: list[str] = field(
        default_factory=lambda: ["arm:mg_hierarchy"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        mg = _mg_data(signals)
        if mg is None:
            return ControlResult(
                status="Error", confidence="Low",
                reason="Management group hierarchy unavailable.",
                signals_used=self.required_signals,
            )

        has_sandbox = mg.get("has_sandbox_mg", False)
        # Also check the raw hierarchy for sandbox-named groups
        children = mg.get("children", [])
        sandbox_found = has_sandbox or any(
            "sandbox" in (c.get("name", "") or "").lower()
            or "sandbox" in (c.get("display_name", "") or "").lower()
            for c in children
        )

        if not sandbox_found:
            return ControlResult(
                status="Fail", severity="Medium", confidence="High",
                reason="No Sandbox management group detected.",
                evidence=[{"type": "metric", "resource_id": "", "summary": "Missing sandbox MG",
                          "properties": {"children": [c.get("name") for c in children[:10]]}}],
                signals_used=self.required_signals,
            )

        return ControlResult(
            status="Pass", severity="Medium", confidence="High",
            reason="Sandbox management group detected.",
            signals_used=self.required_signals,
        )


register_evaluator(SandboxMGEvaluator())


# ── No Subscriptions Under Root MG ───────────────────────────────
# Checklist: "Enforce no subscriptions are placed under the root management group"
@dataclass
class NoSubsUnderRootEvaluator:
    control_id: str = "33b6b780-8b9f-4e5c-9104-9d403a923c34"
    required_signals: list[str] = field(
        default_factory=lambda: ["arm:mg_hierarchy"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        mg = _mg_data(signals)
        if mg is None:
            return ControlResult(
                status="Error", confidence="Low",
                reason="Management group hierarchy unavailable.",
                signals_used=self.required_signals,
            )

        root_subs = mg.get("root_subscriptions", mg.get("subs_under_root", []))
        if isinstance(root_subs, int):
            root_sub_count = root_subs
        else:
            root_sub_count = len(root_subs) if root_subs else 0

        if root_sub_count > 0:
            return ControlResult(
                status="Fail", severity="Medium", confidence="High",
                reason=f"{root_sub_count} subscription(s) placed directly under the root management group.",
                signals_used=self.required_signals,
            )

        return ControlResult(
            status="Pass", severity="Medium", confidence="High",
            reason="No subscriptions placed under the root management group.",
            signals_used=self.required_signals,
        )


register_evaluator(NoSubsUnderRootEvaluator())


# ── MG RBAC Authorization ───────────────────────────────────────
# Checklist: "Enforce that only privileged users can operate management groups"
@dataclass
class MGRBACAuthorizationEvaluator:
    control_id: str = "74d00018-ac6a-49e0-8e6a-83de5de32c19"
    required_signals: list[str] = field(
        default_factory=lambda: ["arm:mg_hierarchy", "identity:rbac_hygiene"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        mg = _mg_data(signals)
        rbac = signals.get("identity:rbac_hygiene")

        if mg is None:
            return ControlResult(
                status="Error", confidence="Low",
                reason="Management group hierarchy unavailable.",
                signals_used=self.required_signals,
            )

        if rbac is None or rbac.status != SignalStatus.OK:
            return ControlResult(
                status="Partial", severity="Medium", confidence="Low",
                reason="MG hierarchy exists but RBAC signal unavailable for verification.",
                signals_used=self.required_signals,
            )

        raw = rbac.raw or {}
        owner_count = raw.get("owner_count", 0)

        if owner_count > 10:
            return ControlResult(
                status="Fail", severity="Medium", confidence="Medium",
                reason=f"{owner_count} Owner role assignments detected. Limit MG-level access to privileged users.",
                signals_used=self.required_signals,
            )

        return ControlResult(
            status="Pass", severity="Medium", confidence="Medium",
            reason=f"Management group access appears restricted ({owner_count} Owner assignments).",
            signals_used=self.required_signals,
        )


register_evaluator(MGRBACAuthorizationEvaluator())


# ── Tags for Billing & Cost Management ───────────────────────────
# Checklist: "Ensure tags are used for billing and cost management"
@dataclass
class TagsForBillingEvaluator:
    control_id: str = "5de32c19-9248-4160-9d5d-1e4e614658d3"
    required_signals: list[str] = field(
        default_factory=lambda: ["resource_graph:tag_coverage"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        sig = signals["resource_graph:tag_coverage"]
        if sig.status != SignalStatus.OK:
            return ControlResult(status="Error", confidence="Low",
                                 reason=sig.error_msg or "Tag coverage signal unavailable",
                                 signals_used=self.required_signals)

        raw = sig.raw or {}
        pct = raw.get("tag_coverage_percent", 0)
        total = raw.get("total_resources", 0)
        tagged = raw.get("tagged_resources", 0)

        if total == 0:
            return ControlResult(status="NotApplicable", severity="Medium", confidence="High",
                                 reason="No resources found in scope.",
                                 signals_used=self.required_signals)

        if pct < 30:
            return ControlResult(
                status="Fail", severity="Medium", confidence="High",
                reason=f"Tag coverage is {pct}% ({tagged}/{total} resources). Tags are essential for billing.",
                signals_used=self.required_signals,
            )

        if pct < 70:
            return ControlResult(
                status="Partial", severity="Medium", confidence="High",
                reason=f"Tag coverage is {pct}% ({tagged}/{total} resources). Target ≥ 70% for effective cost allocation.",
                signals_used=self.required_signals,
            )

        return ControlResult(
            status="Pass", severity="Medium", confidence="High",
            reason=f"Tag coverage is {pct}% ({tagged}/{total} resources).",
            signals_used=self.required_signals,
        )


register_evaluator(TagsForBillingEvaluator())


# ── Region Selection ─────────────────────────────────────────────
# Checklist: "Select the right Azure region/s for your deployment"
@dataclass
class RegionSelectionEvaluator:
    control_id: str = "250d81ce-8bbe-4f85-9051-6a18a8221e50"
    required_signals: list[str] = field(
        default_factory=lambda: ["resource_graph:vnets"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        sig = signals["resource_graph:vnets"]
        if sig.status != SignalStatus.OK:
            return ControlResult(status="Error", confidence="Low",
                                 reason=sig.error_msg or "VNet signal unavailable",
                                 signals_used=self.required_signals)

        items = sig.items or []
        if not items:
            return ControlResult(status="NotApplicable", severity="High", confidence="High",
                                 reason="No VNets found — no region analysis available.",
                                 signals_used=self.required_signals)

        regions = set(v.get("location", "") for v in items if v.get("location"))
        multi_region = len(regions) > 1

        return ControlResult(
            status="Pass" if multi_region else "Partial",
            severity="High", confidence="Medium",
            reason=f"Resources deployed across {len(regions)} region(s): {', '.join(sorted(regions))}."
                   + ("" if multi_region else " Consider multi-region for resiliency."),
            signals_used=self.required_signals,
        )


register_evaluator(RegionSelectionEvaluator())


# ── Multi-Region Deployment ──────────────────────────────────────
# Checklist: "Deploy your Azure landing zone in a multi-region deployment"
@dataclass
class MultiRegionDeploymentEvaluator:
    control_id: str = "19ca3f89-397d-44b1-b5b6-5e18661372ac"
    required_signals: list[str] = field(
        default_factory=lambda: ["resource_graph:vnets"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        sig = signals["resource_graph:vnets"]
        if sig.status != SignalStatus.OK:
            return ControlResult(status="Error", confidence="Low",
                                 reason=sig.error_msg or "VNet signal unavailable",
                                 signals_used=self.required_signals)

        items = sig.items or []
        regions = set(v.get("location", "") for v in items if v.get("location"))

        if len(regions) <= 1:
            return ControlResult(
                status="Fail", severity="Medium", confidence="High",
                reason=f"Resources in only {len(regions)} region. Multi-region deployment recommended.",
                signals_used=self.required_signals,
            )

        return ControlResult(
            status="Pass", severity="Medium", confidence="High",
            reason=f"Multi-region deployment confirmed: {', '.join(sorted(regions))}.",
            signals_used=self.required_signals,
        )


register_evaluator(MultiRegionDeploymentEvaluator())
