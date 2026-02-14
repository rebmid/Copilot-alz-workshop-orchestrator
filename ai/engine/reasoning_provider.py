"""Reasoning provider protocol — model-agnostic contract for LLM access.

The LLM is a dependency, not the product.  Today it's Azure OpenAI,
tomorrow it could be Phi, a local model, or a mock for tests.

Usage:
    provider = AOAIReasoningProvider()       # production
    provider = MockReasoningProvider()       # tests
    engine   = ReasoningEngine(provider, prompts)
"""
from __future__ import annotations

from typing import Any, Protocol


class ReasoningProvider(Protocol):
    """Any backend that can complete a templated prompt and return structured JSON."""

    def complete(self, template: str, payload: dict) -> dict:
        """
        Send *template* (rendered prompt text) with *payload* context
        and return parsed JSON output.

        Parameters
        ----------
        template : str
            The fully-rendered prompt text (system + user already merged
            by the reasoning engine).
        payload : dict
            Structured data the template was rendered with — passed here
            so providers can inspect it for logging / tracing.

        Returns
        -------
        dict   Parsed JSON response from the model.
        """
        ...


# ── Azure OpenAI implementation ──────────────────────────────────
class AOAIReasoningProvider:
    """Wraps the existing AOAIClient as a ReasoningProvider."""

    def __init__(
        self,
        model: str | None = None,
        endpoint: str | None = None,
        key: str | None = None,
        api_version: str = "2024-02-15-preview",
        temperature: float = 0.3,
        max_tokens: int = 4000,
    ):
        # Defer import so the module is loadable without Azure deps
        from ai.engine.aoai_client import AOAIClient

        self._client = AOAIClient(
            model=model,
            endpoint=endpoint,
            key=key,
            api_version=api_version,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def complete(self, template: str, payload: dict, *, max_tokens: int | None = None) -> dict:
        """
        *template* is the user prompt; the system prompt is embedded in
        the first line delimited by ``---SYSTEM---``.
        Falls back to a generic system prompt if delimiter is absent.
        """
        if "---SYSTEM---" in template:
            system, user = template.split("---SYSTEM---", 1)
            system = system.strip()
            user = user.strip()
        else:
            system = "You are a senior Azure architect producing structured JSON."
            user = template

        return self._client.run(system, user, max_tokens=max_tokens)


# ── Mock for offline tests ────────────────────────────────────────
class MockReasoningProvider:
    """Returns canned responses — no LLM, no network."""

    def __init__(self, responses: dict[str, dict] | None = None):
        self._responses = responses or {}
        self.calls: list[dict[str, Any]] = []

    def complete(self, template: str, payload: dict) -> dict:
        self.calls.append({"template": template[:200], "payload_keys": list(payload.keys())})
        # Return a matching canned response or empty dict
        for key, response in self._responses.items():
            if key in template:
                return response
        return {}
