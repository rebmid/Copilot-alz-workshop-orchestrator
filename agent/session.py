"""Agent session state management.

Tracks evaluation progress, open/answered questions, and emits
structured events for downstream consumers (UI, telemetry, etc.).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from signals.types import EvalScope


@dataclass
class QuestionAnswer:
    """A question posed by the agent to clarify control evaluation."""

    question_id: str
    question_text: str
    resolves_controls: list[str] = field(default_factory=list)
    answer: str | None = None


class AgentSession:
    """Stateful session tracking for an interactive ALZ assessment run.

    Parameters
    ----------
    scope : EvalScope
        Azure evaluation scope for this session.
    intent : str
        Human-readable description of the session's purpose.
    """

    def __init__(self, scope: EvalScope, intent: str = "") -> None:
        self.session_id: str = str(uuid.uuid4())
        self.scope = scope
        self.intent = intent
        self.phase: str = "initializing"

        # Evaluation tracking
        self._results: dict[str, dict[str, Any]] = {}

        # Question tracking
        self._open_questions: dict[str, QuestionAnswer] = {}
        self._answered_questions: dict[str, QuestionAnswer] = {}

        # Event log (drained via pop_events)
        self._events: list[dict[str, Any]] = []

        # Cache statistics
        self._cache_hits: int = 0
        self._cache_misses: int = 0

    # ── Evaluation ──────────────────────────────────────────────

    def record_result(self, control_id: str, result: dict[str, Any]) -> None:
        """Record a control evaluation result."""
        self._results[control_id] = result
        self._emit("control_evaluated", {
            "control_id": control_id,
            "status": result.get("status"),
        })

    @property
    def total_evaluated(self) -> int:
        return len(self._results)

    @property
    def pass_count(self) -> int:
        return sum(
            1 for r in self._results.values()
            if str(r.get("status", "")).lower() == "pass"
        )

    @property
    def fail_count(self) -> int:
        return sum(
            1 for r in self._results.values()
            if str(r.get("status", "")).lower() == "fail"
        )

    # ── Questions ───────────────────────────────────────────────

    def ask_question(self, qa: QuestionAnswer) -> None:
        """Register a new open question."""
        self._open_questions[qa.question_id] = qa
        self._emit("question_asked", {
            "question_id": qa.question_id,
            "question_text": qa.question_text,
        })

    def answer_question(self, question_id: str, answer: str) -> None:
        """Move a question from open → answered."""
        qa = self._open_questions.pop(question_id)
        qa.answer = answer
        self._answered_questions[question_id] = qa
        self._emit("question_answered", {
            "question_id": question_id,
            "answer": answer,
        })

    @property
    def open_questions(self) -> list[QuestionAnswer]:
        return list(self._open_questions.values())

    @property
    def answered_questions(self) -> list[QuestionAnswer]:
        return list(self._answered_questions.values())

    # ── Events ──────────────────────────────────────────────────

    def _emit(self, event_type: str, payload: dict[str, Any]) -> None:
        self._events.append({"type": event_type, **payload})

    def pop_events(self) -> list[dict[str, Any]]:
        """Drain and return all accumulated events."""
        events = list(self._events)
        self._events.clear()
        return events

    # ── Summary ─────────────────────────────────────────────────

    def summary(self) -> dict[str, Any]:
        """Return a snapshot of session state."""
        return {
            "session_id": self.session_id,
            "phase": self.phase,
            "evaluated": self.total_evaluated,
            "pass": self.pass_count,
            "fail": self.fail_count,
            "open_questions": len(self._open_questions),
            "answered_questions": len(self._answered_questions),
            "cache_stats": {
                "hits": self._cache_hits,
                "misses": self._cache_misses,
            },
        }
