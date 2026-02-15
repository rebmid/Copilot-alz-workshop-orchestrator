"""Cost evaluators — Cost Management posture."""
from __future__ import annotations

from dataclasses import dataclass, field

from signals.types import SignalResult, SignalStatus, ControlResult, EvalContext, CoveragePayload
from evaluators.registry import register_evaluator


# ── Cost Management Posture ───────────────────────────────────────
@dataclass
class CostManagementEvaluator:
    control_id: str = "cost-management-001"
    required_signals: list[str] = field(
        default_factory=lambda: ["cost:management_posture"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        sig = signals["cost:management_posture"]
        if sig.status != SignalStatus.OK:
            return ControlResult(
                status="Manual", severity="Medium", confidence="Low", confidence_score=0.0,
                reason=sig.error_msg or "Cost Management data not available",
                signals_used=self.required_signals,
            )

        raw = sig.raw or {}
        cov = raw.get("coverage", {})
        applicable = cov.get("applicable", 0)
        compliant = cov.get("compliant", 0)
        ratio = cov.get("ratio", 0.0)

        budget_count = raw.get("budget_count", 0)
        has_notifs = raw.get("has_budget_notifications", False)
        alert_count = raw.get("cost_alert_count", 0)
        has_res = raw.get("has_reservations", False)

        evidence = [{"type": "metric", "resource_id": "",
                     "summary": f"{budget_count} budget(s), notifications={has_notifs}, {alert_count} cost alert(s), reservations={has_res}",
                     "properties": raw}]

        coverage = CoveragePayload(applicable=applicable, compliant=compliant, ratio=ratio)

        issues = []
        if budget_count == 0:
            issues.append("No budgets defined")
        if not has_notifs and budget_count > 0:
            issues.append("Budgets exist but no notification rules configured")
        if alert_count == 0:
            issues.append("No cost anomaly alerts or scheduled actions")

        if not issues:
            status = "Pass"
            reason = f"Cost governance: {budget_count} budget(s) with alerts."
            if has_res:
                reason += " Reservations/savings plans detected."
        elif len(issues) <= 1:
            status = "Partial"
            reason = f"Cost governance: {'; '.join(issues)}."
        else:
            status = "Fail"
            reason = f"Cost governance gaps: {'; '.join(issues)}."

        return ControlResult(
            status=status, severity="Medium", confidence="Medium", confidence_score=0.8,
            reason=reason,
            evidence=evidence, signals_used=self.required_signals, coverage=coverage,
        )


register_evaluator(CostManagementEvaluator())


# ── Cost Forecast Accuracy ────────────────────────────────────────
@dataclass
class CostForecastEvaluator:
    control_id: str = "cost-forecast-001"
    required_signals: list[str] = field(
        default_factory=lambda: ["cost:forecast_accuracy"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        sig = signals["cost:forecast_accuracy"]
        if sig.status != SignalStatus.OK:
            return ControlResult(
                status="Manual", severity="Medium", confidence="Low", confidence_score=0.0,
                reason=sig.error_msg or "Cost forecast data not available",
                signals_used=self.required_signals,
            )

        raw = sig.raw or {}
        cov = raw.get("coverage", {})
        coverage = CoveragePayload(
            applicable=cov.get("applicable", 0),
            compliant=cov.get("compliant", 0),
            ratio=cov.get("ratio", 0.0),
        )

        actual_cost = raw.get("actual_cost_prev_month", 0)
        forecast_cost = raw.get("forecast_cost_prev_month", 0)
        delta_pct = raw.get("delta_pct", 0)
        predictability = raw.get("predictability_metric", 0)

        if actual_cost == 0 and forecast_cost == 0:
            return ControlResult(
                status="NotApplicable", severity="Info", confidence="Medium", confidence_score=0.5,
                reason="No cost data available for the previous month.",
                signals_used=self.required_signals, coverage=coverage,
            )

        evidence = [{"type": "metric", "resource_id": "",
                     "summary": f"Actual: ${actual_cost:,.0f}, Forecast: ${forecast_cost:,.0f}, "
                                f"Delta: {delta_pct:.1f}%, Predictability: {predictability:.2f}",
                     "properties": raw}]

        if predictability >= 0.9:
            return ControlResult(
                status="Pass", severity="Medium", confidence="Medium", confidence_score=0.8,
                reason=f"Cost predictability: {predictability:.0%} (delta {delta_pct:.1f}%).",
                evidence=evidence, signals_used=self.required_signals, coverage=coverage,
            )
        if predictability >= 0.7:
            return ControlResult(
                status="Partial", severity="Medium", confidence="Medium", confidence_score=0.7,
                reason=f"Cost predictability: {predictability:.0%} — forecast diverged {delta_pct:.1f}% from actual.",
                evidence=evidence, signals_used=self.required_signals, coverage=coverage,
            )
        return ControlResult(
            status="Fail", severity="Medium", confidence="Medium", confidence_score=0.7,
            reason=f"Cost predictability low: {predictability:.0%} — forecast diverged {delta_pct:.1f}% from actual.",
            evidence=evidence, signals_used=self.required_signals, coverage=coverage,
        )


register_evaluator(CostForecastEvaluator())


# ── Idle Resource Detection ───────────────────────────────────────
@dataclass
class IdleResourcesEvaluator:
    control_id: str = "idle-resources-001"
    required_signals: list[str] = field(
        default_factory=lambda: ["cost:idle_resources"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        sig = signals["cost:idle_resources"]
        if sig.status != SignalStatus.OK:
            return ControlResult(
                status="Manual", severity="Medium", confidence="Low", confidence_score=0.0,
                reason=sig.error_msg or "Idle resource data not available",
                signals_used=self.required_signals,
            )

        raw = sig.raw or {}
        cov = raw.get("coverage", {})
        coverage = CoveragePayload(
            applicable=cov.get("applicable", 0),
            compliant=cov.get("compliant", 0),
            ratio=cov.get("ratio", 0.0),
        )

        idle_vm_count = raw.get("idle_vm_count", 0)
        total_vms = raw.get("total_vms", 0)
        estimated_annual_savings = raw.get("estimated_annual_savings", 0)

        if total_vms == 0:
            return ControlResult(
                status="NotApplicable", severity="Info", confidence="Medium", confidence_score=0.5,
                reason="No VMs found in scope — idle resource check N/A.",
                signals_used=self.required_signals, coverage=coverage,
            )

        evidence = [{"type": "metric", "resource_id": "",
                     "summary": f"{idle_vm_count}/{total_vms} idle VM(s), est. savings: ${estimated_annual_savings:,.0f}/yr",
                     "properties": raw}]

        if idle_vm_count == 0:
            return ControlResult(
                status="Pass", severity="Medium", confidence="Medium", confidence_score=0.8,
                reason=f"No idle VMs detected among {total_vms} VM(s).",
                evidence=evidence, signals_used=self.required_signals, coverage=coverage,
            )
        idle_ratio = idle_vm_count / total_vms if total_vms > 0 else 0
        if idle_ratio <= 0.1:
            return ControlResult(
                status="Partial", severity="Medium", confidence="Medium", confidence_score=0.7,
                reason=f"{idle_vm_count} idle VM(s) ({idle_ratio*100:.0f}%), est. savings: ${estimated_annual_savings:,.0f}/yr.",
                evidence=evidence, signals_used=self.required_signals, coverage=coverage,
            )
        return ControlResult(
            status="Fail", severity="Medium", confidence="Medium", confidence_score=0.7,
            reason=f"{idle_vm_count} idle VM(s) ({idle_ratio*100:.0f}%), est. savings: ${estimated_annual_savings:,.0f}/yr.",
            evidence=evidence, signals_used=self.required_signals, coverage=coverage,
        )


register_evaluator(IdleResourcesEvaluator())
