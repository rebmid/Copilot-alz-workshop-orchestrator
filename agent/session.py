"""Agent session state — tracks a workshop conversation."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from signals.types import EvalScope
from signals.cache import SignalCache
from signals.registry import SignalBus


@dataclass
class QuestionAnswer:
    """A question–answer pair from the workshop."""
    question_id: str
    question_text: str
    answer: str | None = None
    answered_at: str | None = None
    resolves_controls: list[str] = field(default_factory=list)


@dataclass
class AgentSession:
    """
    Stateful session for a workshop agent conversation.

    Tracks:
    - Which controls have been evaluated
    - Which questions have been asked/answered
    - The signal cache (shared across controls)
    - Streaming events for the UI
    """
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    scope: EvalScope = field(default_factory=EvalScope)
    signal_cache: SignalCache = field(default_factory=SignalCache)

    # State
    evaluated_controls: dict[str, dict[str, Any]] = field(default_factory=dict)
    open_questions: dict[str, QuestionAnswer] = field(default_factory=dict)
    answered_questions: dict[str, QuestionAnswer] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    intent: str = ""
    phase: str = "idle"  # idle | preflight | evaluating | questions | narrative | done

    def get_bus(self) -> SignalBus:
        """Return a SignalBus backed by this session's cache."""
        return SignalBus(cache=self.signal_cache)

    def record_result(self, control_id: str, result: dict[str, Any]) -> None:
        """Record a control evaluation result."""
        self.evaluated_controls[control_id] = result
        self._emit("control_evaluated", control_id=control_id, status=result.get("status"))

    def ask_question(self, qa: QuestionAnswer) -> None:
        """Register a question for the user."""
        self.open_questions[qa.question_id] = qa
        self._emit("question_asked", question_id=qa.question_id, text=qa.question_text)

    def answer_question(self, question_id: str, answer: str) -> None:
        """Record an answer for a previously asked question."""
        qa = self.open_questions.pop(question_id, None)
        if qa is None:
            return
        qa.answer = answer
        qa.answered_at = datetime.now(timezone.utc).isoformat()
        self.answered_questions[question_id] = qa
        self._emit("question_answered", question_id=question_id)

    def set_phase(self, phase: str) -> None:
        self.phase = phase
        self._emit("phase_changed", phase=phase)

    def _emit(self, event_type: str, **kwargs: Any) -> None:
        self.events.append({
            "type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **kwargs,
        })

    def pop_events(self) -> list[dict[str, Any]]:
        """Drain accumulated events for streaming to UI."""
        out = self.events.copy()
        self.events.clear()
        return out

    # ── Summary ───────────────────────────────────────────────

    @property
    def pass_count(self) -> int:
        return sum(1 for r in self.evaluated_controls.values() if r.get("status") == "Pass")

    @property
    def fail_count(self) -> int:
        return sum(1 for r in self.evaluated_controls.values() if r.get("status") == "Fail")

    @property
    def total_evaluated(self) -> int:
        return len(self.evaluated_controls)

    def summary(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "phase": self.phase,
            "intent": self.intent,
            "scope": {
                "tenant_id": self.scope.tenant_id,
                "subscription_count": len(self.scope.subscription_ids),
            },
            "evaluated": self.total_evaluated,
            "pass": self.pass_count,
            "fail": self.fail_count,
            "open_questions": len(self.open_questions),
            "answered_questions": len(self.answered_questions),
            "cache_stats": self.signal_cache.stats(),
        }
