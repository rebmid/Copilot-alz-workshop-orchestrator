"""Management evaluators — Workspace topology, Activity Log automation, Update Manager."""
from __future__ import annotations

from dataclasses import dataclass, field

from signals.types import SignalResult, SignalStatus, ControlResult, EvalContext, CoveragePayload
from evaluators.registry import register_evaluator


# ── SOC Workspace Topology ────────────────────────────────────────
@dataclass
class WorkspaceTopologyEvaluator:
    control_id: str = "monitor-workspace-topology-001"
    required_signals: list[str] = field(
        default_factory=lambda: ["monitor:workspace_topology"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        sig = signals["monitor:workspace_topology"]
        if sig.status != SignalStatus.OK:
            return ControlResult(
                status="Manual", severity="High", confidence="Low", confidence_score=0.0,
                reason=sig.error_msg or "Workspace topology data not available",
                signals_used=self.required_signals,
            )

        raw = sig.raw or {}
        cov = raw.get("coverage", {})
        applicable = cov.get("applicable", 0)
        compliant = cov.get("compliant", 0)
        ratio = cov.get("ratio", 0.0)

        ws_count = raw.get("workspace_count", 0)
        is_central = raw.get("is_centralized", False)
        sentinel = raw.get("sentinel_enabled", False)
        retention = raw.get("max_retention_days", 0)

        if ws_count == 0:
            return ControlResult(
                status="Fail", severity="High", confidence="High", confidence_score=0.9,
                reason="No Log Analytics workspaces found in subscription.",
                signals_used=self.required_signals,
            )

        evidence = [{"type": "metric", "resource_id": "",
                     "summary": f"{ws_count} workspace(s), centralized={is_central}, sentinel={sentinel}, retention={retention}d",
                     "properties": raw}]

        coverage = CoveragePayload(applicable=applicable, compliant=compliant, ratio=ratio)
        issues = []
        if not is_central:
            issues.append(f"{ws_count} workspaces — not centralized")
        if not sentinel:
            issues.append("Sentinel not enabled")
        if retention < 90:
            issues.append(f"Retention {retention}d (recommend ≥ 90)")

        if not issues:
            return ControlResult(
                status="Pass", severity="High", confidence="High", confidence_score=0.9,
                reason=f"Centralized workspace with Sentinel, {retention}d retention.",
                evidence=evidence, signals_used=self.required_signals, coverage=coverage,
            )
        if len(issues) == 1:
            return ControlResult(
                status="Partial", severity="High", confidence="High", confidence_score=0.9,
                reason=f"Workspace topology: {'; '.join(issues)}.",
                evidence=evidence, signals_used=self.required_signals, coverage=coverage,
            )
        return ControlResult(
            status="Fail", severity="High", confidence="High", confidence_score=0.9,
            reason=f"Workspace topology issues: {'; '.join(issues)}.",
            evidence=evidence, signals_used=self.required_signals, coverage=coverage,
        )


register_evaluator(WorkspaceTopologyEvaluator())


# ── Platform Automation Maturity ──────────────────────────────────
@dataclass
class AutomationMaturityEvaluator:
    control_id: str = "activity-log-analysis-001"
    required_signals: list[str] = field(
        default_factory=lambda: ["monitor:activity_log_analysis"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        sig = signals["monitor:activity_log_analysis"]
        if sig.status != SignalStatus.OK:
            return ControlResult(
                status="Manual", severity="Medium", confidence="Low", confidence_score=0.0,
                reason=sig.error_msg or "Activity log analysis not available",
                signals_used=self.required_signals,
            )

        raw = sig.raw or {}
        cov = raw.get("coverage", {})
        applicable = cov.get("applicable", 0)
        compliant = cov.get("compliant", 0)
        ratio = cov.get("ratio", 0.0)

        iac_ratio = raw.get("iac_ratio", 0)
        total_writes = raw.get("total_writes", 0)
        policy_remediations = raw.get("policy_remediations", 0)

        if total_writes == 0:
            return ControlResult(
                status="NotApplicable", severity="Info", confidence="Medium", confidence_score=0.5,
                reason="No write operations found in activity log (90d).",
                signals_used=self.required_signals,
            )

        evidence = [{"type": "metric", "resource_id": "",
                     "summary": f"IaC ratio: {iac_ratio*100:.0f}%, {total_writes} total writes, {policy_remediations} policy remediations",
                     "properties": raw}]

        coverage = CoveragePayload(applicable=applicable, compliant=compliant, ratio=ratio)
        issues = []
        if iac_ratio < 0.5:
            issues.append(f"IaC ratio {iac_ratio*100:.0f}% (recommend ≥ 50%)")
        if policy_remediations == 0:
            issues.append("No policy remediation activity detected")

        if not issues:
            return ControlResult(
                status="Pass", severity="Medium", confidence="Medium", confidence_score=0.7,
                reason=f"Automation maturity: {iac_ratio*100:.0f}% IaC, {policy_remediations} remediations.",
                evidence=evidence, signals_used=self.required_signals, coverage=coverage,
            )
        return ControlResult(
            status="Partial", severity="Medium", confidence="Medium", confidence_score=0.7,
            reason=f"Automation maturity: {'; '.join(issues)}.",
            evidence=evidence, signals_used=self.required_signals, coverage=coverage,
        )


register_evaluator(AutomationMaturityEvaluator())


# ── Update Manager Posture ────────────────────────────────────────
@dataclass
class UpdateManagerEvaluator:
    control_id: str = "update-manager-001"
    required_signals: list[str] = field(
        default_factory=lambda: ["manage:update_manager"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        sig = signals["manage:update_manager"]
        if sig.status != SignalStatus.OK:
            return ControlResult(
                status="Manual", severity="Medium", confidence="Low", confidence_score=0.0,
                reason=sig.error_msg or "Update Manager data not available",
                signals_used=self.required_signals,
            )

        raw = sig.raw or {}
        cov = raw.get("coverage", {})
        applicable = cov.get("applicable", 0)
        compliant = cov.get("compliant", 0)
        ratio = cov.get("ratio", 0.0)

        mc_count = raw.get("maintenance_config_count", 0)
        ga_count = raw.get("guest_assignment_count", 0)
        assessed = raw.get("assessed_machines", 0)
        critical = raw.get("pending_patches_critical", 0)

        evidence = [{"type": "metric", "resource_id": "",
                     "summary": f"{mc_count} maintenance config(s), {ga_count} guest assignment(s), {assessed} assessed machine(s), {critical} critical patches",
                     "properties": raw}]

        coverage = CoveragePayload(applicable=applicable, compliant=compliant, ratio=ratio)

        issues = []
        if mc_count == 0:
            issues.append("No maintenance configurations found")
        if assessed == 0 and ga_count == 0:
            issues.append("No patch assessment or guest configuration detected")
        if critical > 0:
            issues.append(f"{critical} critical patches pending")

        if not issues:
            return ControlResult(
                status="Pass", severity="Medium", confidence="Medium", confidence_score=0.7,
                reason=f"Update Manager: {mc_count} maintenance configs, {assessed} assessed VMs.",
                evidence=evidence, signals_used=self.required_signals, coverage=coverage,
            )
        if mc_count > 0 or ga_count > 0:
            return ControlResult(
                status="Partial", severity="Medium", confidence="Medium", confidence_score=0.7,
                reason=f"Update Manager: {'; '.join(issues)}.",
                evidence=evidence, signals_used=self.required_signals, coverage=coverage,
            )
        return ControlResult(
            status="Fail", severity="Medium", confidence="Medium", confidence_score=0.7,
            reason=f"Update Manager: {'; '.join(issues)}.",
            evidence=evidence, signals_used=self.required_signals, coverage=coverage,
        )


register_evaluator(UpdateManagerEvaluator())


# ── Alert to Action Group Mapping ─────────────────────────────────
@dataclass
class AlertActionMappingEvaluator:
    control_id: str = "alert-action-mapping-001"
    required_signals: list[str] = field(
        default_factory=lambda: ["monitor:alert_action_mapping"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        sig = signals["monitor:alert_action_mapping"]
        if sig.status != SignalStatus.OK:
            return ControlResult(
                status="Manual", severity="Medium", confidence="Low", confidence_score=0.0,
                reason=sig.error_msg or "Alert action mapping data not available",
                signals_used=self.required_signals,
            )

        raw = sig.raw or {}
        cov = raw.get("coverage", {})
        coverage = CoveragePayload(
            applicable=cov.get("applicable", 0),
            compliant=cov.get("compliant", 0),
            ratio=cov.get("ratio", 0.0),
        )

        total_alerts = raw.get("total_alert_rules", 0)
        alerts_with_ag = raw.get("alerts_with_action_groups", 0)
        orphan_alerts = raw.get("orphan_alert_count", 0)

        if total_alerts == 0:
            return ControlResult(
                status="Fail", severity="Medium", confidence="Medium", confidence_score=0.7,
                reason="No metric or scheduled query alert rules found.",
                signals_used=self.required_signals, coverage=coverage,
            )

        evidence = [{"type": "metric", "resource_id": "",
                     "summary": f"{total_alerts} alert(s), {alerts_with_ag} with action groups, {orphan_alerts} orphan(s)",
                     "properties": raw}]

        if orphan_alerts == 0:
            return ControlResult(
                status="Pass", severity="Medium", confidence="High", confidence_score=0.9,
                reason=f"All {total_alerts} alert rule(s) have action groups configured.",
                evidence=evidence, signals_used=self.required_signals, coverage=coverage,
            )
        ratio = alerts_with_ag / total_alerts if total_alerts > 0 else 0
        if ratio >= 0.5:
            return ControlResult(
                status="Partial", severity="Medium", confidence="High", confidence_score=0.85,
                reason=f"{orphan_alerts}/{total_alerts} alert(s) without action groups.",
                evidence=evidence, signals_used=self.required_signals, coverage=coverage,
            )
        return ControlResult(
            status="Fail", severity="Medium", confidence="High", confidence_score=0.9,
            reason=f"{orphan_alerts}/{total_alerts} alert(s) without action groups — alerts won't notify.",
            evidence=evidence, signals_used=self.required_signals, coverage=coverage,
        )


register_evaluator(AlertActionMappingEvaluator())


# ── Action Group Coverage ─────────────────────────────────────────
@dataclass
class ActionGroupCoverageEvaluator:
    control_id: str = "action-group-coverage-001"
    required_signals: list[str] = field(
        default_factory=lambda: ["monitor:action_group_coverage"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        sig = signals["monitor:action_group_coverage"]
        if sig.status != SignalStatus.OK:
            return ControlResult(
                status="Manual", severity="Medium", confidence="Low", confidence_score=0.0,
                reason=sig.error_msg or "Action group coverage data not available",
                signals_used=self.required_signals,
            )

        raw = sig.raw or {}
        cov = raw.get("coverage", {})
        coverage = CoveragePayload(
            applicable=cov.get("applicable", 0),
            compliant=cov.get("compliant", 0),
            ratio=cov.get("ratio", 0.0),
        )

        ag_count = raw.get("action_group_count", 0)
        has_email = raw.get("has_email_receivers", False)
        has_webhook = raw.get("has_webhook_receivers", False)
        has_automation = raw.get("has_automation_receivers", False)

        if ag_count == 0:
            return ControlResult(
                status="Fail", severity="Medium", confidence="High", confidence_score=0.9,
                reason="No action groups found in subscription.",
                signals_used=self.required_signals, coverage=coverage,
            )

        evidence = [{"type": "metric", "resource_id": "",
                     "summary": f"{ag_count} action group(s), email={has_email}, webhook={has_webhook}, automation={has_automation}",
                     "properties": raw}]

        issues = []
        if not has_email:
            issues.append("No email receivers configured")
        if not has_automation:
            issues.append("No automation receivers (Logic App, Function, Webhook)")

        if not issues:
            return ControlResult(
                status="Pass", severity="Medium", confidence="Medium", confidence_score=0.8,
                reason=f"{ag_count} action group(s) with email and automation receivers.",
                evidence=evidence, signals_used=self.required_signals, coverage=coverage,
            )
        return ControlResult(
            status="Partial", severity="Medium", confidence="Medium", confidence_score=0.7,
            reason=f"Action group gaps: {'; '.join(issues)}.",
            evidence=evidence, signals_used=self.required_signals, coverage=coverage,
        )


register_evaluator(ActionGroupCoverageEvaluator())


# ── SLO & Availability Signals ───────────────────────────────────
@dataclass
class AvailabilitySignalsEvaluator:
    control_id: str = "availability-signals-001"
    required_signals: list[str] = field(
        default_factory=lambda: ["monitor:availability_signals"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        sig = signals["monitor:availability_signals"]
        if sig.status != SignalStatus.OK:
            return ControlResult(
                status="Manual", severity="Medium", confidence="Low", confidence_score=0.0,
                reason=sig.error_msg or "Availability signal data not available",
                signals_used=self.required_signals,
            )

        raw = sig.raw or {}
        cov = raw.get("coverage", {})
        coverage = CoveragePayload(
            applicable=cov.get("applicable", 0),
            compliant=cov.get("compliant", 0),
            ratio=cov.get("ratio", 0.0),
        )

        service_health_alerts = raw.get("service_health_alert_count", 0)
        resource_health_alerts = raw.get("resource_health_alert_count", 0)
        smart_detector_rules = raw.get("smart_detector_rule_count", 0)

        evidence = [{"type": "metric", "resource_id": "",
                     "summary": f"Service Health: {service_health_alerts}, Resource Health: {resource_health_alerts}, Smart Detector: {smart_detector_rules}",
                     "properties": raw}]

        issues = []
        if service_health_alerts == 0:
            issues.append("No Service Health alerts configured")
        if resource_health_alerts == 0:
            issues.append("No Resource Health alerts configured")

        if not issues:
            reason = f"Availability monitoring: {service_health_alerts} Service Health + {resource_health_alerts} Resource Health alert(s)."
            if smart_detector_rules > 0:
                reason += f" {smart_detector_rules} smart detector rule(s)."
            return ControlResult(
                status="Pass", severity="Medium", confidence="Medium", confidence_score=0.8,
                reason=reason,
                evidence=evidence, signals_used=self.required_signals, coverage=coverage,
            )
        if service_health_alerts > 0 or resource_health_alerts > 0 or smart_detector_rules > 0:
            return ControlResult(
                status="Partial", severity="Medium", confidence="Medium", confidence_score=0.7,
                reason=f"Availability gaps: {'; '.join(issues)}.",
                evidence=evidence, signals_used=self.required_signals, coverage=coverage,
            )
        return ControlResult(
            status="Fail", severity="Medium", confidence="Medium", confidence_score=0.7,
            reason="No availability monitoring: no Service Health, Resource Health, or Smart Detector alerts.",
            evidence=evidence, signals_used=self.required_signals, coverage=coverage,
        )


register_evaluator(AvailabilitySignalsEvaluator())


# ── Change Tracking Enabled ───────────────────────────────────────
@dataclass
class ChangeTrackingEvaluator:
    control_id: str = "change-tracking-001"
    required_signals: list[str] = field(
        default_factory=lambda: ["monitor:change_tracking"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        sig = signals["monitor:change_tracking"]
        if sig.status != SignalStatus.OK:
            return ControlResult(
                status="Manual", severity="Medium", confidence="Low", confidence_score=0.0,
                reason=sig.error_msg or "Change tracking data not available",
                signals_used=self.required_signals,
            )

        raw = sig.raw or {}
        cov = raw.get("coverage", {})
        coverage = CoveragePayload(
            applicable=cov.get("applicable", 0),
            compliant=cov.get("compliant", 0),
            ratio=cov.get("ratio", 0.0),
        )

        rp_registered = raw.get("change_analysis_rp_registered", False)
        ct_solutions = raw.get("change_tracking_solutions", 0)
        vm_extensions = raw.get("vm_ct_extensions", 0)

        evidence = [{"type": "metric", "resource_id": "",
                     "summary": f"ChangeAnalysis RP: {rp_registered}, CT solutions: {ct_solutions}, VM extensions: {vm_extensions}",
                     "properties": raw}]

        issues = []
        if not rp_registered:
            issues.append("Microsoft.ChangeAnalysis resource provider not registered")
        if ct_solutions == 0:
            issues.append("No ChangeTracking solutions on Log Analytics workspaces")

        if not issues:
            return ControlResult(
                status="Pass", severity="Medium", confidence="Medium", confidence_score=0.8,
                reason=f"Change tracking: RP registered, {ct_solutions} solution(s), {vm_extensions} VM extension(s).",
                evidence=evidence, signals_used=self.required_signals, coverage=coverage,
            )
        if rp_registered or ct_solutions > 0 or vm_extensions > 0:
            return ControlResult(
                status="Partial", severity="Medium", confidence="Medium", confidence_score=0.7,
                reason=f"Change tracking gaps: {'; '.join(issues)}.",
                evidence=evidence, signals_used=self.required_signals, coverage=coverage,
            )
        return ControlResult(
            status="Fail", severity="Medium", confidence="Medium", confidence_score=0.7,
            reason=f"Change tracking not enabled: {'; '.join(issues)}.",
            evidence=evidence, signals_used=self.required_signals, coverage=coverage,
        )


register_evaluator(ChangeTrackingEvaluator())
