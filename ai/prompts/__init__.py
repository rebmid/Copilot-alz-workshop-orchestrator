"""Prompt loader — reads versioned .txt templates from this directory."""
import os
from pathlib import Path

PROMPT_DIR = Path(__file__).parent


def _load(name: str) -> str:
    path = PROMPT_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    return path.read_text(encoding="utf-8")


class PromptPack:
    """Versioned prompt templates for the CSA Copilot engine."""

    def __init__(self):
        self._system = _load("system.txt")

    # ── Shared system prompt ──────────────────────────────────────
    @property
    def system(self) -> str:
        return self._system

    # ── Per-pass user prompts ─────────────────────────────────────
    def roadmap(self, payload: dict) -> str:
        import json
        tpl = _load("roadmap.txt")
        return tpl.replace("{{PAYLOAD}}", json.dumps(payload, indent=2))

    def exec(self, assessment: dict) -> str:
        import json
        tpl = _load("exec.txt")
        return tpl.replace("{{ASSESSMENT}}", json.dumps(assessment, indent=2))

    def implementation(self, initiative: dict) -> str:
        import json
        tpl = _load("implementation.txt")
        return tpl.replace("{{INITIATIVE}}", json.dumps(initiative, indent=2))

    def readiness(self, assessment: dict) -> str:
        import json
        tpl = _load("readiness.txt")
        return tpl.replace("{{ASSESSMENT}}", json.dumps(assessment, indent=2))

    def smart_questions(self, assessment: dict) -> str:
        import json
        tpl = _load("smart_questions.txt")
        return tpl.replace("{{ASSESSMENT}}", json.dumps(assessment, indent=2))

    def target_architecture(self, assessment: dict) -> str:
        import json
        tpl = _load("target_architecture.txt")
        return tpl.replace("{{ASSESSMENT}}", json.dumps(assessment, indent=2))

    def grounding(self, grounding_context: dict) -> str:
        import json
        tpl = _load("grounding.txt")
        return (
            tpl
            .replace("{{ initiatives_json }}", json.dumps(
                grounding_context.get("initiatives", []), indent=2))
            .replace("{{ gaps_json }}", json.dumps(
                grounding_context.get("gaps", []), indent=2))
            .replace("{{ execution_units_json }}", json.dumps(
                grounding_context.get("target_execution_units", []), indent=2))
        )
