"""Security evaluators — Defender, secure score, diagnostics."""
from __future__ import annotations

from dataclasses import dataclass, field

from signals.types import ControlResult, EvalContext, SignalResult, SignalStatus
from evaluators.registry import register_evaluator


# ── Defender CSPM ─────────────────────────────────────────────────
@dataclass
class DefenderCSPMEvaluator:
    control_id: str = "09945bda-4333-44f2-9911-634182ba5275"
    required_signals: list[str] = field(default_factory=lambda: ["defender:pricings"])

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        sig = signals["defender:pricings"]
        if sig.status != SignalStatus.OK:
            return ControlResult(
                status="Manual", severity="High", confidence="Low",
                reason=sig.error_msg or "Defender pricing not available",
                signals_used=self.required_signals,
            )
        plans = sig.items or []
        cspm = [p for p in plans if (p.get("name") or "").lower() in ("cloudposture", "cspm")]

        if not cspm:
            return ControlResult(
                status="Fail", severity="High", confidence="High",
                reason="Defender CSPM plan not found in pricings.",
                signals_used=self.required_signals,
            )
        enabled = [p for p in cspm if (p.get("tier") or "").lower() in ("standard", "premium")]
        if not enabled:
            return ControlResult(
                status="Fail", severity="High", confidence="High",
                reason=f"Defender CSPM plan found but not enabled (tier: {cspm[0].get('tier')}).",
                evidence=[{"type": "config", "resource_id": "", "summary": "CSPM plan",
                           "properties": cspm[0]}],
                signals_used=self.required_signals,
            )
        return ControlResult(
            status="Pass", severity="High", confidence="High",
            reason="Defender CSPM plan is enabled.",
            evidence=[{"type": "config", "resource_id": "", "summary": "CSPM enabled",
                       "properties": enabled[0]}],
            signals_used=self.required_signals,
        )


register_evaluator(DefenderCSPMEvaluator())


# ── Defender CWP Coverage ─────────────────────────────────────────
@dataclass
class DefenderCWPEvaluator:
    control_id: str = "77425f48-ecba-43a0-aeac-a3ac733ccc6a"
    required_signals: list[str] = field(default_factory=lambda: ["defender:pricings"])

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        sig = signals["defender:pricings"]
        if sig.status != SignalStatus.OK:
            return ControlResult(
                status="Manual", severity="High", confidence="Low",
                reason=sig.error_msg or "Defender pricing not available",
                signals_used=self.required_signals,
            )
        data = sig.raw or {}
        total = data.get("plans_total", 0)
        enabled = data.get("plans_enabled", 0)

        if total == 0:
            return ControlResult(
                status="Manual", severity="High", confidence="Low",
                reason="No Defender plans data available.",
                signals_used=self.required_signals,
            )

        pct = round((enabled / total) * 100, 1)
        evidence = [{"type": "metric", "resource_id": "", "summary": f"{pct}% coverage",
                     "properties": {"plans_total": total, "plans_enabled": enabled, "pct": pct}}]

        if pct < 50:
            return ControlResult(
                status="Fail", severity="High", confidence="High",
                reason=f"Only {enabled}/{total} Defender plans enabled ({pct}%).",
                evidence=evidence, signals_used=self.required_signals,
            )
        if pct < 80:
            return ControlResult(
                status="Partial", severity="High", confidence="High",
                reason=f"{enabled}/{total} Defender plans enabled ({pct}%). Some plans still disabled.",
                evidence=evidence, signals_used=self.required_signals,
            )
        return ControlResult(
            status="Pass", severity="High", confidence="High",
            reason=f"{enabled}/{total} Defender plans enabled ({pct}%).",
            evidence=evidence, signals_used=self.required_signals,
        )


register_evaluator(DefenderCWPEvaluator())


