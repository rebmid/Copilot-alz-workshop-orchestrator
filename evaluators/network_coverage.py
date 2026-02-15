# evaluators/network_coverage.py — NSG coverage + AKS posture evaluators
"""
Coverage-based evaluators for NSG subnet coverage and AKS cluster posture.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from signals.types import SignalResult, SignalStatus, ControlResult, EvalContext, CoveragePayload
from evaluators.registry import register_evaluator


# ── NSG Subnet Coverage ──────────────────────────────────────────
@dataclass
class NSGCoverageEvaluator:
    control_id: str = "nsg-coverage-001"
    required_signals: list[str] = field(
        default_factory=lambda: ["resource_graph:nsg_coverage"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        sig = signals["resource_graph:nsg_coverage"]
        if sig.status != SignalStatus.OK:
            return ControlResult(
                status="Manual", severity="High", confidence="Low", confidence_score=0.0,
                reason=sig.error_msg or "NSG coverage data not available",
                signals_used=self.required_signals,
            )

        raw = sig.raw or {}
        cov = raw.get("coverage", {})
        applicable = cov.get("applicable", 0)
        compliant = cov.get("compliant", 0)
        ratio = cov.get("ratio", 0.0)
        empty_count = raw.get("empty_nsg_count", 0)
        uncovered = raw.get("uncovered_subnets", [])

        if applicable == 0:
            return ControlResult(
                status="NotApplicable", severity="Info", confidence="High", confidence_score=1.0,
                reason="No user subnets found — NSG coverage not applicable.",
                signals_used=self.required_signals,
            )

        evidence = [{"type": "coverage", "resource_id": "",
                     "summary": f"{compliant}/{applicable} subnets with NSG ({ratio*100:.0f}%)",
                     "properties": cov}]
        if uncovered:
            evidence.extend([{"type": "finding", "resource_id": "",
                              "summary": f"Subnet '{s.get('subnet','')}' in VNet '{s.get('vnet','')}' has no NSG",
                              "properties": s} for s in uncovered[:5]])
        if empty_count:
            evidence.append({"type": "anti-pattern", "resource_id": "",
                             "summary": f"{empty_count} NSG(s) with 0 custom rules",
                             "properties": {"empty_nsg_count": empty_count}})

        coverage = CoveragePayload(applicable=applicable, compliant=compliant, ratio=ratio)

        issues = []
        if ratio < 0.8:
            issues.append(f"{applicable - compliant} subnet(s) without NSG")
        if empty_count:
            issues.append(f"{empty_count} empty NSG(s)")

        if not issues:
            return ControlResult(
                status="Pass", severity="High", confidence="High", confidence_score=1.0,
                reason=f"NSG coverage: {compliant}/{applicable} subnets protected ({ratio*100:.0f}%).",
                evidence=evidence, signals_used=self.required_signals, coverage=coverage,
            )
        if ratio >= 0.3:
            return ControlResult(
                status="Partial", severity="High", confidence="High", confidence_score=1.0,
                reason=f"NSG coverage gaps: {'; '.join(issues)}.",
                evidence=evidence, signals_used=self.required_signals, coverage=coverage,
            )
        return ControlResult(
            status="Fail", severity="High", confidence="High", confidence_score=1.0,
            reason=f"NSG coverage critical: {'; '.join(issues)}.",
            evidence=evidence, signals_used=self.required_signals, coverage=coverage,
        )


register_evaluator(NSGCoverageEvaluator())


# ── AKS Posture ──────────────────────────────────────────────────
@dataclass
class AKSPostureEvaluator:
    control_id: str = "aks-posture-001"
    required_signals: list[str] = field(
        default_factory=lambda: ["resource_graph:aks_posture"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        sig = signals["resource_graph:aks_posture"]
        if sig.status != SignalStatus.OK:
            return ControlResult(
                status="Manual", severity="High", confidence="Low", confidence_score=0.0,
                reason=sig.error_msg or "AKS data not available",
                signals_used=self.required_signals,
            )

        raw = sig.raw or {}
        cov = raw.get("coverage", {})
        applicable = cov.get("applicable", 0)
        compliant = cov.get("compliant", 0)
        ratio = cov.get("ratio", 0.0)

        if applicable == 0:
            return ControlResult(
                status="NotApplicable", severity="Info", confidence="High", confidence_score=1.0,
                reason="No AKS clusters found — control not applicable.",
                signals_used=self.required_signals,
            )

        details = raw.get("non_compliant_details", [])
        evidence = [{"type": "coverage", "resource_id": "",
                     "summary": f"{compliant}/{applicable} AKS clusters compliant ({ratio*100:.0f}%)",
                     "properties": cov}]
        if details:
            evidence.extend([{"type": "finding", "resource_id": d.get("id", ""),
                              "summary": f"{d.get('resource','?')}: {', '.join(d.get('issues',[]))}",
                              "properties": d} for d in details[:5]])

        coverage = CoveragePayload(applicable=applicable, compliant=compliant, ratio=ratio)

        if ratio >= 0.8:
            return ControlResult(
                status="Pass", severity="High", confidence="High", confidence_score=1.0,
                reason=f"AKS posture: {compliant}/{applicable} compliant ({ratio*100:.0f}%).",
                evidence=evidence, signals_used=self.required_signals, coverage=coverage,
            )
        if ratio >= 0.3:
            return ControlResult(
                status="Partial", severity="High", confidence="High", confidence_score=1.0,
                reason=f"AKS posture: {compliant}/{applicable} compliant ({ratio*100:.0f}%).",
                evidence=evidence, signals_used=self.required_signals, coverage=coverage,
            )
        return ControlResult(
            status="Fail", severity="High", confidence="High", confidence_score=1.0,
            reason=f"AKS posture: only {compliant}/{applicable} compliant ({ratio*100:.0f}%).",
            evidence=evidence, signals_used=self.required_signals, coverage=coverage,
        )


register_evaluator(AKSPostureEvaluator())


# ── Network Watcher Observability ─────────────────────────────────
@dataclass
class NetworkWatcherEvaluator:
    control_id: str = "network-watcher-001"
    required_signals: list[str] = field(
        default_factory=lambda: ["network:watcher_posture"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        sig = signals["network:watcher_posture"]
        if sig.status != SignalStatus.OK:
            return ControlResult(
                status="Manual", severity="Medium", confidence="Low", confidence_score=0.0,
                reason=sig.error_msg or "Network Watcher data not available",
                signals_used=self.required_signals,
            )

        raw = sig.raw or {}
        cov = raw.get("coverage", {})
        applicable = cov.get("applicable", 0)
        compliant = cov.get("compliant", 0)
        ratio = cov.get("ratio", 0.0)

        watcher_count = raw.get("watcher_count", 0)
        flow_v2 = raw.get("flow_log_v2_count", 0)
        ta_count = raw.get("traffic_analytics_count", 0)
        conn_mon = raw.get("connection_monitor_count", 0)

        if watcher_count == 0:
            return ControlResult(
                status="Fail", severity="Medium", confidence="High", confidence_score=0.9,
                reason="No Network Watcher resources found.",
                signals_used=self.required_signals,
            )

        evidence = [{"type": "metric", "resource_id": "",
                     "summary": f"{watcher_count} watcher(s), {flow_v2} flow log v2, {ta_count} Traffic Analytics, {conn_mon} connection monitor(s)",
                     "properties": raw}]

        coverage = CoveragePayload(applicable=applicable, compliant=compliant, ratio=ratio)

        issues = []
        if flow_v2 == 0:
            issues.append("No NSG flow logs v2 configured")
        if ta_count == 0:
            issues.append("Traffic Analytics not enabled")

        if not issues:
            return ControlResult(
                status="Pass", severity="Medium", confidence="High", confidence_score=0.9,
                reason=f"Network observability: {flow_v2} flow log(s) v2, {ta_count} Traffic Analytics.",
                evidence=evidence, signals_used=self.required_signals, coverage=coverage,
            )
        return ControlResult(
            status="Partial", severity="Medium", confidence="High", confidence_score=0.9,
            reason=f"Network observability gaps: {'; '.join(issues)}.",
            evidence=evidence, signals_used=self.required_signals, coverage=coverage,
        )


register_evaluator(NetworkWatcherEvaluator())
