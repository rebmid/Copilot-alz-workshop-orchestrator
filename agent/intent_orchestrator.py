"""Intent orchestrator — the CSA's primary interaction surface.

Combines the deterministic AssessmentRuntime with the model-agnostic
ReasoningEngine to produce explainable intent results.

Usage:
    runtime      = AssessmentRuntime(bus, pack)
    reasoning    = ReasoningEngine(provider, prompts)
    orchestrator = IntentOrchestrator(runtime, reasoning)

    result = orchestrator.run_intent("enterprise_scale_readiness", scope)
    # → { intent_result, explanation, roadmap }
"""
from __future__ import annotations

from typing import Any

from schemas.domain import IntentResult
from signals.types import EvalScope
from engine.assessment_runtime import AssessmentRuntime
from ai.engine.reasoning_engine import ReasoningEngine


class IntentOrchestrator:
    """
    Workshop orchestrator that:
      1. Runs deterministic evaluation (no LLM)
      2. Passes results to the reasoning engine for explanation
      3. Returns both the facts and the narrative
    """

    def __init__(
        self,
        runtime: AssessmentRuntime,
        reasoning: ReasoningEngine | None = None,
    ):
        self.runtime = runtime
        self.reasoning = reasoning

    # ── Core workflow ─────────────────────────────────────────────

    def run_intent(
        self,
        intent_id: str,
        scope: EvalScope,
        *,
        run_id: str = "",
        verbose: bool = False,
        skip_reasoning: bool = False,
    ) -> dict[str, Any]:
        """
        Execute an intent end-to-end:
          1. Deterministic control evaluation → IntentResult
          2. AI explanation (optional) → narrative dict
          3. AI roadmap (optional) → transformation dict

        If *skip_reasoning* is True or no reasoning engine was supplied,
        only the deterministic result is returned.
        """
        # Phase 1: Deterministic evaluation
        if verbose:
            print(f"\n  ── Evaluating intent: {intent_id} ──")
        intent_result = self.runtime.execute_intent(
            intent_id, scope, run_id=run_id, verbose=verbose,
        )

        output: dict[str, Any] = {
            "intent_result": dict(intent_result),
        }

        # Phase 2: Reasoning (optional)
        if not skip_reasoning and self.reasoning is not None:
            if verbose:
                print(f"\n  ── Generating AI explanation ──")
            try:
                explanation = self.reasoning.explain_intent(dict(intent_result))
                output["explanation"] = explanation
            except Exception as e:
                if verbose:
                    print(f"    ⚠ Explanation failed: {e}")
                output["explanation"] = None

            if verbose:
                print(f"  ── Generating roadmap ──")
            try:
                roadmap = self.reasoning.build_roadmap(dict(intent_result))
                output["roadmap"] = roadmap
            except Exception as e:
                if verbose:
                    print(f"    ⚠ Roadmap failed: {e}")
                output["roadmap"] = None

            if verbose:
                print(f"  ── Generating target architecture ──")
            try:
                target_arch = self.reasoning.target_architecture(dict(intent_result))
                output["target_architecture"] = target_arch
            except Exception as e:
                if verbose:
                    print(f"    ⚠ Target architecture failed: {e}")
                output["target_architecture"] = None
        else:
            output["explanation"] = None
            output["roadmap"] = None
            output["target_architecture"] = None

        return output
