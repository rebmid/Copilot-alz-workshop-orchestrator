# evaluators/identity.py — RBAC hygiene, Entra ID logs, PIM evaluators
"""
Identity evaluators: RBAC hygiene, Entra log availability, PIM usage.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from signals.types import SignalResult, SignalStatus, ControlResult, EvalContext, CoveragePayload
from evaluators.registry import register_evaluator


@dataclass
class RBACHygieneEvaluator:
    control_id: str = "rbac-hygiene-001"
    required_signals: list[str] = field(
        default_factory=lambda: ["identity:rbac_hygiene"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        sig = signals["identity:rbac_hygiene"]
        if sig.status != SignalStatus.OK:
            return ControlResult(
                status="Manual", severity="High", confidence="Low", confidence_score=0.0,
                reason=sig.error_msg or "RBAC data not available",
                signals_used=self.required_signals,
            )

        raw = sig.raw or {}
        cov = raw.get("coverage", {})
        applicable = cov.get("applicable", 0)
        compliant = cov.get("compliant", 0)
        ratio = cov.get("ratio", 0.0)
        owner_count = raw.get("owner_count", 0)
        total = raw.get("total_assignments", 0)
        group_ratio = raw.get("group_assignment_ratio", 0.0)
        by_type = raw.get("by_principal_type", {})

        issues = []
        evidence = []

        # Owner sprawl
        evidence.append({"type": "metric", "resource_id": "",
                         "summary": f"{owner_count} owner(s), {total} total assignments",
                         "properties": raw})

        if owner_count > 5:
            issues.append(f"{owner_count} Owner role assignments (recommend ≤ 5)")
        if group_ratio < 0.5:
            issues.append(f"Group-based: {group_ratio*100:.0f}% (recommend ≥ 50%)")

        coverage = CoveragePayload(applicable=applicable, compliant=compliant, ratio=ratio)

        if not issues:
            return ControlResult(
                status="Pass", severity="High", confidence="High", confidence_score=0.9,
                reason=f"RBAC hygiene: {owner_count} owners, {group_ratio*100:.0f}% group-based.",
                evidence=evidence, signals_used=self.required_signals, coverage=coverage,
            )
        if len(issues) == 1:
            return ControlResult(
                status="Partial", severity="High", confidence="High", confidence_score=0.9,
                reason=f"RBAC hygiene: {'; '.join(issues)}.",
                evidence=evidence, signals_used=self.required_signals, coverage=coverage,
            )
        return ControlResult(
            status="Fail", severity="High", confidence="High", confidence_score=0.9,
            reason=f"RBAC hygiene issues: {'; '.join(issues)}.",
            evidence=evidence, signals_used=self.required_signals, coverage=coverage,
        )


register_evaluator(RBACHygieneEvaluator())


# ── Entra ID Log Availability ────────────────────────────────────
@dataclass
class EntraLogAvailabilityEvaluator:
    control_id: str = "entra-log-availability-001"
    required_signals: list[str] = field(
        default_factory=lambda: ["identity:entra_log_availability"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        sig = signals["identity:entra_log_availability"]
        if sig.status != SignalStatus.OK:
            return ControlResult(
                status="Manual", severity="High", confidence="Low", confidence_score=0.0,
                reason=sig.error_msg or "Entra ID log availability data not accessible",
                signals_used=self.required_signals,
            )

        raw = sig.raw or {}
        cov = raw.get("coverage", {})
        applicable = cov.get("applicable", 0)
        compliant = cov.get("compliant", 0)
        ratio = cov.get("ratio", 0.0)

        sign_in = raw.get("sign_in_logs", False)
        audit = raw.get("audit_logs", False)
        sp_logs = raw.get("sp_sign_in_logs", False)

        evidence = [{"type": "metric", "resource_id": "",
                     "summary": f"Sign-in logs: {sign_in}, Audit logs: {audit}, SP sign-in: {sp_logs}",
                     "properties": raw}]

        coverage = CoveragePayload(applicable=applicable, compliant=compliant, ratio=ratio)

        issues = []
        if not sign_in:
            issues.append("Sign-in logs not forwarded to Log Analytics")
        if not audit:
            issues.append("Audit logs not forwarded to Log Analytics")
        if not sp_logs:
            issues.append("Service principal sign-in logs not forwarded")

        if not issues:
            return ControlResult(
                status="Pass", severity="High", confidence="High", confidence_score=0.9,
                reason="All Entra ID log categories forwarded to Log Analytics.",
                evidence=evidence, signals_used=self.required_signals, coverage=coverage,
            )
        if compliant > 0:
            return ControlResult(
                status="Partial", severity="High", confidence="High", confidence_score=0.9,
                reason=f"Entra ID log gaps: {'; '.join(issues)}.",
                evidence=evidence, signals_used=self.required_signals, coverage=coverage,
            )
        return ControlResult(
            status="Fail", severity="High", confidence="High", confidence_score=0.9,
            reason=f"Entra ID logs not forwarded: {'; '.join(issues)}.",
            evidence=evidence, signals_used=self.required_signals, coverage=coverage,
        )


register_evaluator(EntraLogAvailabilityEvaluator())


# ── PIM Usage ─────────────────────────────────────────────────────
@dataclass
class PIMUsageEvaluator:
    control_id: str = "pim-usage-001"
    required_signals: list[str] = field(
        default_factory=lambda: ["identity:pim_usage"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        sig = signals["identity:pim_usage"]
        if sig.status != SignalStatus.OK:
            return ControlResult(
                status="Manual", severity="Medium", confidence="Low", confidence_score=0.0,
                reason=sig.error_msg or "PIM usage data not available",
                signals_used=self.required_signals,
            )

        raw = sig.raw or {}
        cov = raw.get("coverage", {})
        applicable = cov.get("applicable", 0)
        compliant = cov.get("compliant", 0)
        ratio = cov.get("ratio", 0.0)

        eligibility_count = raw.get("pim_eligibility_activations", 0)
        has_break_glass = raw.get("break_glass_elevations", 0) > 0

        evidence = [{"type": "metric", "resource_id": "",
                     "summary": f"PIM activations: {eligibility_count}, break-glass detected: {has_break_glass}",
                     "properties": raw}]

        coverage = CoveragePayload(applicable=applicable, compliant=compliant, ratio=ratio)

        if eligibility_count > 0:
            reason = f"PIM active: {eligibility_count} role activation(s) detected."
            if has_break_glass:
                reason += " Break-glass elevation events also detected."
            return ControlResult(
                status="Pass", severity="Medium", confidence="Medium", confidence_score=0.7,
                reason=reason,
                evidence=evidence, signals_used=self.required_signals, coverage=coverage,
            )

        return ControlResult(
            status="Partial", severity="Medium", confidence="Low", confidence_score=0.5,
            reason="No PIM eligibility activations detected in activity log (90d). "
                   "PIM may not be enabled or may require Entra P2 license.",
            evidence=evidence, signals_used=self.required_signals, coverage=coverage,
            next_checks=[{
                "signal": "identity:entra_log_availability",
                "why": "Verify Entra ID logs are flowing to confirm PIM status",
            }],
        )


register_evaluator(PIMUsageEvaluator())


# ── PIM Maturity (Graph-based) ────────────────────────────────────
@dataclass
class PIMMaturityEvaluator:
    control_id: str = "pim-maturity-001"
    required_signals: list[str] = field(
        default_factory=lambda: ["identity:pim_maturity"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        sig = signals["identity:pim_maturity"]
        if sig.status != SignalStatus.OK:
            return ControlResult(
                status="Manual", severity="High", confidence="Low", confidence_score=0.0,
                reason=sig.error_msg or "PIM maturity data not available (Graph API access required)",
                signals_used=self.required_signals,
            )

        raw = sig.raw or {}
        cov = raw.get("coverage", {})
        coverage = CoveragePayload(
            applicable=cov.get("applicable", 0),
            compliant=cov.get("compliant", 0),
            ratio=cov.get("ratio", 0.0),
        )

        eligible_ratio = raw.get("eligible_ratio", 0.0)
        total_privileged = raw.get("total_privileged_assignments", 0)
        standing_admin = raw.get("standing_admin_count", 0)

        evidence = [{"type": "metric", "resource_id": "",
                     "summary": f"Eligible ratio: {eligible_ratio*100:.0f}%, "
                                f"{total_privileged} privileged assignment(s), "
                                f"{standing_admin} standing admin(s)",
                     "properties": raw}]

        issues = []
        if eligible_ratio < 0.8:
            issues.append(f"Eligible ratio {eligible_ratio*100:.0f}% (recommend ≥ 80%)")
        if standing_admin > 0:
            issues.append(f"{standing_admin} standing admin assignment(s) (recommend 0)")

        if not issues:
            return ControlResult(
                status="Pass", severity="High", confidence="High", confidence_score=0.9,
                reason=f"PIM maturity: {eligible_ratio*100:.0f}% eligible, zero standing admins.",
                evidence=evidence, signals_used=self.required_signals, coverage=coverage,
            )
        if eligible_ratio > 0:
            return ControlResult(
                status="Partial", severity="High", confidence="High", confidence_score=0.9,
                reason=f"PIM gaps: {'; '.join(issues)}.",
                evidence=evidence, signals_used=self.required_signals, coverage=coverage,
            )
        return ControlResult(
            status="Fail", severity="High", confidence="High", confidence_score=0.9,
            reason=f"PIM not effective: {'; '.join(issues)}.",
            evidence=evidence, signals_used=self.required_signals, coverage=coverage,
        )


register_evaluator(PIMMaturityEvaluator())


# ── Break-Glass Account Validation ───────────────────────────────
@dataclass
class BreakglassValidationEvaluator:
    control_id: str = "breakglass-validation-001"
    required_signals: list[str] = field(
        default_factory=lambda: ["identity:breakglass_validation"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        sig = signals["identity:breakglass_validation"]
        if sig.status != SignalStatus.OK:
            return ControlResult(
                status="Manual", severity="High", confidence="Low", confidence_score=0.0,
                reason=sig.error_msg or "Break-glass validation data not available",
                signals_used=self.required_signals,
            )

        raw = sig.raw or {}
        cov = raw.get("coverage", {})
        coverage = CoveragePayload(
            applicable=cov.get("applicable", 0),
            compliant=cov.get("compliant", 0),
            ratio=cov.get("ratio", 0.0),
        )

        bg_count = raw.get("breakglass_accounts_found", 0)
        ca_excluded = raw.get("ca_policy_excluded", False)
        recently_tested = raw.get("recently_tested", False)

        evidence = [{"type": "metric", "resource_id": "",
                     "summary": f"{bg_count} break-glass account(s), CA excluded={ca_excluded}, recently tested={recently_tested}",
                     "properties": raw}]

        if bg_count == 0:
            return ControlResult(
                status="Fail", severity="High", confidence="Medium", confidence_score=0.7,
                reason="No break-glass accounts detected (naming pattern: breakglass*, emergency*, bg-*).",
                evidence=evidence, signals_used=self.required_signals, coverage=coverage,
                next_checks=[{
                    "signal": "identity:breakglass_validation",
                    "why": "Verify naming convention or document alternative emergency access",
                }],
            )

        issues = []
        if not ca_excluded:
            issues.append("Break-glass account(s) not excluded from Conditional Access policies")
        if not recently_tested:
            issues.append("No sign-in activity in last 90 days (recommend periodic testing)")

        if not issues:
            return ControlResult(
                status="Pass", severity="High", confidence="High", confidence_score=0.9,
                reason=f"{bg_count} break-glass account(s): CA excluded, recently tested.",
                evidence=evidence, signals_used=self.required_signals, coverage=coverage,
            )
        return ControlResult(
            status="Partial", severity="High", confidence="High", confidence_score=0.85,
            reason=f"Break-glass gaps: {'; '.join(issues)}.",
            evidence=evidence, signals_used=self.required_signals, coverage=coverage,
        )


register_evaluator(BreakglassValidationEvaluator())


# ── Service Principal Owner Risk ─────────────────────────────────
@dataclass
class SPOwnerRiskEvaluator:
    control_id: str = "sp-owner-risk-001"
    required_signals: list[str] = field(
        default_factory=lambda: ["identity:sp_owner_risk"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        sig = signals["identity:sp_owner_risk"]
        if sig.status != SignalStatus.OK:
            return ControlResult(
                status="Manual", severity="High", confidence="Low", confidence_score=0.0,
                reason=sig.error_msg or "Service principal role data not available",
                signals_used=self.required_signals,
            )

        raw = sig.raw or {}
        cov = raw.get("coverage", {})
        coverage = CoveragePayload(
            applicable=cov.get("applicable", 0),
            compliant=cov.get("compliant", 0),
            ratio=cov.get("ratio", 0.0),
        )

        sp_owner_count = raw.get("sp_owner_count", 0)
        sp_uaa_count = raw.get("sp_uaa_count", 0)

        evidence = [{"type": "metric", "resource_id": "",
                     "summary": f"{sp_owner_count} SP Owner(s), {sp_uaa_count} SP User Access Admin(s)",
                     "properties": raw}]

        issues = []
        if sp_owner_count > 0:
            issues.append(f"{sp_owner_count} service principal(s) with Owner role")
        if sp_uaa_count > 0:
            issues.append(f"{sp_uaa_count} service principal(s) with User Access Administrator")

        if not issues:
            return ControlResult(
                status="Pass", severity="High", confidence="High", confidence_score=0.9,
                reason="No service principals hold Owner or User Access Administrator roles.",
                evidence=evidence, signals_used=self.required_signals, coverage=coverage,
            )
        return ControlResult(
            status="Fail", severity="High", confidence="High", confidence_score=0.9,
            reason=f"SP privilege risk: {'; '.join(issues)}.",
            evidence=evidence, signals_used=self.required_signals, coverage=coverage,
        )


register_evaluator(SPOwnerRiskEvaluator())


# ── Admin Conditional Access Coverage ─────────────────────────────
@dataclass
class AdminCACoverageEvaluator:
    control_id: str = "admin-ca-coverage-001"
    required_signals: list[str] = field(
        default_factory=lambda: ["identity:admin_ca_coverage"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        sig = signals["identity:admin_ca_coverage"]
        if sig.status != SignalStatus.OK:
            return ControlResult(
                status="Manual", severity="High", confidence="Low", confidence_score=0.0,
                reason=sig.error_msg or "Admin CA coverage data not available (Graph API access required)",
                signals_used=self.required_signals,
            )

        raw = sig.raw or {}
        cov = raw.get("coverage", {})
        coverage = CoveragePayload(
            applicable=cov.get("applicable", 0),
            compliant=cov.get("compliant", 0),
            ratio=cov.get("ratio", 0.0),
        )

        admin_count = raw.get("admin_user_count", 0)
        ca_coverage_ratio = raw.get("ca_coverage_ratio", 0.0)
        mfa_policies = raw.get("mfa_policy_count", 0)

        evidence = [{"type": "metric", "resource_id": "",
                     "summary": f"{admin_count} admin(s), CA coverage: {ca_coverage_ratio*100:.0f}%, {mfa_policies} MFA policy(ies)",
                     "properties": raw}]

        if admin_count == 0:
            return ControlResult(
                status="NotApplicable", severity="Info", confidence="Medium", confidence_score=0.5,
                reason="No admin directory role members found.",
                signals_used=self.required_signals, coverage=coverage,
            )

        issues = []
        if mfa_policies == 0:
            issues.append("No CA policies requiring MFA for admin roles")
        if ca_coverage_ratio < 0.9:
            issues.append(f"CA coverage {ca_coverage_ratio*100:.0f}% (recommend ≥ 90%)")

        if not issues:
            return ControlResult(
                status="Pass", severity="High", confidence="High", confidence_score=0.9,
                reason=f"Admin CA coverage: {ca_coverage_ratio*100:.0f}% of {admin_count} admin(s) protected by MFA policies.",
                evidence=evidence, signals_used=self.required_signals, coverage=coverage,
            )
        if mfa_policies > 0:
            return ControlResult(
                status="Partial", severity="High", confidence="High", confidence_score=0.85,
                reason=f"Admin CA gaps: {'; '.join(issues)}.",
                evidence=evidence, signals_used=self.required_signals, coverage=coverage,
            )
        return ControlResult(
            status="Fail", severity="High", confidence="High", confidence_score=0.9,
            reason=f"Admin CA coverage missing: {'; '.join(issues)}.",
            evidence=evidence, signals_used=self.required_signals, coverage=coverage,
        )


register_evaluator(AdminCACoverageEvaluator())
