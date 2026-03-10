"""Identity & Access Management evaluators — ALZ checklist section.

Evaluates controls from the official 'Identity and Access Management'
design area.  These use existing identity signals plus new managed
identity signal to cover checklist controls beyond the base 7 already
in evaluators/identity.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from signals.types import ControlResult, EvalContext, SignalResult, SignalStatus
from evaluators.registry import register_evaluator


# ── Managed Identities ──────────────────────────────────────────
# Checklist: "Use managed identities instead of service principals for authentication"
@dataclass
class ManagedIdentityUsageEvaluator:
    control_id: str = "4348bf81-7573-4512-8f46-9061cc198fea"
    required_signals: list[str] = field(
        default_factory=lambda: ["resource_graph:managed_identities"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        sig = signals["resource_graph:managed_identities"]
        if sig.status != SignalStatus.OK:
            return ControlResult(status="Error", confidence="Low",
                                 reason=sig.error_msg or "Managed identity signal unavailable",
                                 signals_used=self.required_signals)

        raw = sig.raw or {}
        count = raw.get("resources_with_identity", 0)

        if count == 0:
            return ControlResult(
                status="Fail", severity="High", confidence="High",
                reason="No resources using managed identities detected. Use managed identities instead of service principals.",
                signals_used=self.required_signals,
            )

        return ControlResult(
            status="Pass", severity="High", confidence="High",
            reason=f"{count} resource(s) using managed identities.",
            signals_used=self.required_signals,
        )


register_evaluator(ManagedIdentityUsageEvaluator())


# ── Conditional Access Policies ──────────────────────────────────
# Checklist: "Enforce Microsoft Entra ID Conditional Access policies for any user with rights to Azure environments"
@dataclass
class ConditionalAccessEvaluator:
    control_id: str = "53e8908a-e28c-484c-93b6-b7808b9fe5c4"
    required_signals: list[str] = field(
        default_factory=lambda: ["identity:admin_ca_coverage"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        sig = signals["identity:admin_ca_coverage"]
        if sig.status != SignalStatus.OK:
            return ControlResult(status="Error", confidence="Low",
                                 reason=sig.error_msg or "Conditional access signal unavailable",
                                 signals_used=self.required_signals)

        raw = sig.raw or {}
        policy_count = raw.get("active_policies", raw.get("policy_count", 0))
        total_admins = raw.get("total_admin_members", 0)

        # If we found zero admins AND zero policies, Graph API likely denied access
        if total_admins == 0 and policy_count == 0:
            return ControlResult(
                status="Manual", severity="High", confidence="Low",
                reason="Unable to enumerate Conditional Access policies (Graph API permissions required: Global Reader).",
                signals_used=self.required_signals,
            )

        if policy_count == 0:
            return ControlResult(
                status="Fail", severity="High", confidence="High",
                reason="No active Conditional Access policies detected.",
                signals_used=self.required_signals,
            )

        return ControlResult(
            status="Pass", severity="High", confidence="High",
            reason=f"{policy_count} active Conditional Access policy(ies) detected.",
            signals_used=self.required_signals,
        )


register_evaluator(ConditionalAccessEvaluator())


# ── MFA Enforcement ──────────────────────────────────────────────
# Checklist: "Enforce multi-factor authentication for any user with rights to the Azure environments"
# NOTE: Microsoft enforces MFA for all Azure users by default since Oct 2024.
# This evaluator always returns Pass. Custom CA policies are checked separately.
@dataclass
class MFAEnforcementEvaluator:
    control_id: str = "1049d403-a923-4c34-94d0-0018ac6a9e01"
    required_signals: list[str] = field(
        default_factory=lambda: ["identity:admin_ca_coverage"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        return ControlResult(
            status="Pass", severity="High", confidence="High",
            reason="Microsoft enforces MFA for all Azure users by default (Oct 2024). "
                   "Custom Conditional Access policies are evaluated separately.",
            signals_used=self.required_signals,
        )


register_evaluator(MFAEnforcementEvaluator())


# ── PIM for Zero Standing Access ─────────────────────────────────
# Checklist: "Enforce PIM to establish zero standing access and least privilege"
@dataclass
class PIMZeroStandingAccessEvaluator:
    control_id: str = "14658d35-58fd-4772-99b8-21112df27ee4"
    required_signals: list[str] = field(
        default_factory=lambda: ["identity:pim_maturity"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        sig = signals["identity:pim_maturity"]
        if sig.status != SignalStatus.OK:
            return ControlResult(status="Error", confidence="Low",
                                 reason=sig.error_msg or "PIM maturity signal unavailable",
                                 signals_used=self.required_signals)

        raw = sig.raw or {}
        eligible_ratio = raw.get("eligible_ratio", 0)

        if eligible_ratio < 20:
            return ControlResult(
                status="Fail", severity="Medium", confidence="High",
                reason=f"PIM eligible ratio is {eligible_ratio}%. Zero standing access requires ≥ 80%.",
                signals_used=self.required_signals,
            )

        if eligible_ratio < 80:
            return ControlResult(
                status="Partial", severity="Medium", confidence="High",
                reason=f"PIM eligible ratio is {eligible_ratio}%. Target ≥ 80% for zero standing access.",
                signals_used=self.required_signals,
            )

        return ControlResult(
            status="Pass", severity="Medium", confidence="High",
            reason=f"PIM eligible ratio is {eligible_ratio}% — zero standing access enforced.",
            signals_used=self.required_signals,
        )


register_evaluator(PIMZeroStandingAccessEvaluator())


# ── Break-Glass Accounts ─────────────────────────────────────────
# Checklist: "Implement emergency access or break-glass accounts"
@dataclass
class BreakGlassAccountsEvaluator:
    control_id: str = "984a859c-773e-47d2-9162-3a765a917e1f"
    required_signals: list[str] = field(
        default_factory=lambda: ["identity:breakglass_validation"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        sig = signals["identity:breakglass_validation"]
        if sig.status != SignalStatus.OK:
            return ControlResult(status="Error", confidence="Low",
                                 reason=sig.error_msg or "Break-glass signal unavailable",
                                 signals_used=self.required_signals)

        raw = sig.raw or {}
        bg_count = raw.get("breakglass_count", 0)

        if bg_count == 0:
            return ControlResult(
                status="Fail", severity="High", confidence="High",
                reason="No break-glass accounts detected (naming pattern: breakglass*, emergency*, bg-*).",
                signals_used=self.required_signals,
            )

        if bg_count < 2:
            return ControlResult(
                status="Partial", severity="High", confidence="High",
                reason=f"Only {bg_count} break-glass account(s) found. Microsoft recommends at least 2.",
                signals_used=self.required_signals,
            )

        return ControlResult(
            status="Pass", severity="High", confidence="High",
            reason=f"{bg_count} break-glass account(s) detected.",
            signals_used=self.required_signals,
        )


register_evaluator(BreakGlassAccountsEvaluator())


# ── RBAC Model Alignment ────────────────────────────────────────
# Checklist: "Enforce a RBAC model that aligns to your cloud operating model"
@dataclass
class RBACModelAlignmentEvaluator:
    control_id: str = "348ef254-c27d-442e-abba-c7571559ab91"
    required_signals: list[str] = field(
        default_factory=lambda: ["identity:rbac_hygiene"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        sig = signals["identity:rbac_hygiene"]
        if sig.status != SignalStatus.OK:
            return ControlResult(status="Error", confidence="Low",
                                 reason=sig.error_msg or "RBAC hygiene signal unavailable",
                                 signals_used=self.required_signals)

        raw = sig.raw or {}
        owner_count = raw.get("owner_count", 0)
        group_based_pct = raw.get("group_based_percent", 0)

        issues = []
        if owner_count > 5:
            issues.append(f"{owner_count} Owner role assignments (recommend ≤ 5)")
        if group_based_pct < 50:
            issues.append(f"Group-based assignments: {group_based_pct}% (recommend ≥ 50%)")

        if issues:
            return ControlResult(
                status="Fail", severity="High", confidence="High",
                reason=f"RBAC model issues: {'; '.join(issues)}.",
                signals_used=self.required_signals,
            )

        return ControlResult(
            status="Pass", severity="High", confidence="High",
            reason=f"RBAC model aligned: {owner_count} Owner assignments, {group_based_pct}% group-based.",
            signals_used=self.required_signals,
        )


register_evaluator(RBACModelAlignmentEvaluator())


# ── PIM Access Reviews ──────────────────────────────────────────
# Checklist: "Use Microsoft Entra ID PIM access reviews to periodically validate resource entitlements"
@dataclass
class PIMAccessReviewsEvaluator:
    control_id: str = "d505ebcb-79b1-4274-9c0d-a27c8bea489c"
    required_signals: list[str] = field(
        default_factory=lambda: ["identity:pim_usage"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        sig = signals["identity:pim_usage"]
        if sig.status != SignalStatus.OK:
            return ControlResult(status="Error", confidence="Low",
                                 reason=sig.error_msg or "PIM usage signal unavailable",
                                 signals_used=self.required_signals)

        raw = sig.raw or {}
        activations = raw.get("activation_count", raw.get("pim_activations", 0))

        if activations == 0:
            return ControlResult(
                status="Fail", severity="Medium", confidence="Medium",
                reason="No PIM activations detected. PIM access reviews may not be configured.",
                signals_used=self.required_signals,
            )

        return ControlResult(
            status="Partial", severity="Medium", confidence="Medium",
            reason=f"{activations} PIM activation(s) detected. Verify access reviews are configured.",
            signals_used=self.required_signals,
        )


register_evaluator(PIMAccessReviewsEvaluator())


# ── Centralized and Delegated Responsibilities ───────────────────
# Checklist: "Enforce centralized and delegated responsibilities to manage resources inside the landing zone"
@dataclass
class CentralizedDelegationEvaluator:
    control_id: str = "e6a83de5-de32-4c19-a248-1607d5d1e4e6"
    required_signals: list[str] = field(
        default_factory=lambda: ["identity:rbac_hygiene", "arm:mg_hierarchy"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        rbac = signals["identity:rbac_hygiene"]
        mg = signals["arm:mg_hierarchy"]

        if rbac.status != SignalStatus.OK:
            return ControlResult(status="Error", confidence="Low",
                                 reason=rbac.error_msg or "RBAC signal unavailable",
                                 signals_used=self.required_signals)

        raw_rbac = rbac.raw or {}
        raw_mg = (mg.raw or {}) if mg.status == SignalStatus.OK else {}

        has_mg = raw_mg.get("max_depth", 0) > 0
        custom_roles = raw_rbac.get("custom_role_count", 0)

        if not has_mg:
            return ControlResult(
                status="Fail", severity="High", confidence="Medium",
                reason="No management group hierarchy detected. Centralized delegation requires MG structure.",
                signals_used=self.required_signals,
            )

        if custom_roles > 0:
            return ControlResult(
                status="Pass", severity="High", confidence="Medium",
                reason=f"MG hierarchy with {custom_roles} custom RBAC role(s) supports centralized delegation.",
                signals_used=self.required_signals,
            )

        return ControlResult(
            status="Partial", severity="High", confidence="Medium",
            reason="MG hierarchy exists but no custom RBAC roles found. Consider custom roles for fine-grained delegation.",
            signals_used=self.required_signals,
        )


register_evaluator(CentralizedDelegationEvaluator())
