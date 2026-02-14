"""Governance evaluators — MG hierarchy, policy, compliance."""
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


def _mg_unavailable(signals: dict[str, SignalResult], required: list[str]) -> ControlResult:
    sig = signals.get("arm:mg_hierarchy")
    msg = (sig.error_msg if sig else "") or "Management group data not accessible"
    return ControlResult(
        status="Manual", severity="Medium", confidence="Low",
        reason=msg,
        signals_used=required,
    )


# ── MG Depth ─────────────────────────────────────────────────────
@dataclass
class MGDepthEvaluator:
    control_id: str = "2df27ee4-12e7-4f98-9f63-04722dd69c5b"
    required_signals: list[str] = field(default_factory=lambda: ["arm:mg_hierarchy"])

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        mg = _mg_data(signals)
        if mg is None:
            return _mg_unavailable(signals, self.required_signals)

        depth = mg.get("max_depth", 0)
        evidence = [{"type": "metric", "resource_id": "", "summary": f"max_depth={depth}",
                      "properties": {"max_depth": depth}}]

        if depth > 4:
            return ControlResult(
                status="Fail", severity="Medium", confidence="High",
                reason=f"MG hierarchy is {depth} levels deep (recommended ≤ 4).",
                evidence=evidence, signals_used=self.required_signals,
            )
        return ControlResult(
            status="Pass", severity="Medium", confidence="High",
            reason=f"MG hierarchy depth is {depth} (within recommended ≤ 4).",
            evidence=evidence, signals_used=self.required_signals,
        )


register_evaluator(MGDepthEvaluator())


# ── Platform MG ──────────────────────────────────────────────────
@dataclass
class PlatformMGEvaluator:
    control_id: str = "61623a76-5a91-47e1-b348-ef254c27d42e"
    required_signals: list[str] = field(default_factory=lambda: ["arm:mg_hierarchy"])

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        mg = _mg_data(signals)
        if mg is None:
            return _mg_unavailable(signals, self.required_signals)

        has = mg.get("has_platform_mg", False)
        evidence = [{"type": "metric", "resource_id": "", "summary": f"has_platform_mg={has}",
                      "properties": {"has_platform_mg": has}}]

        if has:
            return ControlResult(
                status="Pass", severity="Medium", confidence="High",
                reason="Platform management group detected.",
                evidence=evidence, signals_used=self.required_signals,
            )
        return ControlResult(
            status="Fail", severity="Medium", confidence="High",
            reason="No Platform management group detected under root.",
            evidence=evidence, signals_used=self.required_signals,
            next_checks=[{
                "signal": "policy:assignments",
                "why": "Without platform MG, check if policies are assigned at subscription level",
            }],
        )


register_evaluator(PlatformMGEvaluator())


# ── Landing Zones MG ─────────────────────────────────────────────
@dataclass
class LandingZonesMGEvaluator:
    control_id: str = "92481607-d5d1-4e4e-9146-58d3558fd772"
    required_signals: list[str] = field(default_factory=lambda: ["arm:mg_hierarchy"])

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        mg = _mg_data(signals)
        if mg is None:
            return _mg_unavailable(signals, self.required_signals)

        has = mg.get("has_landing_zones_mg", False)
        evidence = [{"type": "metric", "resource_id": "", "summary": f"has_landing_zones_mg={has}",
                      "properties": {"has_landing_zones_mg": has}}]

        if has:
            return ControlResult(
                status="Pass", severity="Medium", confidence="High",
                reason="Landing Zones management group detected.",
                evidence=evidence, signals_used=self.required_signals,
            )
        return ControlResult(
            status="Fail", severity="Medium", confidence="High",
            reason="No Landing Zones management group detected.",
            evidence=evidence, signals_used=self.required_signals,
        )


register_evaluator(LandingZonesMGEvaluator())


# ── Connectivity MG ──────────────────────────────────────────────
@dataclass
class ConnectivityMGEvaluator:
    control_id: str = "8bbac757-1559-4ab9-853e-8908ae28c84c"
    required_signals: list[str] = field(default_factory=lambda: ["arm:mg_hierarchy"])

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        mg = _mg_data(signals)
        if mg is None:
            return _mg_unavailable(signals, self.required_signals)

        has = mg.get("has_connectivity_mg", False)
        evidence = [{"type": "metric", "resource_id": "", "summary": f"has_connectivity_mg={has}",
                      "properties": {"has_connectivity_mg": has}}]

        if has:
            return ControlResult(
                status="Pass", severity="Medium", confidence="High",
                reason="Connectivity management group detected.",
                evidence=evidence, signals_used=self.required_signals,
            )
        return ControlResult(
            status="Fail", severity="Medium", confidence="High",
            reason="No Connectivity management group detected.",
            evidence=evidence, signals_used=self.required_signals,
        )


register_evaluator(ConnectivityMGEvaluator())


