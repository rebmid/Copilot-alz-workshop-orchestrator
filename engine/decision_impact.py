"""Decision Impact Model — per-initiative "what breaks if not implemented".

Computes enterprise_scale_blocked, critical_risks_remaining,
fail_controls_remaining, blocked_initiatives, and maturity_ceiling
from deterministic joins of initiatives, results, risks, and blockers.

Layer: Derived models (deterministic joins only — no creative logic).
"""
from __future__ import annotations

from engine.guardrails import (
    empty_evidence_refs,
    compute_derived_confidence,
    insufficient_evidence_marker,
)

from schemas.taxonomy import BLOCKER_CATEGORY_TO_SECTIONS


def _build_initiative_index(initiatives: list[dict]) -> dict:
    """Map initiative_id → initiative dict."""
    return {
        init.get("initiative_id", ""): init
        for init in initiatives
        if init.get("initiative_id")
    }


def _build_dependency_reverse_map(initiatives: list[dict]) -> dict[str, list[str]]:
    """Map initiative_id → list of initiative_ids that depend on it."""
    reverse: dict[str, list[str]] = {}
    for init in initiatives:
        iid = init.get("initiative_id", "")
        for dep in init.get("dependencies", []):
            reverse.setdefault(dep, []).append(iid)
    return reverse


def _controls_for_initiative(initiative: dict) -> set[str]:
    """Extract control_id set from an initiative."""
    return set(initiative.get("controls", []))


# Use canonical mapping from schemas.taxonomy
_BLOCKER_CATEGORY_TO_SECTIONS = BLOCKER_CATEGORY_TO_SECTIONS


def resolve_blockers_to_initiatives(
    blockers: list[dict],
    initiatives: list[dict],
    results: list[dict],
) -> dict[str, str | None]:
    """
    Deterministically resolve blockers to initiatives via control overlap.

    For each blocker:
      1. If the blocker has affected_controls, find the initiative whose
         controls overlap most with those affected controls.
      2. If no affected_controls, match by category → section → initiative
         with the most failing controls in that section.
      3. Falls back to LLM-declared resolving_initiative only if no
         deterministic match is found AND the LLM reference is valid.

    Returns: dict of blocker_key → initiative_id (or None if unmappable)
    """
    results_by_id = {r.get("control_id", ""): r for r in results if r.get("control_id")}

    # Build initiative → controls set index
    init_controls_map: dict[str, set[str]] = {}
    for init in initiatives:
        iid = init.get("initiative_id", "")
        if iid:
            init_controls_map[iid] = set(init.get("controls", []))

    # Build initiative → sections covered
    init_sections: dict[str, set[str]] = {}
    for init in initiatives:
        iid = init.get("initiative_id", "")
        if not iid:
            continue
        sections = set()
        for ctrl_id in init.get("controls", []):
            ctrl = results_by_id.get(ctrl_id, {})
            sec = ctrl.get("section", "")
            if sec:
                sections.add(sec)
        init_sections[iid] = sections

    valid_init_ids = set(init_controls_map.keys())

    blocker_init_map: dict[str, str | None] = {}

    for b in blockers:
        raw_key = b.get("category", "") or b.get("description", "")
        if not raw_key:
            continue
        # Normalize key to lowercase — patch_blocker_initiatives also
        # lowercases the category at lookup time.
        blocker_key = raw_key.lower()

        # Strategy 1: Match by affected_controls overlap
        affected = set(b.get("affected_controls", []))
        if affected:
            best_init = None
            best_overlap = 0
            for iid, ctrl_set in init_controls_map.items():
                overlap = len(affected & ctrl_set)
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_init = iid
            if best_init:
                blocker_init_map[blocker_key] = best_init
                continue

        # Strategy 2: Match by category → section → initiative with most
        # failing controls in that section
        category = blocker_key  # already lowercase
        target_sections = _BLOCKER_CATEGORY_TO_SECTIONS.get(category, [])
        if target_sections:
            best_init = None
            best_fail_count = 0
            for iid, ctrl_set in init_controls_map.items():
                # Count failing controls in target sections
                fail_count = 0
                for ctrl_id in ctrl_set:
                    ctrl = results_by_id.get(ctrl_id, {})
                    if (ctrl.get("section", "") in target_sections
                            and ctrl.get("status") in ("Fail", "Partial")):
                        fail_count += 1
                if fail_count > best_fail_count:
                    best_fail_count = fail_count
                    best_init = iid
            if best_init:
                blocker_init_map[blocker_key] = best_init
                continue

            # Also try matching by initiative section coverage
            for iid, sections in init_sections.items():
                if any(ts in sections for ts in target_sections):
                    blocker_init_map[blocker_key] = iid
                    break
            if blocker_key in blocker_init_map:
                continue

        # Strategy 3: Fallback to LLM-declared resolving_initiative
        # (only if the referenced initiative actually exists)
        llm_ref = b.get("resolving_initiative", "")
        if llm_ref and llm_ref in valid_init_ids:
            blocker_init_map[blocker_key] = llm_ref
            continue

        # No deterministic match — set null
        blocker_init_map[blocker_key] = None

    return blocker_init_map


def _count_risks_for_controls(
    control_ids: set[str],
    top_risks: list[dict],
) -> int:
    """Count how many top business risks overlap with a set of controls."""
    count = 0
    for risk in top_risks:
        affected = set(risk.get("affected_controls", []))
        if affected & control_ids:
            count += 1
    return count