# ── Defender for Servers ──────────────────────────────────────────
@dataclass
class DefenderServersEvaluator:
    control_id: str = "36a72a48-fffe-4c40-9747-0ab5064355ba"
    required_signals: list[str] = field(default_factory=lambda: ["defender:pricings"])

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        sig = signals["defender:pricings"]
        if sig.status != SignalStatus.OK:
            return ControlResult(
                status="Manual", severity="High", confidence="Low",
                reason=sig.error_msg or "Defender pricing not available",
                signals_used=self.required_signals,
            )
        plans = sig.items or []
        servers = [p for p in plans if (p.get("name") or "").lower() in (
            "virtualmachines", "servers", "virtualmachine")]

        if not servers:
            return ControlResult(
                status="Fail", severity="High", confidence="High",
                reason="Defender for Servers plan not found.",
                signals_used=self.required_signals,
            )
        enabled = [p for p in servers if (p.get("tier") or "").lower() in ("standard", "premium")]
        if not enabled:
            return ControlResult(
                status="Fail", severity="High", confidence="High",
                reason=f"Defender for Servers found but not enabled (tier: {servers[0].get('tier')}).",
                evidence=[{"type": "config", "resource_id": "", "summary": "Servers plan",
                           "properties": servers[0]}],
                signals_used=self.required_signals,
            )
        return ControlResult(
            status="Pass", severity="High", confidence="High",
            reason="Defender for Servers plan is enabled.",
            evidence=[{"type": "config", "resource_id": "", "summary": "Servers enabled",
                       "properties": enabled[0]}],
            signals_used=self.required_signals,
        )


register_evaluator(DefenderServersEvaluator())


# ── Secure Score Threshold ────────────────────────────────────────
@dataclass
class SecureScoreEvaluator:
    control_id: str = "15833ee7-ad6c-46d3-9331-65c7acbe44ab"
    required_signals: list[str] = field(default_factory=lambda: ["defender:secure_score"])

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        sig = signals["defender:secure_score"]
        if sig.status != SignalStatus.OK:
            return ControlResult(
                status="Manual", severity="Medium", confidence="Low",
                reason=sig.error_msg or "Secure score not available",
                signals_used=self.required_signals,
            )
        scores = sig.items or []
        if not scores:
            return ControlResult(
                status="Manual", severity="Medium", confidence="Low",
                reason="No secure score data returned.",
                signals_used=self.required_signals,
            )

        primary = scores[0]
        pct = primary.get("percentage")
        if pct is None:
            return ControlResult(
                status="Manual", severity="Medium", confidence="Low",
                reason="Secure score percentage not available.",
                signals_used=self.required_signals,
            )

        pct_val = pct * 100 if pct <= 1 else pct
        evidence = [{"type": "metric", "resource_id": "", "summary": f"score={pct_val:.0f}%",
                     "properties": {"score_name": primary.get("name"), "percentage": pct_val,
                                    "current": primary.get("current"), "max": primary.get("max")}}]

        if pct_val < 40:
            return ControlResult(
                status="Fail", severity="Medium", confidence="High",
                reason=f"Secure score is {pct_val:.0f}% — critical.",
                evidence=evidence, signals_used=self.required_signals,
            )
        if pct_val < 70:
            return ControlResult(
                status="Partial", severity="Medium", confidence="High",
                reason=f"Secure score is {pct_val:.0f}% — below recommended 70% baseline.",
                evidence=evidence, signals_used=self.required_signals,
            )
        return ControlResult(
            status="Pass", severity="Medium", confidence="High",
            reason=f"Secure score is {pct_val:.0f}%.",
            evidence=evidence, signals_used=self.required_signals,
        )


register_evaluator(SecureScoreEvaluator())


# ── Centralized Security Visibility (score + diagnostics) ─────────
@dataclass
class CentralizedSecurityEvaluator:
    control_id: str = "a56888b2-7e83-4404-bd31-b886528502d1"
    required_signals: list[str] = field(
        default_factory=lambda: ["defender:secure_score", "monitor:diag_coverage_sample"]
    )

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        ds = signals["defender:secure_score"]
        diag = signals["monitor:diag_coverage_sample"]
        issues = []
        evidence = []

        if ds.status == SignalStatus.OK and ds.items:
            pct = ds.items[0].get("percentage", 0) or 0
            pct_val = pct * 100 if pct <= 1 else pct
            evidence.append({"type": "metric", "resource_id": "", "summary": f"score={pct_val:.0f}%",
                            "properties": {"secure_score_percent": pct_val}})
            if pct_val < 50:
                issues.append(f"Secure score {pct_val:.0f}% is low")

        if diag.status == SignalStatus.OK and diag.raw:
            diag_pct = diag.raw.get("diag_coverage_percent")
            if diag_pct is not None:
                evidence.append({"type": "metric", "resource_id": "", "summary": f"diag={diag_pct}%",
                                "properties": {"diag_coverage_percent": diag_pct}})
                if diag_pct < 50:
                    issues.append(f"Diagnostics coverage {diag_pct}% is low")

        if not evidence:
            return ControlResult(
                status="Manual", severity="High", confidence="Low",
                reason="Neither secure score nor diagnostics data available.",
                signals_used=self.required_signals,
            )

        if issues:
            return ControlResult(
                status="Fail", severity="High", confidence="High",
                reason="Centralized security visibility gaps: " + "; ".join(issues) + ".",
                evidence=evidence, signals_used=self.required_signals,
            )
        return ControlResult(
            status="Pass", severity="High", confidence="High",
            reason="Security data consolidation indicators are healthy.",
            evidence=evidence, signals_used=self.required_signals,
        )