# ── Policy Initiatives ────────────────────────────────────────────
@dataclass
class PolicyInitiativesEvaluator:
    control_id: str = "5c986cb2-9131-456a-8247-6e49f541acdc"
    required_signals: list[str] = field(default_factory=lambda: ["policy:assignments"])

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        sig = signals["policy:assignments"]
        if sig.status != SignalStatus.OK:
            return ControlResult(
                status="Manual", severity="High", confidence="Low",
                reason=sig.error_msg or "Policy assignments not available",
                signals_used=self.required_signals,
            )

        data = sig.raw or {}
        initiatives = data.get("initiative", 0)
        total = data.get("total", 0)
        evidence = [{"type": "metric", "resource_id": "", "summary": f"{initiatives} initiatives / {total} total",
                      "properties": {"initiative": initiatives, "total": total}}]

        if initiatives == 0:
            return ControlResult(
                status="Fail", severity="High", confidence="High",
                reason=f"{total} policy assignment(s) but 0 initiatives. "
                       "Use Policy Initiatives to group related policies.",
                evidence=evidence, signals_used=self.required_signals,
            )
        return ControlResult(
            status="Pass", severity="High", confidence="High",
            reason=f"{initiatives} policy initiative(s) assigned ({total} total).",
            evidence=evidence, signals_used=self.required_signals,
        )


register_evaluator(PolicyInitiativesEvaluator())


# ── Policy Assignment Count ───────────────────────────────────────
@dataclass
class PolicyAssignmentCountEvaluator:
    control_id: str = "3829e7e3-1618-4368-9a04-77a209945bda"
    required_signals: list[str] = field(default_factory=lambda: ["policy:assignments"])

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        sig = signals["policy:assignments"]
        if sig.status != SignalStatus.OK:
            return ControlResult(
                status="Manual", severity="High", confidence="Low",
                reason=sig.error_msg or "Policy assignments not available",
                signals_used=self.required_signals,
            )

        data = sig.raw or {}
        total = data.get("total", 0)
        evidence = [{"type": "metric", "resource_id": "", "summary": f"{total} assignments",
                      "properties": {"total": total}}]

        if total == 0:
            return ControlResult(
                status="Fail", severity="High", confidence="High",
                reason="No policy assignments found. Azure Policy is not being used for governance.",
                evidence=evidence, signals_used=self.required_signals,
            )
        return ControlResult(
            status="Pass", severity="High", confidence="High",
            reason=f"{total} policy assignment(s) detected.",
            evidence=evidence, signals_used=self.required_signals,
        )


register_evaluator(PolicyAssignmentCountEvaluator())


# ── Policy Compliance % ───────────────────────────────────────────
@dataclass
class PolicyComplianceEvaluator:
    control_id: str = "d8a2adb1-17d6-4326-af62-5ca44e5695f2"
    required_signals: list[str] = field(default_factory=lambda: ["policy:compliance_summary"])

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        sig = signals["policy:compliance_summary"]
        if sig.status != SignalStatus.OK:
            return ControlResult(
                status="Manual", severity="Medium", confidence="Low",
                reason=sig.error_msg or "Policy compliance data not available",
                signals_used=self.required_signals,
            )

        data = sig.raw or {}
        pct = data.get("compliance_percent")
        nc = data.get("noncompliant_resources", 0)
        total = data.get("total_resources", 0)

        if pct is None:
            return ControlResult(
                status="Manual", severity="Medium", confidence="Low",
                reason="Policy compliance data not evaluable.",
                signals_used=self.required_signals,
            )

        evidence = [{"type": "metric", "resource_id": "", "summary": f"{pct}% compliance",
                      "properties": {"compliance_percent": pct, "noncompliant": nc, "total": total}}]

        if pct < 70:
            return ControlResult(
                status="Fail", severity="Medium", confidence="High",
                reason=f"Policy compliance is {pct}% ({nc} noncompliant of {total}). Target ≥ 70%.",
                evidence=evidence, signals_used=self.required_signals,
            )
        if pct < 90:
            return ControlResult(
                status="Partial", severity="Medium", confidence="High",
                reason=f"Policy compliance is {pct}% — improving but below 90% target.",
                evidence=evidence, signals_used=self.required_signals,
            )
        return ControlResult(
            status="Pass", severity="Medium", confidence="High",
            reason=f"Policy compliance is {pct}%.",
            evidence=evidence, signals_used=self.required_signals,
        )


register_evaluator(PolicyComplianceEvaluator())


# ── Noncompliant Resource Count ───────────────────────────────────
@dataclass
class NoncompliantResourcesEvaluator:
    control_id: str = "49b82111-2df2-47ee-912e-7f983f630472"
    required_signals: list[str] = field(default_factory=lambda: ["policy:compliance_summary"])

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        sig = signals["policy:compliance_summary"]
        if sig.status != SignalStatus.OK:
            return ControlResult(
                status="Manual", severity="High", confidence="Low",
                reason=sig.error_msg or "Policy compliance not available",
                signals_used=self.required_signals,
            )

        data = sig.raw or {}
        nc = data.get("noncompliant_resources", 0)
        total = data.get("total_resources", 0)
        evidence = [{"type": "metric", "resource_id": "",
                      "summary": f"{nc} noncompliant / {total} total",
                      "properties": {"noncompliant_resources": nc, "total_resources": total}}]

        if nc > 50:
            return ControlResult(
                status="Fail", severity="High", confidence="High",
                reason=f"{nc} noncompliant resources detected. Owners must be notified.",
                evidence=evidence, signals_used=self.required_signals,
            )
        if nc > 0:
            return ControlResult(
                status="Partial", severity="High", confidence="High",
                reason=f"{nc} noncompliant resource(s) detected.",
                evidence=evidence, signals_used=self.required_signals,
            )
        return ControlResult(
            status="Pass", severity="High", confidence="High",
            reason="Zero noncompliant resources.",
            evidence=evidence, signals_used=self.required_signals,
        )


register_evaluator(NoncompliantResourcesEvaluator())
