"""Azure OpenAI JSON client with retry, validation, and linting."""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any

from dotenv import load_dotenv
from openai import AzureOpenAI

load_dotenv()

FORBIDDEN_START_WORDS = ("Deploy", "Create", "Configure", "Enable", "Install", "Set up")

# Maximum retries when the model returns invalid JSON
_MAX_RETRIES = 2


class AOAIClient:
    """Thin wrapper over AzureOpenAI that always returns parsed JSON."""

    def __init__(
        self,
        model: str | None = None,
        endpoint: str | None = None,
        key: str | None = None,
        api_version: str = "2024-02-15-preview",
        temperature: float = 0.3,
        max_tokens: int = 4000,
    ):
        self.model = model or "gpt-4.1"
        self.endpoint = endpoint or os.environ.get("AZURE_OPENAI_ENDPOINT", "")
        self.key = key or os.environ.get("AZURE_OPENAI_KEY", "")
        self.api_version = api_version
        self.temperature = temperature
        self.max_tokens = max_tokens

        if not self.key or not self.endpoint:
            raise EnvironmentError(
                "AZURE_OPENAI_KEY / AZURE_OPENAI_ENDPOINT not set."
            )

        self._client = AzureOpenAI(
            api_key=self.key,
            azure_endpoint=self.endpoint,
            api_version=self.api_version,
        )

    # ── Core call ─────────────────────────────────────────────────
    def run(
        self,
        system: str,
        user: str,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """
        Send system + user prompt, parse response as JSON.
        Retries up to _MAX_RETRIES on JSONDecodeError.
        """
        temp = temperature if temperature is not None else self.temperature
        tokens = max_tokens if max_tokens is not None else self.max_tokens

        last_error: Exception | None = None
        raw = ""

        for attempt in range(_MAX_RETRIES + 1):
            try:
                response = self._client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    temperature=temp,
                    max_tokens=tokens,
                )
                raw = response.choices[0].message.content or ""
                raw = self._strip_fences(raw)
                parsed = json.loads(raw)
                self._lint(parsed)
                return parsed

            except json.JSONDecodeError as e:
                last_error = e
                print(f"  ⚠ JSON parse failed (attempt {attempt + 1}): {e}")
                if attempt < _MAX_RETRIES:
                    time.sleep(1)
                continue

            except Exception as e:
                raise RuntimeError(f"AOAI call failed: {e}") from e

        # All retries exhausted — attempt truncation repair
        repaired = self._repair_truncated(raw)
        if repaired is not None:
            print("  ⚠ Recovered truncated JSON via repair")
            self._lint(repaired)
            return repaired

        print(f"  ✗ Raw response (last attempt): {raw[:500]}")
        raise ValueError(f"Model did not return valid JSON after {_MAX_RETRIES + 1} attempts: {last_error}")

    # ── Outcome-language linter ───────────────────────────────────

    @staticmethod
    def _repair_truncated(text: str) -> dict | None:
        """Best-effort repair of JSON truncated by max_tokens.

        Closes any dangling strings, arrays, and objects so that
        json.loads() can parse it.  Returns None if repair fails.
        """
        if not text or not text.strip():
            return None
        t = AOAIClient._strip_fences(text).rstrip()
        # Remove trailing comma if any
        t = re.sub(r",\s*$", "", t)
        # Close unterminated string
        if t.count('"') % 2 != 0:
            t += '"'
        # Close open brackets/braces
        opens = []
        in_string = False
        escape = False
        for ch in t:
            if escape:
                escape = False
                continue
            if ch == '\\':
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch in ('{', '['):
                opens.append(ch)
            elif ch == '}' and opens and opens[-1] == '{':
                opens.pop()
            elif ch == ']' and opens and opens[-1] == '[':
                opens.pop()
        # Remove trailing comma before we close
        t = re.sub(r",\s*$", "", t)
        for bracket in reversed(opens):
            t += ']' if bracket == '[' else '}'
        try:
            return json.loads(t)
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _strip_fences(text: str) -> str:
        """Remove markdown code fences (```json ... ```) wrapping."""
        stripped = text.strip()
        if stripped.startswith("```"):
            # Remove opening fence (```json or just ```)
            first_nl = stripped.find("\n")
            if first_nl != -1:
                stripped = stripped[first_nl + 1:]
        if stripped.endswith("```"):
            stripped = stripped[:-3].rstrip()
        return stripped

    @staticmethod
    def _lint(data: dict) -> None:
        """Warn on task-based language in known action fields."""
        texts: list[str] = []

        # Roadmap actions
        for key in ("roadmap", "roadmap_30_60_90"):
            section = data.get(key, {})
            if isinstance(section, dict):
                for phase in section.values():
                    if isinstance(phase, list):
                        texts.extend(
                            item.get("action", "") for item in phase if isinstance(item, dict)
                        )

        # Initiative titles
        for init in data.get("initiative_execution_plan", data.get("initiatives", [])):
            if isinstance(init, dict):
                texts.append(init.get("title", ""))
                texts.append(init.get("why_it_matters", ""))

        # Backlog epics
        for epic in data.get("backlog", {}).get("epics", []):
            if isinstance(epic, dict):
                texts.append(epic.get("title", ""))
                for cap in epic.get("capabilities", []):
                    if isinstance(cap, dict):
                        texts.append(cap.get("capability", ""))
                        texts.extend(cap.get("features", []))

        for text in texts:
            if isinstance(text, str) and text.startswith(FORBIDDEN_START_WORDS):
                print(f"  ⚠ Task-based language: \"{text[:80]}\"")
