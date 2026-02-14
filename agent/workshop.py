"""Workshop agent loop — orchestrates an interactive assessment session.

Usage:
    from agent.workshop import WorkshopAgent
    agent = WorkshopAgent()
    result = agent.run_assessment("enterprise_readiness", scope)
    # or step-by-step:
    agent.start_session("network_review", scope)
    events = agent.step()   # returns streaming events
"""
from __future__ import annotations

from typing import Any, Generator

from signals.types import EvalScope
from signals.registry import SignalBus
from graph.knowledge_graph import ControlKnowledgeGraph, EvalPlan
from evaluators.registry import evaluate_control, EVALUATORS
from agent.session import AgentSession, QuestionAnswer
from preflight.analyzer import AzureContext, run_preflight, build_azure_context


class WorkshopAgent:
    """
    Stateful workshop agent that:
    1. Runs preflight probes
    2. Plans evaluation via knowledge graph
    3. Evaluates controls in dependency order
    4. Applies deferrals for failed parents
    5. Surfaces targeted questions
    6. Computes discipline scores
    """

    def __init__(
        self,
        graph: ControlKnowledgeGraph | None = None,
        azure_ctx: AzureContext | None = None,
    ):
        self.graph = graph or ControlKnowledgeGraph()
        self.azure_ctx = azure_ctx
        self.session: AgentSession | None = None
        self._plan: EvalPlan | None = None

    # ── Full run (non-interactive) ────────────────────────────

    def run_assessment(
        self,
        intent: str,
        scope: EvalScope,
        *,
        skip_preflight: bool = False,
        verbose: bool = False,
    ) -> dict[str, Any]:
        """
        Run a complete assessment for an intent bundle.
        Returns the full session result including discipline scores.
        """
        self.start_session(intent, scope)
        assert self.session is not None
        assert self._plan is not None

        # Phase 1: Preflight
        preflight_result = None
        if not skip_preflight:
            self.session.set_phase("preflight")
            if verbose:
                print(f"\n  Phase 1: Preflight probes …")
            ctx = self.azure_ctx or build_azure_context(
                subscription_ids=scope.subscription_ids
            )
            preflight_result = run_preflight(ctx, verbose=verbose)

        # Phase 2: Plan
        if verbose:
            plan = self._plan
            print(f"\n  Phase 2: Planning — {len(plan.ordered_controls)} controls, "
                  f"{len(plan.required_signals)} unique signals")

        # Phase 3: Evaluate
        self.session.set_phase("evaluating")
        if verbose:
            print(f"\n  Phase 3: Evaluating controls …")

        bus = self.session.get_bus()
        deferred_ids: set[str] = set()

        for control_id in self._plan.ordered_controls:
            # Check for deferrals
            deferrals = self.graph.apply_deferrals(self._plan, self.session.evaluated_controls)
            deferred_ids.update(d.control_id for d in deferrals)

            if control_id in deferred_ids:
                # Record as deferred
                deferral = next((d for d in deferrals if d.control_id == control_id), None)
                self.session.record_result(control_id, {
                    "control_id": control_id,
                    "status": "Deferred",
                    "severity": "Medium",
                    "confidence": "N/A",
                    "reason": deferral.reason if deferral else "Deferred due to parent failure",
                    "evidence": [],
                    "signals_used": [],
                    "next_checks": [],
                    "telemetry": {"duration_ms": 0, "cache_hit": False},
                })
                if verbose:
                    node = self.graph.get_node(control_id)
                    name = node.name if node else control_id
                    print(f"    ⏭ {control_id} ({name}) — DEFERRED")
                continue

            # Resolve full ID for evaluate_control
            full_id = self.graph.resolve_full_id(control_id)
            eval_id = full_id or control_id

            result = evaluate_control(eval_id, scope, bus, run_id=self.session.session_id)
            self.session.record_result(control_id, result)

            if verbose:
                node = self.graph.get_node(control_id)
                name = node.name if node else control_id
                status = result.get("status", "?")
                ms = result.get("telemetry", {}).get("duration_ms", 0)
                cache = result.get("telemetry", {}).get("cache_hit", False)
                icon = {"Pass": "✓", "Fail": "✗", "Partial": "◐", "Deferred": "⏭"}.get(status, "?")
                print(f"    {icon} {control_id} ({name}) — {status} ({ms}ms, cache={cache})")

        # Phase 4: Questions
        self.session.set_phase("questions")
        failed_controls = {
            cid: res for cid, res in self.session.evaluated_controls.items()
            if res.get("status") in ("Fail", "Partial", "Error")
        }
        questions = self.graph.get_questions_for(
            list(self.session.evaluated_controls.keys()),
            only_failed=failed_controls,
        )
        for q in questions:
            qa = QuestionAnswer(
                question_id=q["id"],
                question_text=q["question"],
                resolves_controls=q.get("resolves_controls", []),
            )
            self.session.ask_question(qa)

        if verbose and questions:
            print(f"\n  Phase 4: {len(questions)} question(s) to resolve:")
            for q in questions:
                print(f"    ? {q['id']}: {q['question']}")

        # Phase 5: Scores
        self.session.set_phase("done")
        discipline_scores = self.graph.discipline_score(self.session.evaluated_controls)

        if verbose:
            print(f"\n  ── Discipline Scores ──")
            for d, data in discipline_scores.items():
                print(f"    {data['discipline_label']:40s} {data['score']:>3d}%")

        # Final output
        return {
            "session": self.session.summary(),
            "preflight": preflight_result,
            "plan": {
                "intent": self._plan.intent,
                "controls_planned": len(self._plan.ordered_controls),
                "signals_required": self._plan.required_signals,
                "deferred": self._plan.deferred,
            },
            "results": self.session.evaluated_controls,
            "discipline_scores": discipline_scores,
            "questions": [
                {
                    "id": qa.question_id,
                    "question": qa.question_text,
                    "resolves_controls": qa.resolves_controls,
                }
                for qa in self.session.open_questions.values()
            ],
            "signal_cache_stats": self.session.signal_cache.stats(),
            "events": self.session.pop_events(),
        }

    # ── Session management ────────────────────────────────────

    def start_session(self, intent: str, scope: EvalScope) -> AgentSession:
        """Initialize a new session with a plan."""
        self.session = AgentSession(scope=scope, intent=intent)
        self._plan = self.graph.plan_evaluation(intent)
        self.session.set_phase("planned")
        return self.session

    def step(self) -> list[dict[str, Any]]:
        """
        Execute the next step in the session and return events.
        For use in interactive/streaming mode.
        """
        if self.session is None or self._plan is None:
            return [{"type": "error", "detail": "No active session"}]

        bus = self.session.get_bus()

        # Find next unevaluated control
        for control_id in self._plan.ordered_controls:
            if control_id in self.session.evaluated_controls:
                continue

            # Check deferrals
            deferrals = self.graph.apply_deferrals(self._plan, self.session.evaluated_controls)
            deferred_ids = {d.control_id for d in deferrals}

            if control_id in deferred_ids:
                deferral = next((d for d in deferrals if d.control_id == control_id), None)
                self.session.record_result(control_id, {
                    "control_id": control_id,
                    "status": "Deferred",
                    "reason": deferral.reason if deferral else "Deferred",
                    "evidence": [],
                    "signals_used": [],
                    "next_checks": [],
                    "telemetry": {"duration_ms": 0, "cache_hit": False},
                })
                return self.session.pop_events()

            full_id = self.graph.resolve_full_id(control_id)
            result = evaluate_control(
                full_id or control_id,
                self.session.scope,
                bus,
                run_id=self.session.session_id,
            )
            self.session.record_result(control_id, result)
            return self.session.pop_events()

        # All controls done — transition to questions phase
        if self.session.phase == "evaluating":
            self.session.set_phase("questions")
            failed = {
                cid: r for cid, r in self.session.evaluated_controls.items()
                if r.get("status") in ("Fail", "Partial", "Error")
            }
            questions = self.graph.get_questions_for(
                list(self.session.evaluated_controls.keys()),
                only_failed=failed,
            )
            for q in questions:
                self.session.ask_question(QuestionAnswer(
                    question_id=q["id"],
                    question_text=q["question"],
                    resolves_controls=q.get("resolves_controls", []),
                ))

        return self.session.pop_events()

    # ── Step-through generator (streaming) ────────────────────

    def stream_evaluation(
        self,
        intent: str,
        scope: EvalScope,
    ) -> Generator[list[dict[str, Any]], None, dict[str, Any]]:
        """
        Generator that yields events after each control evaluation.
        Returns final result dict when exhausted.

        Usage:
            gen = agent.stream_evaluation("network_review", scope)
            for events in gen:
                for e in events:
                    print(e)
        """
        self.start_session(intent, scope)
        assert self.session is not None
        assert self._plan is not None
        self.session.set_phase("evaluating")

        while True:
            events = self.step()
            if not events:
                break
            yield events

            # Check if all done
            remaining = [
                c for c in self._plan.ordered_controls
                if c not in self.session.evaluated_controls
            ]
            if not remaining:
                break

        # Yield question events
        events = self.step()
        if events:
            yield events

        self.session.set_phase("done")
        scores = self.graph.discipline_score(self.session.evaluated_controls)

        return {
            "session": self.session.summary(),
            "results": self.session.evaluated_controls,
            "discipline_scores": scores,
        }
