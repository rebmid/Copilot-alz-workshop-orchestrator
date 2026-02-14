"""Assessment runtime — deterministic control evaluation engine.

No LLM here. Ever.

This is the truth layer.  It wires together:
  - SignalBus        (fetches data from Azure)
  - EVALUATORS       (deterministic control logic)
  - ControlPack      (which controls to run and how they relate)

Usage:
    runtime = AssessmentRuntime(bus, pack)
    result  = runtime.evaluate_control("e6c4cfd3", scope)
    intent  = runtime.execute_intent("enterprise_scale_readiness", scope)
"""
from __future__ import annotations

from typing import Any

from schemas.domain import ControlResult, IntentResult, Confidence
from signals.types import EvalScope, EvalContext, SignalResult
from signals.registry import SignalBus
from evaluators.registry import EVALUATORS, evaluate_control as _raw_evaluate
from control_packs.loader import ControlPack
from graph.knowledge_graph import ControlKnowledgeGraph


class AssessmentRuntime:
    """Deterministic assessment engine — evaluates controls and intents."""

    def __init__(
        self,
        bus: SignalBus,
        pack: ControlPack,
        graph: ControlKnowledgeGraph | None = None,
    ):
        self.bus = bus
        self.pack = pack
        self.graph = graph or ControlKnowledgeGraph()

    # ── Single control ────────────────────────────────────────────

    def evaluate_control(
        self,
        control_id: str,
        scope: EvalScope,
        *,
        run_id: str = "",
    ) -> ControlResult:
        """
        Evaluate one control.  Returns the domain ControlResult contract.

        *control_id* can be a short ID (e6c4cfd3) or full GUID — both work.
        """
        # Resolve to full ID that the evaluator registry uses
        full_id = self.graph.resolve_full_id(control_id) or control_id

        raw = _raw_evaluate(full_id, scope, self.bus, run_id=run_id)

        return ControlResult(
            control_id=raw["control_id"],
            status=raw["status"],
            severity=raw["severity"],
            reason=raw.get("reason", ""),
            evidence=raw.get("evidence", []),
            confidence=raw.get("confidence", "Low"),
            signals_used=raw.get("signals_used", []),
        )

    # ── Intent bundle ─────────────────────────────────────────────

    def execute_intent(
        self,
        intent_id: str,
        scope: EvalScope,
        *,
        run_id: str = "",
        verbose: bool = False,
    ) -> IntentResult:
        """
        Evaluate all controls for an intent and aggregate.

        Uses the knowledge graph for:
        - control ordering (topo sort by dependencies)
        - deferral logic (skip children when parents fail)
        - discipline scoring
        """
        plan = self.graph.plan_evaluation(intent_id)
        results: dict[str, ControlResult] = {}
        deferred_ids: set[str] = set()

        for control_id in plan.ordered_controls:
            # Check deferrals against already-evaluated results
            deferrals = self.graph.apply_deferrals(
                plan,
                {cid: {"status": r["status"]} for cid, r in results.items()},
            )
            deferred_ids.update(d.control_id for d in deferrals)

            if control_id in deferred_ids:
                deferral = next(
                    (d for d in deferrals if d.control_id == control_id), None
                )
                results[control_id] = ControlResult(
                    control_id=control_id,
                    status="Deferred",
                    severity="Medium",
                    reason=deferral.reason if deferral else "Parent control failed",
                    evidence=[],
                    confidence="High",
                    signals_used=[],
                )
                if verbose:
                    node = self.graph.get_node(control_id)
                    print(f"    ⏭ {control_id} ({node.name if node else '?'}) — DEFERRED")
                continue

            cr = self.evaluate_control(control_id, scope, run_id=run_id)
            results[control_id] = cr

            if verbose:
                node = self.graph.get_node(control_id)
                icon = {"Pass": "✓", "Fail": "✗", "Partial": "◐"}.get(cr["status"], "?")
                print(f"    {icon} {control_id} ({node.name if node else '?'}) — {cr['status']}")

        # Aggregate
        passed = [cid for cid, r in results.items() if r["status"] == "Pass"]
        failed = [cid for cid, r in results.items() if r["status"] == "Fail"]
        deferred = [cid for cid, r in results.items() if r["status"] == "Deferred"]

        # Discipline scores (knowledge graph)
        raw_for_scores = {
            cid: {"status": r["status"]} for cid, r in results.items()
        }
        discipline_scores = self.graph.discipline_score(raw_for_scores)

        # Determine overall status
        if not failed and not deferred:
            status = "Ready"
        elif failed:
            status = "NotReady"
        else:
            status = "Partial"

        return IntentResult(
            intent=intent_id,
            status=status,
            summary=self._build_summary(intent_id, results),
            controls_evaluated=len(results),
            passed_controls=passed,
            failed_controls=failed,
            deferred_controls=deferred,
            data_confidence=self._aggregate_confidence(results),
            discipline_scores=discipline_scores,
        )

    # ── Batch evaluation (all pack controls) ──────────────────────

    def evaluate_all(
        self,
        scope: EvalScope,
        *,
        run_id: str = "",
    ) -> list[ControlResult]:
        """Evaluate every control registered in the evaluator registry."""
        return [
            self.evaluate_control(cid, scope, run_id=run_id)
            for cid in EVALUATORS
        ]

    # ── Helpers ───────────────────────────────────────────────────

    @staticmethod
    def _build_summary(intent_id: str, results: dict[str, ControlResult]) -> str:
        total = len(results)
        passed = sum(1 for r in results.values() if r["status"] == "Pass")
        failed = sum(1 for r in results.values() if r["status"] == "Fail")
        deferred = sum(1 for r in results.values() if r["status"] == "Deferred")

        if failed == 0:
            return f"All {passed} controls passed for {intent_id}."
        return (
            f"{failed}/{total} control(s) failed for {intent_id}. "
            f"{deferred} deferred, {passed} passed."
        )

    @staticmethod
    def _aggregate_confidence(results: dict[str, ControlResult]) -> Confidence:
        levels = [r.get("confidence", "Low") for r in results.values()]
        if all(c == "High" for c in levels):
            return "High"
        if any(c == "Low" for c in levels):
            return "Low"
        return "Medium"
