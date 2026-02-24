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
    get_alz_implementation_options,
)
from alz.loader import (
    ALZ_DESIGN_AREAS,
    build_prompt_checklist_context,
    get_design_area_learn_urls,
)
from engine.guardrails import validate_anti_drift
from engine.scaling_rules import build_scaling_simulation
from engine.drift_model import build_drift_model
from engine.cost_simulation import build_cost_simulation
from engine.decision_impact import build_decision_impact_model, resolve_blockers_to_items
from engine.dependency_engine import build_initiative_dependency_graph, reorder_roadmap_phases
from engine.risk_impact import build_risk_impact_model
from engine.transform_optimizer import build_transformation_optimization
from engine.maturity_trajectory import compute_maturity_trajectory
from graph.knowledge_graph import ControlKnowledgeGraph


class ReasoningEngine:
    """
    Orchestrates the full AI advisory pipeline:
      0. ALZ checklist grounding (deterministic)
      1. Roadmap + Initiatives         (roadmap prompt)
      2. Executive briefing             (exec prompt)
      3. Implementation Decision        (MCP + implementation_decision prompt) ← NEW
      4. Sequence Justification         (sequence_justification prompt)        ← NEW
      5. Enterprise readiness           (readiness prompt)
      6. Smart questions                (smart_questions prompt)
      7. Implementation backlog         (implementation prompt × N)
      8. Learn reference grounding      (MCP retriever)
      9. Target architecture            (target_architecture prompt)

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
        total_passes = 9

        # ── 0. ALZ checklist grounding context ────────────────────
        # Inject official ALZ design area references + checklist items
        # into the system prompt so every LLM call is anchored to
        # the authoritative Azure/review-checklists repo.
        print(f"  [0/{total_passes}] Loading ALZ checklist grounding context …")
        try:
            alz_block = build_alz_grounding_block()
            alz_checklist_ctx = build_prompt_checklist_context(max_items=40)
            system = f"{system}\n\n{alz_block}\n\n{alz_checklist_ctx}"
            print(f"        → ALZ context injected ({len(ALZ_DESIGN_AREAS)} design areas)")
        except Exception as e:
            print(f"  ⚠ ALZ checklist grounding skipped: {e}")

        # ── 1. Roadmap + Remediation Items ────────────────────
        print(f"  [1/{total_passes}] Generating roadmap & remediation items …")
        roadmap_raw = self._safe_run(
            system,
            self.prompts.roadmap(assessment),
            label="Roadmap",
            max_tokens=8000,
        )

        # Accept new key (remediation_plan) with fallback to legacy key
        items = roadmap_raw.get("remediation_plan",
                                roadmap_raw.get("initiative_execution_plan", []))
        print(f"        → {len(items)} remediation item(s)")

        # ── 2. Executive briefing ─────────────────────────────────
        print(f"  [2/{total_passes}] Generating executive briefing …")
        executive = self._safe_run(
            system,
            self.prompts.exec(assessment),
            label="Executive",
            max_tokens=8000,
        )

        # ── 3. Implementation Decision (NEW) ─────────────────────
        # For each initiative, retrieve ALZ implementation options via MCP
        # then ask the LLM to select and justify the right pattern.
        implementation_decisions: list[dict] = []
        if items:
            print(f"  [3/{total_passes}] Selecting ALZ implementation patterns ({len(items)} items) …")
            items_with_options = []
            for item in items:
                try:
                    options = get_alz_implementation_options(item, assessment)
                except Exception as e:
                    print(f"        ⚠ MCP pattern retrieval failed for '{item.get('title', '?')[:40]}': {e}")
                    options = []
                items_with_options.append({
                    **item,
                    "available_patterns": options,
                })

            # Build assessment context subset for the decision prompt
            decision_context = {
                "design_area_maturity": assessment.get("design_area_maturity", []),
                "platform_scale_limits": assessment.get("platform_scale_limits", {}),
                "signal_confidence": assessment.get("signal_confidence", {}),
                "execution_context": assessment.get("execution_context", {}),
                "dependency_order": assessment.get("dependency_order", []),
            }

            decision_raw = self._safe_run(
                system,
                self.prompts.implementation_decision(
                    items_with_options, decision_context
                ),
                label="Implementation Decision",
                max_tokens=8000,
            )
            implementation_decisions = decision_raw.get("implementation_decisions", [])
            print(f"        → {len(implementation_decisions)} pattern decision(s)")

            # Merge decisions back into items for downstream passes
            decision_map = {
                d.get("checklist_id", d.get("initiative_id", "")): d
                for d in implementation_decisions
                if d.get("checklist_id") or d.get("initiative_id")
            }
            for item in items:
                cid = item.get("checklist_id", item.get("initiative_id", ""))
                if cid in decision_map:
                    item["selected_pattern"] = decision_map[cid].get("recommended_pattern", "")
                    item["alz_module"] = decision_map[cid].get("alz_module", "")
                    item["capability_unlocked"] = decision_map[cid].get("capability_unlocked", "")
                    item["prerequisites_missing"] = decision_map[cid].get("prerequisites_missing", [])
        else:
            print(f"  [3/{total_passes}] Implementation Decision skipped (no items).")

        # ── 4. Sequence Justification (NEW) ───────────────────────
        # Explain WHY initiatives are ordered this way in platform terms.
        sequence_justification: dict = {}
        engagement_recommendations: list[dict] = []
        if items and implementation_decisions:
            print(f"  [4/{total_passes}] Generating sequence justification …")
            seq_context = {
                "design_area_maturity": assessment.get("design_area_maturity", []),
                "platform_scale_limits": assessment.get("platform_scale_limits", {}),
                "execution_context": assessment.get("execution_context", {}),
            }
            seq_raw = self._safe_run(
                system,
                self.prompts.sequence_justification(
                    implementation_decisions,
                    assessment.get("dependency_order", []),
                    seq_context,
                ),
                label="Sequence Justification",
                max_tokens=8000,
            )
            sequence_justification = seq_raw
            engagement_recommendations = seq_raw.get("engagement_recommendations", [])
            print(f"        → {len(engagement_recommendations)} engagement recommendation(s)")
        else:
            print(f"  [4/{total_passes}] Sequence Justification skipped.")

        # ── 5. Enterprise-scale readiness ─────────────────────────
        print(f"  [5/{total_passes}] Evaluating enterprise-scale readiness …")
        # Enrich assessment with checklist IDs so readiness can reference them
        readiness_input = {
            **assessment,
            "checklist_ids": [i.get("checklist_id", i.get("initiative_id", "")) for i in items],
        }
        readiness = self._safe_run(
            system,
            self.prompts.readiness(readiness_input),
            label="Readiness",
            max_tokens=8000,
        )

        # Clamp readiness_score to valid range
        from engine.id_rewriter import clamp_readiness_score
        clamp_readiness_score(readiness)

        # ── 6. Smart questions ────────────────────────────────────
        print(f"  [6/{total_passes}] Generating smart questions …")
        sq_raw = self._safe_run(
            system,
            self.prompts.smart_questions(assessment),
            label="Smart Questions",
            max_tokens=8000,
        )
        smart_questions = sq_raw.get("smart_questions", [])
        print(f"        → {len(smart_questions)} question(s)")

        # ── 7. Implementation backlog ─────────────────────────────
        implementation_backlog: list[dict] = []
        if not skip_implementation and items:
            print(f"  [7/{total_passes}] Generating implementation for {len(items)} item(s) …")
            for item in items:
                impl = self._safe_run(
                    system,
                    self.prompts.implementation(item),
                    label=f"Impl:{item.get('checklist_id', item.get('initiative_id', '?'))}",
                )
                implementation_backlog.append(impl)
        else:
            print(f"  [7/{total_passes}] Implementation backlog skipped.")

        # ── 8. Learn reference grounding (ALZ-design-area-aware) ──
        print(f"  [8/{total_passes}] Grounding items with Microsoft Learn (ALZ-aware) …")
        enriched_items = ground_initiatives(items)

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

        # ── 8b. Checklist grounding (authority: Azure/review-checklists) ──
        # Derive checklist references for each item from its controls'
        # checklist_ids.  This is deterministic — no AI involved.
        from alz.checklist_grounding import (
            ground_initiatives_to_checklist,
            validate_checklist_coverage,
        )
        try:
            ground_initiatives_to_checklist(enriched_items)
            _checklist_violations = validate_checklist_coverage(enriched_items)
            _grounded_count = sum(
                1 for i in enriched_items
                if i.get("derived_from_checklist")
            )
            print(f"        → checklist grounding: {_grounded_count}/{len(enriched_items)} items grounded")
            if _checklist_violations:
                for v in _checklist_violations:
                    print(f"        ⚠ {v}")
        except Exception as e:
            print(f"  ⚠ Checklist grounding failed: {e}")
            _checklist_violations = []

        # ── 9. Target architecture ─────────────────────────────────
        print(f"  [9/{total_passes}] Generating target architecture …")
        # Enrich assessment with selected patterns so target arch derives from decisions
        arch_input = {
            **assessment,
            "implementation_decisions": implementation_decisions,
        }
        target_arch = self._safe_run(
            system,
            self.prompts.target_architecture(arch_input),
            label="Target Architecture",
            max_tokens=8000,
        )

        # Ground target architecture execution units with Learn refs
        if target_arch:
            print("        Grounding target architecture execution units …")
            target_arch = ground_target_architecture(target_arch)

        # ── AI-enriched grounding (contextualise refs via LLM) ────
        grounding_ctx = build_grounding_context(
            enriched_items, grounded_refs, target_arch,
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

        # ── Anti-drift derived models (deterministic, no AOAI) ────
        # Extract signals and results from the assessment payload
        # so the derived-model builders can work from factual data.
        _signals = assessment.get("signals", {})
        _results = assessment.get("results", [])
        _exec_ctx = assessment.get("execution_context", {})
        _section_scores = assessment.get("design_area_maturity", [])
        _top_risks = (executive or {}).get("top_business_risks", [])
        _blockers = (readiness or {}).get("blockers", [])

        print("  [derived] Building anti-drift models …")

        try:
            scaling_sim = build_scaling_simulation(_results, _signals, _exec_ctx)
            print(f"        → scaling_simulation: {sum(len(s.get('derived_impacts', [])) for s in scaling_sim.get('scenarios', []))} impacts across {len(scaling_sim.get('scenarios', []))} scenarios")
        except Exception as e:
            print(f"  ⚠ scaling_simulation failed: {e}")
            scaling_sim = {"scenarios": []}

        try:
            drift = build_drift_model(_results, _signals, _signals.get("activity_log"))
            print(f"        → drift_model: {drift.get('drift_likelihood', '?')} likelihood (score={drift.get('drift_score', '?')})")
        except Exception as e:
            print(f"  ⚠ drift_model failed: {e}")
            drift = {}

        try:
            cost_sim = build_cost_simulation(items, _results, mcp_pricing_available=False)
            print(f"        → cost_simulation: {len(cost_sim.get('drivers', []))} drivers ({cost_sim.get('mode', '?')})")
        except Exception as e:
            print(f"  ⚠ cost_simulation failed: {e}")
            cost_sim = {"mode": "category_only", "drivers": []}

        try:
            decision_impact = build_decision_impact_model(
                items, _results, _top_risks, _blockers, _section_scores, _signals,
            )
            print(f"        → decision_impact_model: {len(decision_impact.get('items', []))} items")
        except Exception as e:
            print(f"  ⚠ decision_impact_model failed: {e}")
            decision_impact = {"items": []}

        # ── 3-Layer Deterministic Decision Engine ─────────────────
        # Layer 1: Dependency Engine — strict architectural ordering
        # Layer 2: Risk Impact — executive framing (NO sequencing influence)
        # Layer 3: Transformation Optimizer — parallelization within dep boundaries
        # Plus: deterministic maturity trajectory & blocker resolution

        # Extract control-level dependencies from the knowledge graph
        # (full_id → [prerequisite full_ids]) for the dependency engine
        _control_deps: dict[str, list[str]] = {}
        try:
            _kg = ControlKnowledgeGraph()
            for _sid, _node in _kg.controls.items():
                _full_id = _node.full_id
                _prereq_full_ids = [
                    _kg.controls[p].full_id
                    for p in _node.depends_on
                    if p in _kg.controls
                ]
                if _prereq_full_ids:
                    _control_deps[_full_id] = _prereq_full_ids
        except Exception as e:
            print(f"  ⚠ Could not load control dependencies from KG: {e}")

        print("  [derived] Building 3-layer deterministic decision engine …")

        # Layer 1: Dependency Engine
        try:
            dep_graph = build_initiative_dependency_graph(
                items, control_dependencies=_control_deps or None,
            )
            print(f"        → dependency_engine: {len(dep_graph.get('item_order', dep_graph.get('initiative_order', [])))} items ordered, "
                  f"{len(dep_graph.get('dependency_violations', []))} violations detected")
        except Exception as e:
            print(f"  ⚠ dependency_engine failed: {e}")
            dep_graph = {"item_order": [], "item_deps": {}, "phase_assignment": {}, "parallel_groups": [], "dependency_violations": []}

        # Layer 2: Risk Impact (narrative only — NOT for sequencing)
        try:
            risk_impact = build_risk_impact_model(
                items, _results, _top_risks, _section_scores,
            )
            print(f"        → risk_impact: {len(risk_impact.get('items', []))} items, "
                  f"total maturity lift {risk_impact.get('summary', {}).get('total_maturity_lift_percent', 0):.1f}%")
        except Exception as e:
            print(f"  ⚠ risk_impact failed: {e}")
            risk_impact = {"items": [], "summary": {}}

        # Layer 3: Transformation Optimizer
        try:
            transform_opt = build_transformation_optimization(
                items, dep_graph, risk_impact, _results,
            )
            print(f"        → transform_optimizer: {len(transform_opt.get('quick_wins', []))} quick wins, "
                  f"{len(transform_opt.get('parallel_tracks', []))} parallel tracks")
        except Exception as e:
            print(f"  ⚠ transform_optimizer failed: {e}")
            transform_opt = {"quick_wins": [], "parallel_tracks": [], "optimization_notes": [], "effort_matrix": []}

        # Deterministic maturity trajectory
        _current_maturity = assessment.get("scoring", {}).get("overall_maturity_percent", 0.0)
        _total_controls = assessment.get("scoring", {}).get(
            "automation_coverage", {}
        ).get("total_controls", len(assessment.get("results", [])))
        try:
            det_trajectory = compute_maturity_trajectory(
                items, _results,
                phase_assignment=dep_graph.get("phase_assignment", {}),
                current_maturity_percent=_current_maturity,
                total_controls=_total_controls,
            )
            print(f"        → maturity_trajectory: {det_trajectory.get('current_percent', 0):.1f}% → "
                  f"{det_trajectory.get('post_90_day_percent', 0):.1f}% (90d)")
        except Exception as e:
            print(f"  ⚠ maturity_trajectory failed: {e}")
            det_trajectory = {}

        # Deterministic blocker → item resolution
        try:
            blocker_item_mapping = resolve_blockers_to_items(
                _blockers, items, _results,
            )
            print(f"        → blocker_mapping: {len(blocker_item_mapping)} blockers resolved")
        except Exception as e:
            print(f"  ⚠ blocker_mapping failed: {e}")
            blocker_item_mapping = {}

        # Patch readiness blockers with deterministic resolving_checklist_ids
        if blocker_item_mapping and readiness:
            from engine.id_rewriter import patch_blocker_items
            patch_blocker_items(readiness, blocker_item_mapping)

        # ── Pipeline integrity validation ──────────────────────────
        from engine.id_rewriter import validate_pipeline_integrity
        _pipeline_violations = validate_pipeline_integrity(
            readiness, enriched_items,
            blocker_item_mapping, decision_impact,
        )
        # Merge checklist grounding violations
        if _checklist_violations:
            _pipeline_violations.extend(_checklist_violations)

        # ── Assemble unified output ───────────────────────────────
        output: dict[str, Any] = {
            "meta": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "assessment_run_id": run_id,
                "tenant_id": tenant_id,
                "pipeline_version": "3.0-checklist-canonical",
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
            "remediation_items": enriched_items,
            "implementation_decisions": implementation_decisions,
            "sequence_justification": sequence_justification,
            "engagement_recommendations": engagement_recommendations,
            "implementation_backlog": implementation_backlog,
            "smart_questions": smart_questions,
            "target_architecture": target_arch,
            "grounding": enriched_grounding,
            "alz_design_area_references": design_area_refs,
            "alz_design_area_urls": get_design_area_learn_urls(),
            "progress_analysis": progress,
            # Anti-drift derived models (deterministic)
            "scaling_simulation": scaling_sim,
            "drift_model": drift,
            "cost_simulation": cost_sim,
            "decision_impact_model": decision_impact,
            # 3-Layer Deterministic Decision Engine
            "dependency_graph_model": dep_graph,
            "risk_impact_model": risk_impact,
            "transform_optimization": transform_opt,
            "deterministic_trajectory": det_trajectory,
            "blocker_item_mapping": blocker_item_mapping,
            # Pipeline structural integrity violations
            "_pipeline_violations": _pipeline_violations,
            # Keep raw blocks for backwards compatibility
            "_raw": {
                "roadmap": roadmap_raw,
                "grounded_refs": grounded_refs,
                "grounding_context": grounding_ctx,
            },
        }

        # ── Anti-drift validation ─────────────────────────────────
        drift_violations = validate_anti_drift(output)
        if drift_violations:
            print(f"\n  ⚠ Anti-drift guardrail violations ({len(drift_violations)}):")
            for v in drift_violations[:20]:
                print(f"    • {v}")
            output["_anti_drift_violations"] = drift_violations
        else:
            print("  ✓ Anti-drift validation passed — no violations")

        # ── Relationship integrity validation (Rule F) ────────────
        # Compiler-grade check: all blocker→item, item→controls,
        # roadmap→item, and derived_from_checklist references must be
        # structurally valid.  If not, violations are recorded.
        from engine.relationship_integrity import validate_relationship_integrity
        _ri_ok, _ri_violations = validate_relationship_integrity(output)
        if _ri_violations:
            _pipeline_violations.extend(_ri_violations)
            output["_pipeline_violations"] = _pipeline_violations
            output["_relationship_integrity"] = False
        else:
            output["_relationship_integrity"] = True

        print(f"\n  ✓ Reasoning engine complete — {len(enriched_items)} items, "
              f"{len(implementation_decisions)} pattern decisions, "
              f"{len(engagement_recommendations)} engagement recs, "
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
