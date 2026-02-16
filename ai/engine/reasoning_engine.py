"""Reasoning Engine — orchestrates all AI advisory passes into a unified output."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from ai.engine.reasoning_provider import ReasoningProvider
from ai.prompts import PromptPack
from ai.mcp_retriever import (
    ground_initiatives,
    ground_gaps,
    ground_target_architecture,
    build_grounding_context,
    ground_all_design_areas,
    build_alz_grounding_block,
)
from alz.loader import (
    ALZ_DESIGN_AREAS,
    build_prompt_checklist_context,
    get_design_area_learn_urls,
)


class ReasoningEngine:
    """
    Orchestrates the full AI advisory pipeline:
      1. Roadmap + Initiatives  (roadmap prompt)
      2. Executive briefing     (exec prompt)
      3. Enterprise readiness   (readiness prompt)
      4. Smart questions        (smart_questions prompt)
      5. Implementation backlog (implementation prompt × N)
      6. Learn reference grounding (MCP retriever)
      7. Progress analysis      (derived from delta)

    The provider is model-agnostic — swap AOAIReasoningProvider for
    PhiReasoningProvider or MockReasoningProvider in one line.

    Returns a dict conforming to the advisor output schema.
    """

    def __init__(self, provider: ReasoningProvider, prompts: PromptPack | None = None):
        self.provider = provider
        self.prompts = prompts or PromptPack()

    # ──────────────────────────────────────────────────────────────
    # ──────────────────────────────────────────────────────────────
    # Intent-level convenience methods
    # ──────────────────────────────────────────────────────────────

    def explain_intent(self, intent_result: dict) -> dict:
        """Generate a natural-language explanation for an intent result."""
        template = self.prompts.system + "\n---SYSTEM---\n" + self.prompts.exec(intent_result)
        return self.provider.complete(template, intent_result)

    def build_roadmap(self, assessment_data: dict) -> dict:
        """Generate a transformation roadmap from assessment data."""
        template = self.prompts.system + "\n---SYSTEM---\n" + self.prompts.roadmap(assessment_data)
        return self.provider.complete(template, assessment_data)

    def target_architecture(self, assessment_data: dict) -> dict:
        """Generate target architecture conforming to target_architecture.schema.json."""
        template = self.prompts.system + "\n---SYSTEM---\n" + self.prompts.target_architecture(assessment_data)
        return self.provider.complete(template, assessment_data, max_tokens=8000)

    # ──────────────────────────────────────────────────────────────
    # Full pipeline entry point
    # ──────────────────────────────────────────────────────────────
    def generate(
        self,
        assessment: dict,
        *,
        run_id: str = "",
        tenant_id: str = "",
        skip_implementation: bool = False,
    ) -> dict[str, Any]:
        """
        Run the full pipeline.

        Parameters
        ----------
        assessment : dict
            The advisor payload from build_advisor_payload().
        run_id : str
            Current scan run ID for meta.
        tenant_id : str
            Tenant ID for meta.
        skip_implementation : bool
            Skip the per-initiative implementation pass (saves tokens).
        """
        system = self.prompts.system

        # ── 0. ALZ checklist grounding context ────────────────────
        # Inject official ALZ design area references + checklist items
        # into the system prompt so every LLM call is anchored to
        # the authoritative Azure/review-checklists repo.
        print("  [0/7] Loading ALZ checklist grounding context …")
        try:
            alz_block = build_alz_grounding_block()
            alz_checklist_ctx = build_prompt_checklist_context(max_items=40)
            system = f"{system}\n\n{alz_block}\n\n{alz_checklist_ctx}"
            print(f"        → ALZ context injected ({len(ALZ_DESIGN_AREAS)} design areas)")
        except Exception as e:
            print(f"  ⚠ ALZ checklist grounding skipped: {e}")

        # ── 1. Roadmap + Initiatives ──────────────────────────────
        print("  [1/6] Generating roadmap & initiatives …")
        roadmap_raw = self._safe_run(
            system,
            self.prompts.roadmap(assessment),
            label="Roadmap",
            max_tokens=8000,
        )

        initiatives = roadmap_raw.get("initiative_execution_plan", [])
        print(f"        → {len(initiatives)} initiative(s)")

        # ── 2. Executive briefing ─────────────────────────────────
        print("  [2/6] Generating executive briefing …")
        executive = self._safe_run(
            system,
            self.prompts.exec(assessment),
            label="Executive",
            max_tokens=8000,
        )

        # ── 3. Enterprise-scale readiness ─────────────────────────
        print("  [3/6] Evaluating enterprise-scale readiness …")
        # Enrich assessment with initiative IDs so readiness can reference them
        readiness_input = {**assessment, "initiative_ids": [i["initiative_id"] for i in initiatives]}
        readiness = self._safe_run(
            system,
            self.prompts.readiness(readiness_input),
            label="Readiness",
            max_tokens=8000,
        )

        # ── 4. Smart questions ────────────────────────────────────
        print("  [4/6] Generating smart questions …")
        sq_raw = self._safe_run(
            system,
            self.prompts.smart_questions(assessment),
            label="Smart Questions",
            max_tokens=8000,
        )
        smart_questions = sq_raw.get("smart_questions", [])
        print(f"        → {len(smart_questions)} question(s)")

        # ── 5. Implementation backlog ─────────────────────────────
        implementation_backlog: list[dict] = []
        if not skip_implementation and initiatives:
            print(f"  [5/6] Generating implementation for {len(initiatives)} initiative(s) …")
            for init in initiatives:
                impl = self._safe_run(
                    system,
                    self.prompts.implementation(init),
                    label=f"Impl:{init.get('initiative_id', '?')}",
                )
                implementation_backlog.append(impl)
        else:
            print("  [5/6] Implementation backlog skipped.")

        # ── 6. Learn reference grounding (ALZ-design-area-aware) ──
        print("  [6/7] Grounding initiatives with Microsoft Learn (ALZ-aware) …")
        enriched_initiatives = ground_initiatives(initiatives)

        # Also ground the top gaps used in executive — scoped to ALZ areas
        top_gaps = assessment.get("most_impactful_gaps", [])[:10]
        grounded_refs = ground_gaps(top_gaps)

        # Pre-ground all 8 ALZ design areas for comprehensive coverage
        try:
            design_area_refs = ground_all_design_areas(top_per_area=2)
            print(f"        → {sum(len(v) for v in design_area_refs.values())} ALZ design area refs")
        except Exception as e:
            print(f"  ⚠ ALZ design area grounding skipped: {e}")
            design_area_refs = {}

        # ── 7. Target architecture ─────────────────────────────────
        print("  [7/7] Generating target architecture …")
        target_arch = self._safe_run(
            system,
            self.prompts.target_architecture(assessment),
            label="Target Architecture",
            max_tokens=8000,
        )

        # Ground target architecture execution units with Learn refs
        if target_arch:
            print("        Grounding target architecture execution units …")
            target_arch = ground_target_architecture(target_arch)

        # ── AI-enriched grounding (contextualise refs via LLM) ────
        grounding_ctx = build_grounding_context(
            enriched_initiatives, grounded_refs, target_arch,
        )
        if any(grounding_ctx.get(k) for k in grounding_ctx):
            print("        Enriching grounding with AI contextualisation …")
            enriched_grounding = self._safe_run(
                system,
                self.prompts.grounding(grounding_ctx),
                label="Grounding Enrichment",
                max_tokens=8000,
            )
        else:
            enriched_grounding = {}

        # ── Progress analysis (derived, no AOAI call) ─────────────
        progress = self._derive_progress(assessment)

        # ── Assemble unified output ───────────────────────────────
        output: dict[str, Any] = {
            "meta": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "assessment_run_id": run_id,
                "tenant_id": tenant_id,
            },
            "executive": executive,
            "enterprise_scale_readiness": readiness,
            "transformation_roadmap": {
                "roadmap_30_60_90": roadmap_raw.get("roadmap_30_60_90", {}),
                "dependency_graph": roadmap_raw.get("dependency_graph", []),
                "critical_path": roadmap_raw.get("critical_path", []),
                "parallel_execution_groups": roadmap_raw.get("parallel_execution_groups", []),
                "maturity_trajectory": roadmap_raw.get("maturity_trajectory", {}),
            },
            "initiatives": enriched_initiatives,
            "implementation_backlog": implementation_backlog,
            "smart_questions": smart_questions,
            "target_architecture": target_arch,
            "grounding": enriched_grounding,
            "alz_design_area_references": design_area_refs,
            "alz_design_area_urls": get_design_area_learn_urls(),
            "progress_analysis": progress,
            # Keep raw blocks for backwards compatibility
            "_raw": {
                "roadmap": roadmap_raw,
                "grounded_refs": grounded_refs,
                "grounding_context": grounding_ctx,
            },
        }

        print(f"\n  ✓ Reasoning engine complete — {len(enriched_initiatives)} initiatives, "
              f"{len(smart_questions)} questions, "
              f"{len(implementation_backlog)} implementation plans, "
              f"target architecture {'generated' if target_arch else 'skipped'}")

        return output

    # ──────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────
    def _safe_run(self, system: str, user: str, *, label: str = "", payload: dict | None = None, max_tokens: int | None = None) -> dict:
        """Call provider; return empty dict on failure instead of crashing."""
        try:
            # Pack system + user into the template contract
            template = f"{system}\n---SYSTEM---\n{user}"
            kwargs: dict[str, Any] = {}
            if max_tokens is not None:
                kwargs["max_tokens"] = max_tokens
            return self.provider.complete(template, payload or {}, **kwargs)
        except Exception as e:
            print(f"  ✗ {label} failed: {e}")
            return {}

    @staticmethod
    def _derive_progress(assessment: dict) -> dict:
        """Derive velocity / trend from delta without an AOAI call."""
        delta = assessment.get("delta") or {}
        if not delta.get("has_previous", False):
            return {
                "velocity": "stalled",
                "maturity_trend": "No previous run — baseline established.",
                "recommended_next_initiative": "",
            }

        changed = delta.get("count", 0)
        improvements = sum(
            1 for c in delta.get("changed_controls", [])
            if c.get("new_status") == "Pass" and c.get("old_status") == "Fail"
        )
        regressions = sum(
            1 for c in delta.get("changed_controls", [])
            if c.get("new_status") == "Fail" and c.get("old_status") == "Pass"
        )

        if improvements > regressions:
            velocity = "progressing"
            trend = f"{improvements} control(s) improved, {regressions} regressed ({changed} total changes)."
        elif regressions > improvements:
            velocity = "regressing"
            trend = f"{regressions} control(s) regressed, {improvements} improved ({changed} total changes)."
        else:
            velocity = "stalled"
            trend = f"{changed} changes but no net improvement."

        return {
            "velocity": velocity,
            "maturity_trend": trend,
            "recommended_next_initiative": "",
        }