register_evaluator(CentralizedSecurityEvaluator())


# ── Diagnostics Coverage ──────────────────────────────────────────
@dataclass
class DiagnosticsCoverageEvaluator:
    control_id: str = "67e7a8ed-4b30-4e38-a3f2-9812b2363cef"
    required_signals: list[str] = field(default_factory=lambda: ["monitor:diag_coverage_sample"])

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        sig = signals["monitor:diag_coverage_sample"]
        if sig.status != SignalStatus.OK:
            return ControlResult(
                status="Manual", severity="Medium", confidence="Low",
                reason=sig.error_msg or "Diagnostics data not available",
                signals_used=self.required_signals,
            )
        data = sig.raw or {}
        pct = data.get("diag_coverage_percent")
        sample = data.get("sample_size", 0)

        if pct is None:
            return ControlResult(
                status="Manual", severity="Medium", confidence="Low",
                reason="Diagnostics coverage data not evaluable.",
                signals_used=self.required_signals,
            )

        evidence = [{"type": "metric", "resource_id": "",
                     "summary": f"{pct}% coverage (sample={sample})",
                     "properties": {"diag_coverage_percent": pct, "sample_size": sample}}]

        if pct < 30:
            return ControlResult(
                status="Fail", severity="Medium", confidence="High",
                reason=f"Diagnostics coverage is {pct}% (sample={sample}). "
                       "Most resources lack diagnostic settings.",
                evidence=evidence, signals_used=self.required_signals,
            )
        if pct < 70:
            return ControlResult(
                status="Partial", severity="Medium", confidence="High",
                reason=f"Diagnostics coverage is {pct}% (sample={sample}).",
                evidence=evidence, signals_used=self.required_signals,
            )
        return ControlResult(
            status="Pass", severity="Medium", confidence="High",
            reason=f"Diagnostics coverage is {pct}% (sample={sample}).",
            evidence=evidence, signals_used=self.required_signals,
        )


register_evaluator(DiagnosticsCoverageEvaluator())


# ── Diagnostics for Identity (Entra ID logs) ─────────────────────
@dataclass
class DiagnosticsIdentityEvaluator:
    control_id: str = "1cf0b8da-70bd-44d0-94af-8d99cfc89ae1"
    required_signals: list[str] = field(default_factory=lambda: ["monitor:diag_coverage_sample"])

    def evaluate(self, ctx: EvalContext, signals: dict[str, SignalResult]) -> ControlResult:
        sig = signals["monitor:diag_coverage_sample"]
        if sig.status != SignalStatus.OK:
            return ControlResult(
                status="Manual", severity="Medium", confidence="Low",
                reason=sig.error_msg or "Diagnostics data not available",
                signals_used=self.required_signals,
            )
        data = sig.raw or {}
        pct = data.get("diag_coverage_percent")

        if pct is None:
            return ControlResult(
                status="Manual", severity="Medium", confidence="Low",
                reason="Cannot assess Entra ID log integration.",
                signals_used=self.required_signals,
            )

        evidence = [{"type": "metric", "resource_id": "",
                     "summary": f"diag={pct}%",
                     "properties": {"diag_coverage_percent": pct}}]

        if pct < 50:
            return ControlResult(
                status="Fail", severity="Medium", confidence="High",
                reason=f"Low diagnostics coverage ({pct}%) suggests Entra ID logs may not be centralized.",
                evidence=evidence, signals_used=self.required_signals,
                next_checks=[{
                    "signal": "arm:entra_diagnostic_settings",
                    "why": "Directly verify Entra ID diagnostic settings export to Log Analytics",
                }],
            )
        return ControlResult(
            status="Pass", severity="Medium", confidence="High",
            reason=f"Diagnostics coverage ({pct}%) suggests centralized logging is in place.",
            evidence=evidence, signals_used=self.required_signals,
        )


register_evaluator(DiagnosticsIdentityEvaluator())
