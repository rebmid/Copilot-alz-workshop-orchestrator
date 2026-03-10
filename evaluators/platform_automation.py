"""Platform Automation & DevOps evaluators — ALZ checklist section.

Evaluates controls from the official 'Platform Automation and DevOps'
design area using activity log analysis and Key Vault signals.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from signals.types import ControlResult, EvalContext, SignalResult, SignalStatus
from evaluators.registry import register_evaluator


# ── Key Vault for Secrets ────────────────────────────────────────
# Checklist: "Use Key Vault secrets to avoid hard-coding sensitive information"
@dataclass
class KeyVaultSecretsEvaluator:
    control_id: str = "108d5099-a11d-4445-bd8b-e12a5e95412e"
    required_signals: list[str] = field(
        default_factory=lambda: ["resource_graph:keyvault_posture"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        sig = signals["resource_graph:keyvault_posture"]
        if sig.status != SignalStatus.OK:
            return ControlResult(status="Error", confidence="Low",
                                 reason=sig.error_msg or "Key Vault signal unavailable",
                                 signals_used=self.required_signals)

        items = sig.items or []
        if not items:
            return ControlResult(
                status="Fail", severity="High", confidence="High",
                reason="No Key Vaults detected. Use Key Vault to store secrets, keys, and certificates.",
                signals_used=self.required_signals,
            )

        return ControlResult(
            status="Pass", severity="High", confidence="High",
            reason=f"{len(items)} Key Vault(s) detected for secrets management.",
            signals_used=self.required_signals,
        )


register_evaluator(KeyVaultSecretsEvaluator())


# ── IaC Maturity ─────────────────────────────────────────────────
# Checklist: "Leverage Declarative Infrastructure as Code Tools such as Azure Bicep, ARM Templates or Terraform"
@dataclass
class IaCMaturityEvaluator:
    control_id: str = "2cdc9d99-dbcc-4ad4-97f5-e7d358bdfa73"
    required_signals: list[str] = field(
        default_factory=lambda: ["monitor:activity_log_analysis"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        sig = signals["monitor:activity_log_analysis"]
        if sig.status != SignalStatus.OK:
            return ControlResult(status="Error", confidence="Low",
                                 reason=sig.error_msg or "Activity log signal unavailable",
                                 signals_used=self.required_signals)

        raw = sig.raw or {}
        iac_ratio = raw.get("iac_ratio", raw.get("template_deployment_ratio", 0))
        write_count = raw.get("write_operations", raw.get("total_writes", 0))

        if write_count == 0:
            return ControlResult(
                status="NotApplicable", severity="High", confidence="Medium",
                reason="No write operations found in activity log.",
                signals_used=self.required_signals,
            )

        if iac_ratio < 20:
            return ControlResult(
                status="Fail", severity="High", confidence="Medium",
                reason=f"IaC ratio is {iac_ratio}% of deployments. Adopt ARM/Bicep/Terraform for ≥ 50%.",
                signals_used=self.required_signals,
            )

        if iac_ratio < 50:
            return ControlResult(
                status="Partial", severity="High", confidence="Medium",
                reason=f"IaC ratio is {iac_ratio}%. Target ≥ 50% declarative deployments.",
                signals_used=self.required_signals,
            )

        return ControlResult(
            status="Pass", severity="High", confidence="Medium",
            reason=f"IaC ratio is {iac_ratio}% — declarative infrastructure as code adopted.",
            signals_used=self.required_signals,
        )


register_evaluator(IaCMaturityEvaluator())


# ── DevSecOps Integration ────────────────────────────────────────
# Checklist: "Integrate security into the already combined process of development and operations"
@dataclass
class DevSecOpsEvaluator:
    control_id: str = "cc87a3bc-c572-4ad2-92ed-8cabab66160f"
    required_signals: list[str] = field(
        default_factory=lambda: ["defender:pricings", "resource_graph:keyvault_posture"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        defender = signals["defender:pricings"]
        kv = signals["resource_graph:keyvault_posture"]

        if defender.status != SignalStatus.OK:
            return ControlResult(status="Error", confidence="Low",
                                 reason=defender.error_msg or "Defender signal unavailable",
                                 signals_used=self.required_signals)

        raw = defender.raw or {}
        plans_enabled = raw.get("plans_enabled", 0)
        plans_total = raw.get("plans_total", 0)
        kv_count = len(kv.items or []) if kv.status == SignalStatus.OK else 0

        issues = []
        if plans_enabled < 5:
            issues.append(f"Only {plans_enabled}/{plans_total} Defender plans enabled")
        if kv_count == 0:
            issues.append("No Key Vaults for secrets management")

        if len(issues) >= 2:
            return ControlResult(
                status="Fail", severity="High", confidence="Medium",
                reason=f"DevSecOps gaps: {'; '.join(issues)}.",
                signals_used=self.required_signals,
            )

        if issues:
            return ControlResult(
                status="Partial", severity="High", confidence="Medium",
                reason=f"Partial DevSecOps: {'; '.join(issues)}.",
                signals_used=self.required_signals,
            )

        return ControlResult(
            status="Pass", severity="High", confidence="Medium",
            reason=f"DevSecOps indicators present: {plans_enabled} Defender plans, {kv_count} Key Vaults.",
            signals_used=self.required_signals,
        )


register_evaluator(DevSecOpsEvaluator())
