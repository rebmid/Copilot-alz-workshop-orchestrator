"""Azure Billing & Microsoft Entra ID Tenants evaluators — ALZ checklist section.

Evaluates controls from the official 'Azure Billing and Microsoft Entra ID Tenants'
design area using cost management and budget signals.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from signals.types import ControlResult, EvalContext, SignalResult, SignalStatus
from evaluators.registry import register_evaluator


# ── Cost Reporting and Views ─────────────────────────────────────
# Checklist: "Setup Cost Reporting and Views with Azure Cost Management"
@dataclass
class CostReportingEvaluator:
    control_id: str = "32952499-58c8-4e6f-ada5-972e67893d55"
    required_signals: list[str] = field(
        default_factory=lambda: ["cost:management_posture"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        sig = signals["cost:management_posture"]
        if sig.status != SignalStatus.OK:
            return ControlResult(status="Error", confidence="Low",
                                 reason=sig.error_msg or "Cost management signal unavailable",
                                 signals_used=self.required_signals)

        raw = sig.raw or {}
        budget_count = raw.get("budget_count", 0)

        if budget_count == 0:
            return ControlResult(
                status="Fail", severity="Medium", confidence="High",
                reason="No budgets configured. Set up Cost Management reporting and budget views.",
                signals_used=self.required_signals,
            )

        return ControlResult(
            status="Pass", severity="Medium", confidence="High",
            reason=f"{budget_count} budget(s) configured for cost reporting.",
            signals_used=self.required_signals,
        )


register_evaluator(CostReportingEvaluator())


# ── Budget Alerts ────────────────────────────────────────────────
# Checklist: "Assign a budget for each department and account, and establish an alert"
@dataclass
class BudgetAlertsEvaluator:
    control_id: str = "54f0d8b1-22a3-4c0d-8ce2-58b9e086c93a"
    required_signals: list[str] = field(
        default_factory=lambda: ["cost:management_posture"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        sig = signals["cost:management_posture"]
        if sig.status != SignalStatus.OK:
            return ControlResult(status="Error", confidence="Low",
                                 reason=sig.error_msg or "Cost management signal unavailable",
                                 signals_used=self.required_signals)

        raw = sig.raw or {}
        budget_count = raw.get("budget_count", 0)
        alert_count = raw.get("alert_rules", raw.get("budgets_with_alerts", budget_count))

        if budget_count == 0:
            return ControlResult(
                status="Fail", severity="Low", confidence="High",
                reason="No budgets with alerts found. Assign budgets and configure budget alerts.",
                signals_used=self.required_signals,
            )

        if alert_count < budget_count:
            return ControlResult(
                status="Partial", severity="Low", confidence="Medium",
                reason=f"{budget_count} budget(s) found but alert configuration may be incomplete.",
                signals_used=self.required_signals,
            )

        return ControlResult(
            status="Pass", severity="Low", confidence="High",
            reason=f"{budget_count} budget(s) with alerts configured.",
            signals_used=self.required_signals,
        )


register_evaluator(BudgetAlertsEvaluator())


# ── Notification Contact Email ───────────────────────────────────
# Checklist: "Set up a Notification Contact email address to ensure notifications are sent"
@dataclass
class NotificationContactEvaluator:
    control_id: str = "685cb4f2-ac9c-4b19-9167-993ed0b32415"
    required_signals: list[str] = field(
        default_factory=lambda: ["monitor:action_group_coverage"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        sig = signals["monitor:action_group_coverage"]
        if sig.status != SignalStatus.OK:
            return ControlResult(status="Error", confidence="Low",
                                 reason=sig.error_msg or "Action group signal unavailable",
                                 signals_used=self.required_signals)

        raw = sig.raw or {}
        email_receivers = raw.get("email_receivers", raw.get("has_email", 0))

        if not email_receivers:
            return ControlResult(
                status="Fail", severity="Medium", confidence="High",
                reason="No email receivers configured in action groups. Set up notification contacts.",
                signals_used=self.required_signals,
            )

        return ControlResult(
            status="Pass", severity="Medium", confidence="High",
            reason="Notification email receivers configured in action groups.",
            signals_used=self.required_signals,
        )


register_evaluator(NotificationContactEvaluator())
