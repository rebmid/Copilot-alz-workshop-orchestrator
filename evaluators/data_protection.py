# evaluators/data_protection.py — PaaS data posture evaluators
"""
Coverage-based evaluators for Storage, Key Vault, SQL, App Service,
Container Registry, and Private Endpoints.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from signals.types import SignalResult, SignalStatus, ControlResult, EvalContext, CoveragePayload
from evaluators.registry import register_evaluator


def _coverage_result(
    sig: SignalResult,
    *,
    required_signals: list[str],
    label: str,
    severity: str = "High",
) -> ControlResult:
    """Generic coverage-based evaluator logic with applicability filter."""
    if sig.status != SignalStatus.OK:
        return ControlResult(
            status="Manual", severity=severity, confidence="Low", confidence_score=0.0,
            reason=sig.error_msg or f"{label} data not available",
            signals_used=required_signals,
        )

    raw = sig.raw or {}
    cov = raw.get("coverage", {})
    applicable = cov.get("applicable", 0)
    compliant = cov.get("compliant", 0)
    ratio = cov.get("ratio", 0.0)

    # Applicability filter: no resources → NotApplicable
    if applicable == 0:
        return ControlResult(
            status="NotApplicable", severity="Info", confidence="High", confidence_score=1.0,
            reason=f"No {label} resources found — control not applicable.",
            signals_used=required_signals,
        )

    details = raw.get("non_compliant_details", [])
    evidence = [{"type": "coverage", "resource_id": "",
                 "summary": f"{compliant}/{applicable} compliant ({ratio*100:.0f}%)",
                 "properties": cov}]
    if details:
        evidence.extend([{"type": "finding", "resource_id": d.get("id", ""),
                          "summary": f"{d.get('resource','?')}: {', '.join(d.get('issues',[]))}",
                          "properties": d} for d in details[:5]])

    coverage = CoveragePayload(applicable=applicable, compliant=compliant, ratio=ratio)

    if ratio >= 0.8:
        return ControlResult(
            status="Pass", severity=severity, confidence="High", confidence_score=1.0,
            reason=f"{label}: {compliant}/{applicable} compliant ({ratio*100:.0f}%).",
            evidence=evidence, signals_used=required_signals, coverage=coverage,
        )
    if ratio >= 0.3:
        return ControlResult(
            status="Partial", severity=severity, confidence="High", confidence_score=1.0,
            reason=f"{label}: {compliant}/{applicable} compliant ({ratio*100:.0f}%). "
                   f"{applicable - compliant} resource(s) need remediation.",
            evidence=evidence, signals_used=required_signals, coverage=coverage,
        )
    return ControlResult(
        status="Fail", severity=severity, confidence="High", confidence_score=1.0,
        reason=f"{label}: only {compliant}/{applicable} compliant ({ratio*100:.0f}%). "
               f"Majority of resources are non-compliant.",
        evidence=evidence, signals_used=required_signals, coverage=coverage,
    )


# ── Storage Posture ──────────────────────────────────────────────
@dataclass
class StoragePostureEvaluator:
    control_id: str = "storage-posture-001"
    required_signals: list[str] = field(
        default_factory=lambda: ["resource_graph:storage_posture"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        return _coverage_result(
            signals["resource_graph:storage_posture"],
            required_signals=self.required_signals,
            label="Storage accounts",
            severity="High",
        )


register_evaluator(StoragePostureEvaluator())


# ── Key Vault Posture ─────────────────────────────────────────────
@dataclass
class KeyVaultPostureEvaluator:
    control_id: str = "keyvault-posture-001"
    required_signals: list[str] = field(
        default_factory=lambda: ["resource_graph:keyvault_posture"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        return _coverage_result(
            signals["resource_graph:keyvault_posture"],
            required_signals=self.required_signals,
            label="Key Vaults",
            severity="High",
        )


register_evaluator(KeyVaultPostureEvaluator())


# ── SQL Posture ───────────────────────────────────────────────────
@dataclass
class SqlPostureEvaluator:
    control_id: str = "sql-posture-001"
    required_signals: list[str] = field(
        default_factory=lambda: ["resource_graph:sql_posture"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        return _coverage_result(
            signals["resource_graph:sql_posture"],
            required_signals=self.required_signals,
            label="SQL servers",
            severity="High",
        )


register_evaluator(SqlPostureEvaluator())


# ── App Service Posture ───────────────────────────────────────────
@dataclass
class AppServicePostureEvaluator:
    control_id: str = "appservice-posture-001"
    required_signals: list[str] = field(
        default_factory=lambda: ["resource_graph:app_service_posture"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        return _coverage_result(
            signals["resource_graph:app_service_posture"],
            required_signals=self.required_signals,
            label="App Services",
            severity="Medium",
        )


register_evaluator(AppServicePostureEvaluator())


# ── Private Endpoint Coverage ─────────────────────────────────────
@dataclass
class PrivateEndpointCoverageEvaluator:
    control_id: str = "private-endpoint-001"
    required_signals: list[str] = field(
        default_factory=lambda: ["resource_graph:private_endpoints"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        return _coverage_result(
            signals["resource_graph:private_endpoints"],
            required_signals=self.required_signals,
            label="PaaS private endpoints",
            severity="High",
        )


register_evaluator(PrivateEndpointCoverageEvaluator())


# ── Container Registry Posture ────────────────────────────────────
@dataclass
class ACRPostureEvaluator:
    control_id: str = "acr-posture-001"
    required_signals: list[str] = field(
        default_factory=lambda: ["resource_graph:acr_posture"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        return _coverage_result(
            signals["resource_graph:acr_posture"],
            required_signals=self.required_signals,
            label="Container Registries",
            severity="Medium",
        )


register_evaluator(ACRPostureEvaluator())
