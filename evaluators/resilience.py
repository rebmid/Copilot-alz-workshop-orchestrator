# evaluators/resilience.py — Backup + resource lock coverage evaluators
"""
Coverage-based evaluators for Backup and Resource Locks.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from signals.types import SignalResult, SignalStatus, ControlResult, EvalContext, CoveragePayload
from evaluators.registry import register_evaluator


# ── Backup Coverage ───────────────────────────────────────────────
@dataclass
class BackupCoverageEvaluator:
    control_id: str = "backup-coverage-001"
    required_signals: list[str] = field(
        default_factory=lambda: ["resource_graph:backup_coverage"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        sig = signals["resource_graph:backup_coverage"]
        if sig.status != SignalStatus.OK:
            return ControlResult(
                status="Manual", severity="High", confidence="Low", confidence_score=0.0,
                reason=sig.error_msg or "Backup data not available",
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
                reason="No VMs found — backup coverage not applicable.",
                signals_used=self.required_signals,
            )

        unprotected = raw.get("unprotected_vms", [])
        evidence = [{"type": "coverage", "resource_id": "",
                     "summary": f"{compliant}/{applicable} VMs protected ({ratio*100:.0f}%)",
                     "properties": cov}]
        if unprotected:
            evidence.extend([{"type": "finding", "resource_id": vm.get("id", ""),
                              "summary": f"VM '{vm.get('name','')}' has no backup",
                              "properties": vm} for vm in unprotected[:5]])

        coverage = CoveragePayload(applicable=applicable, compliant=compliant, ratio=ratio)

        if ratio >= 0.8:
            return ControlResult(
                status="Pass", severity="High", confidence="High", confidence_score=1.0,
                reason=f"Backup coverage: {compliant}/{applicable} VMs protected ({ratio*100:.0f}%).",
                evidence=evidence, signals_used=self.required_signals, coverage=coverage,
            )
        if ratio >= 0.3:
            return ControlResult(
                status="Partial", severity="High", confidence="High", confidence_score=1.0,
                reason=f"Backup coverage: {compliant}/{applicable} VMs ({ratio*100:.0f}%). "
                       f"{applicable - compliant} VM(s) unprotected.",
                evidence=evidence, signals_used=self.required_signals, coverage=coverage,
            )
        return ControlResult(
            status="Fail", severity="High", confidence="High", confidence_score=1.0,
            reason=f"Backup coverage: only {compliant}/{applicable} VMs protected ({ratio*100:.0f}%).",
            evidence=evidence, signals_used=self.required_signals, coverage=coverage,
        )


register_evaluator(BackupCoverageEvaluator())


# ── Resource Lock Coverage ────────────────────────────────────────
@dataclass
class ResourceLockEvaluator:
    control_id: str = "resource-lock-001"
    required_signals: list[str] = field(
        default_factory=lambda: ["resource_graph:resource_locks"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        sig = signals["resource_graph:resource_locks"]
        if sig.status != SignalStatus.OK:
            return ControlResult(
                status="Manual", severity="Medium", confidence="Low", confidence_score=0.0,
                reason=sig.error_msg or "Resource lock data not available",
                signals_used=self.required_signals,
            )

        raw = sig.raw or {}
        cov = raw.get("coverage", {})
        applicable = cov.get("applicable", 0)
        compliant = cov.get("compliant", 0)
        ratio = cov.get("ratio", 0.0)
        lock_count = raw.get("lock_count", 0)

        if applicable == 0:
            return ControlResult(
                status="NotApplicable", severity="Info", confidence="High", confidence_score=1.0,
                reason="No resource groups found — lock coverage not applicable.",
                signals_used=self.required_signals,
            )

        evidence = [{"type": "coverage", "resource_id": "",
                     "summary": f"{compliant}/{applicable} RGs locked ({ratio*100:.0f}%), "
                                f"{lock_count} total locks",
                     "properties": {**cov, "lock_count": lock_count}}]

        coverage = CoveragePayload(applicable=applicable, compliant=compliant, ratio=ratio)

        if ratio >= 0.5:
            return ControlResult(
                status="Pass", severity="Medium", confidence="High", confidence_score=0.8,
                reason=f"Resource locks: {compliant}/{applicable} RGs locked. "
                       f"{lock_count} locks deployed.",
                evidence=evidence, signals_used=self.required_signals, coverage=coverage,
            )
        if lock_count > 0:
            return ControlResult(
                status="Partial", severity="Medium", confidence="High", confidence_score=0.8,
                reason=f"Resource locks exist ({lock_count}) but only {compliant}/{applicable} "
                       f"RGs covered ({ratio*100:.0f}%).",
                evidence=evidence, signals_used=self.required_signals, coverage=coverage,
            )
        return ControlResult(
            status="Fail", severity="Medium", confidence="High", confidence_score=0.8,
            reason="No resource locks found. Production resources risk accidental deletion.",
            evidence=evidence, signals_used=self.required_signals, coverage=coverage,
        )


register_evaluator(ResourceLockEvaluator())
