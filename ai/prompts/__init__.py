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

    # ── New: Architectural Decision Support prompts ───────────────

    def implementation_decision(
        self,
        initiatives_with_options: list[dict],
        assessment_context: dict,
    ) -> str:
        import json
        tpl = _load("implementation_decision.txt")
        return (
            tpl
            .replace("{{INITIATIVES_WITH_OPTIONS}}", json.dumps(initiatives_with_options, indent=2))
            .replace("{{ASSESSMENT_CONTEXT}}", json.dumps(assessment_context, indent=2))
        )

    def sequence_justification(
        self,
        initiatives_with_decisions: list[dict],
        dependency_order: list[str],
        assessment_context: dict,
    ) -> str:
        import json
        tpl = _load("sequence_justification.txt")
        return (
            tpl
            .replace("{{INITIATIVES_WITH_DECISIONS}}", json.dumps(initiatives_with_decisions, indent=2))
            .replace("{{DEPENDENCY_ORDER}}", json.dumps(dependency_order, indent=2))
            .replace("{{ASSESSMENT_CONTEXT}}", json.dumps(assessment_context, indent=2))
        )

    def critical_issues(
        self,
        critical_controls: list[dict],
        assessment_context: dict,
    ) -> str:
        import json
        tpl = _load("critical_issues.txt")
        return (
            tpl
            .replace("{{CRITICAL_CONTROLS}}", json.dumps(critical_controls, indent=2))
            .replace("{{ASSESSMENT_CONTEXT}}", json.dumps(assessment_context, indent=2))
        )

    def blocker_resolution(
        self,
        blocker_mapping: dict,
        blockers: list[dict],
        remediation_items: list[dict],
        dependency_graph: dict,
        maturity_trajectory: dict,
    ) -> str:
        import json
        tpl = _load("blocker_resolution.txt")
        return (
            tpl
            .replace("{{BLOCKER_MAPPING}}", json.dumps(blocker_mapping, indent=2))
            .replace("{{BLOCKERS}}", json.dumps(blockers, indent=2))
            .replace("{{REMEDIATION_ITEMS}}", json.dumps(remediation_items, indent=2))
            .replace("{{DEPENDENCY_GRAPH}}", json.dumps(dependency_graph, indent=2))
            .replace("{{MATURITY_TRAJECTORY}}", json.dumps(maturity_trajectory, indent=2))
        )

    def governance_intelligence(
        self,
        dependency_graph: dict,
        risk_impact: dict,
        transform_optimization: dict,
        maturity_trajectory: dict,
        implementation_decisions: list[dict],
        executive: dict,
        assessment_context: dict,
    ) -> str:
        import json
        tpl = _load("governance_intelligence.txt")
        return (
            tpl
            .replace("{{DEPENDENCY_GRAPH}}", json.dumps(dependency_graph, indent=2))
            .replace("{{RISK_IMPACT_MODEL}}", json.dumps(risk_impact, indent=2))
            .replace("{{TRANSFORM_OPTIMIZATION}}", json.dumps(transform_optimization, indent=2))
            .replace("{{MATURITY_TRAJECTORY}}", json.dumps(maturity_trajectory, indent=2))
            .replace("{{IMPLEMENTATION_DECISIONS}}", json.dumps(implementation_decisions, indent=2))
            .replace("{{EXECUTIVE_BRIEFING}}", json.dumps(executive, indent=2))
            .replace("{{ASSESSMENT_CONTEXT}}", json.dumps(assessment_context, indent=2))
        )