def _affected_risk_titles(
    control_ids: set[str],
    top_risks: list[dict],
) -> list[str]:
    """Return titles of risks that overlap with control_ids."""
    titles = []
    for risk in top_risks:
        affected = set(risk.get("affected_controls", []))
        if affected & control_ids:
            titles.append(risk.get("title", "unnamed risk"))
    return titles


def _maturity_ceiling_if_skipped(
    initiative: dict,
    results: list[dict],
    section_scores: list[dict],
) -> str:
    """
    Compute a human-readable maturity ceiling statement.

    If we skip this initiative, the affected design area(s) cannot
    improve beyond their current maturity.
    """
    init_controls = set(initiative.get("controls", []))
    if not init_controls:
        return insufficient_evidence_marker()

    # Find which sections are affected
    affected_sections: dict[str, int] = {}
    for r in results:
        if r.get("control_id") in init_controls and r.get("status") == "Fail":
            section = r.get("section") or r.get("alz_design_area") or "Unknown"
            affected_sections[section] = affected_sections.get(section, 0) + 1

    if not affected_sections:
        return "No failing controls in this initiative — maturity ceiling not impacted."

    # Map to current maturity
    section_maturity = {
        s.get("section") or s.get("alz_design_area", ""): s.get("maturity_percent", 0)
        for s in section_scores
    }

    parts = []
    for section, fail_count in sorted(affected_sections.items(), key=lambda x: -x[1]):
        current = section_maturity.get(section, 0)
        parts.append(f"{section} capped at ~{current:.0f}% ({fail_count} failing controls unresolved)")

    return "; ".join(parts)


def build_decision_impact_model(
    initiatives: list[dict],
    results: list[dict],
    top_risks: list[dict],
    blockers: list[dict],
    section_scores: list[dict],
    signals: dict | None = None,
) -> dict:
    """
    Build the decision impact model: per-initiative "if not implemented" analysis.

    Every item includes evidence_refs and assumptions. No freeform inference.

    Parameters
    ----------
    initiatives : list[dict]
        Initiative list from roadmap pass.
    results : list[dict]
        Assessment control results.
    top_risks : list[dict]
        Top business risks from executive pass.
    blockers : list[dict]
        Enterprise readiness blockers.
    section_scores : list[dict]
        Per-section maturity scores.
    signals : dict | None
        Signal data for evidence linking.

    Returns
    -------
    dict conforming to decision_impact_model schema.
    """
    init_index = _build_initiative_index(initiatives)
    dep_reverse = _build_dependency_reverse_map(initiatives)

    # Build blocker → initiative mapping (DETERMINISTIC)
    # Instead of trusting LLM-generated resolving_initiative,
    # we derive the mapping from control overlap:
    # A blocker maps to an initiative whose controls include any of
    # the blocker's affected controls, or whose section/category matches.
    blocker_init_map = resolve_blockers_to_initiatives(blockers, initiatives, results)

    items = []
    for init in initiatives:
        iid = init.get("initiative_id", "")
        init_controls = _controls_for_initiative(init)

        # Controls that remain failing
        fail_controls = [
            r.get("control_id", "")
            for r in results
            if r.get("control_id") in init_controls and r.get("status") == "Fail"
        ]
        fail_controls = [c for c in fail_controls if c]

        # Risks that remain
        risk_titles = _affected_risk_titles(init_controls, top_risks)

        # Blocked downstream initiatives
        blocked = dep_reverse.get(iid, [])

        # Enterprise-scale blocked: if this initiative resolves a blocker
        resolves_blockers = [
            cat for cat, res_init in blocker_init_map.items()
            if res_init == iid and res_init is not None
        ]
        enterprise_blocked = len(resolves_blockers) > 0

        # Maturity ceiling
        ceiling = _maturity_ceiling_if_skipped(init, results, section_scores)

        # Confidence: average of underlying control confidences.
        # Only include controls that actually have a confidence_score.
        # Do NOT substitute a default — missing means missing.
        ctrl_confidences = [
            r["confidence_score"]
            for r in results
            if r.get("control_id") in init_controls
            and "confidence_score" in r
            and isinstance(r["confidence_score"], (int, float))
        ]
        # Signal coverage for this initiative's signals
        init_signals = set()
        for r in results:
            if r.get("control_id") in init_controls:
                init_signals.update(r.get("signals_used", []))
        signals_dict = signals or {}
        covered = sum(1 for s in init_signals if signals_dict.get(s))
        signal_pct = (covered / max(len(init_signals), 1)) * 100

        confidence = compute_derived_confidence(list(map(float, ctrl_confidences)), signal_pct)

        item = {
            "initiative_id": iid,
            "if_not_implemented": {
                "enterprise_scale_blocked": enterprise_blocked,
                "critical_risks_remaining": len(risk_titles),
                "fail_controls_remaining": len(fail_controls),
                "blocked_initiatives": blocked,
                "maturity_ceiling_notes": ceiling,
            },
            "confidence": confidence,
            "evidence_refs": {
                "controls": list(init_controls)[:15] if init_controls else fail_controls[:15],
                "risks": risk_titles[:5],
                "blockers": resolves_blockers[:5],
                "signals": [f"signal:{s}" for s in sorted(init_signals)[:10]],
                "mcp_queries": [],
            },
            "assumptions": [
                "Impact computed from current assessment results",
                "Assumes no partial implementation or alternative mitigations",
            ],
        }

        items.append(item)

    return {
        "items": items,
    }
