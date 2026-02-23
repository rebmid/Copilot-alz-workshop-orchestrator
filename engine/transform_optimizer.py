"""Transformation Optimizer — parallelization and quick-win identification.

Layer 3 of the 3-layer deterministic decision engine.

Within the dependency boundaries set by Layer 1 (Dependency Engine),
this module identifies:
  - Quick wins: low-effort, high-impact initiatives that can start immediately
  - Parallel tracks: initiatives that can execute concurrently
  - Cost-control-first opportunities (only if no dependency violation)

This layer CANNOT override sequencing from the Dependency Engine.
It can only annotate and group within existing dependency constraints.
"""
from __future__ import annotations

from typing import Any


def build_transformation_optimization(
    initiatives: list[dict],
    dep_graph: dict[str, Any],
    risk_impact: dict[str, Any],
    results: list[dict],
) -> dict[str, Any]:
    """
    Build transformation optimization model.

    Parameters
    ----------
    initiatives : list[dict]
        Initiative list from roadmap pass.
    dep_graph : dict
        Output of build_initiative_dependency_graph() (Layer 1).
    risk_impact : dict
        Output of build_risk_impact_model() (Layer 2).
    results : list[dict]
        Assessment control results.

    Returns
    -------
    dict with:
      - quick_wins: list[dict]  — initiatives that are quick wins
      - parallel_tracks: list[dict]  — named parallel execution tracks
      - optimization_notes: list[str]  — advisory notes
      - effort_matrix: list[dict]  — per-initiative effort vs impact
    """
    init_index = {i.get("initiative_id", ""): i for i in initiatives}
    phase_assignment = dep_graph.get("phase_assignment", {})
    parallel_groups = dep_graph.get("parallel_groups", [])
    init_deps = dep_graph.get("initiative_deps", {})
    initiative_order = dep_graph.get("initiative_order", [])

    # Build impact lookup from risk_impact layer
    impact_by_id = {
        item["initiative_id"]: item
        for item in risk_impact.get("items", [])
    }

    # ── Quick wins ────────────────────────────────────────────────
    quick_wins = _identify_quick_wins(
        initiatives, phase_assignment, init_deps, impact_by_id
    )

    # ── Parallel tracks ───────────────────────────────────────────
    parallel_tracks = _build_parallel_tracks(
        parallel_groups, init_index, impact_by_id
    )

    # ── Effort vs Impact matrix ───────────────────────────────────
    effort_matrix = _build_effort_matrix(
        initiatives, impact_by_id, phase_assignment
    )

    # ── Optimization notes ────────────────────────────────────────
    optimization_notes = _generate_optimization_notes(
        initiatives, dep_graph, risk_impact, quick_wins
    )

    return {
        "quick_wins": quick_wins,
        "parallel_tracks": parallel_tracks,
        "effort_matrix": effort_matrix,
        "optimization_notes": optimization_notes,
    }


# ── Internal helpers ──────────────────────────────────────────────

def _identify_quick_wins(
    initiatives: list[dict],
    phase_assignment: dict[str, str],
    init_deps: dict[str, list[str]],
    impact_by_id: dict[str, dict],
) -> list[dict]:
    """
    Quick win criteria:
      - In 30_days phase (no blocking dependencies from prior phases)
      - No unresolved dependencies
      - Controls resolved > 0
      - Estimated effort is "short" (< 2 weeks or unspecified)
    """
    quick_wins = []

    for init in initiatives:
        iid = init.get("initiative_id", "")
        if not iid:
            continue

        phase = phase_assignment.get(iid, "90_days")
        deps = init_deps.get(iid, [])
        impact = impact_by_id.get(iid, {})
        controls_resolved = impact.get("controls_resolved", 0)

        # Must be in 30_days phase
        if phase != "30_days":
            continue

        # Must have no dependencies (root initiative)
        if deps:
            continue

        # Must resolve at least one control
        if controls_resolved == 0:
            continue

        # Effort check: short estimated duration
        delivery = init.get("delivery_model", {})
        duration = delivery.get("estimated_duration", "")
        is_quick = _is_short_duration(duration)

        if is_quick or not duration:
            quick_wins.append({
                "initiative_id": iid,
                "title": init.get("title", ""),
                "controls_resolved": controls_resolved,
                "risks_reduced": impact.get("risks_reduced", 0),
                "blast_radius": impact.get("blast_radius_label", "Low"),
                "reason": "No dependencies, immediate start, resolves failing controls",
            })

    return quick_wins


def _is_short_duration(duration: str) -> bool:
    """Heuristic: duration < 2 weeks is a quick win."""
    if not duration:
        return True
    dl = duration.lower()
    if any(x in dl for x in ("1 week", "1-2 week", "1–2 week", "< 2 week",
                               "days", "immediate", "1 day", "2 day", "3 day")):
        return True
    return False


def _build_parallel_tracks(
    parallel_groups: list[list[str]],
    init_index: dict[str, dict],
    impact_by_id: dict[str, dict],
) -> list[dict]:
    """Build named parallel tracks from parallel_groups."""
    tracks = []
    for idx, group in enumerate(parallel_groups):
        if len(group) < 2:
            # Single-initiative groups aren't really parallel
            continue

        init_titles = []
        total_controls = 0
        total_risks = 0
        for iid in group:
            init = init_index.get(iid, {})
            impact = impact_by_id.get(iid, {})
            init_titles.append(init.get("title", iid))
            total_controls += impact.get("controls_resolved", 0)
            total_risks += impact.get("risks_reduced", 0)

        tracks.append({
            "track_name": f"Parallel Track {idx + 1}",
            "initiative_ids": group,
            "initiative_titles": init_titles,
            "total_controls_resolved": total_controls,
            "total_risks_reduced": total_risks,
        })

    return tracks


def _build_effort_matrix(
    initiatives: list[dict],
    impact_by_id: dict[str, dict],
    phase_assignment: dict[str, str],
) -> list[dict]:
    """Build effort vs impact matrix for each initiative."""
    matrix = []
    for init in initiatives:
        iid = init.get("initiative_id", "")
        if not iid:
            continue

        impact = impact_by_id.get(iid, {})
        delivery = init.get("delivery_model", {})

        # Effort classification
        duration = delivery.get("estimated_duration", "")
        effort = _classify_effort(duration)

        # Impact classification
        controls = impact.get("controls_resolved", 0)
        risks = impact.get("risks_reduced", 0)
        blast = impact.get("blast_radius_score", 0)
        impact_score = controls * 2 + risks * 5 + blast

        matrix.append({
            "initiative_id": iid,
            "title": init.get("title", ""),
            "phase": phase_assignment.get(iid, "unknown"),
            "effort": effort,
            "estimated_duration": duration,
            "impact_score": round(impact_score, 1),
            "controls_resolved": controls,
            "risks_reduced": risks,
            "quadrant": _quadrant(effort, impact_score),
        })

    return matrix


def _classify_effort(duration: str) -> str:
    """Classify effort as Low/Medium/High from duration string."""
    if not duration:
        return "Unknown"
    dl = duration.lower()
    if any(x in dl for x in ("1 week", "days", "immediate", "1 day", "2 day", "3 day")):
        return "Low"
    if any(x in dl for x in ("2 week", "3 week", "1–2 week", "1-2 week", "2-3 week")):
        return "Medium"
    return "High"


def _quadrant(effort: str, impact_score: float) -> str:
    """Classify into effort-impact quadrant."""
    high_impact = impact_score >= 10
    low_effort = effort in ("Low", "Unknown")

    if high_impact and low_effort:
        return "Quick Win"
    if high_impact and not low_effort:
        return "Major Project"
    if not high_impact and low_effort:
        return "Fill In"
    return "Reconsider"


def _generate_optimization_notes(
    initiatives: list[dict],
    dep_graph: dict[str, Any],
    risk_impact: dict[str, Any],
    quick_wins: list[dict],
) -> list[str]:
    """Generate advisory optimization notes."""
    notes: list[str] = []

    violations = dep_graph.get("dependency_violations", [])
    if violations:
        notes.append(
            f"Dependency engine detected {len(violations)} ordering violation(s) "
            f"in the LLM-generated roadmap. These have been corrected."
        )

    if quick_wins:
        qw_ids = [q["initiative_id"] for q in quick_wins]
        notes.append(
            f"Quick wins identified: {', '.join(qw_ids)} — "
            f"no dependencies, immediate start."
        )

    # Check for initiatives with >3 risks reduced
    high_impact = [
        item for item in risk_impact.get("items", [])
        if item.get("risks_reduced", 0) >= 3
    ]
    if high_impact:
        for item in high_impact:
            notes.append(
                f"{item['initiative_id']} resolves {item['risks_reduced']} business risks — "
                f"prioritize within dependency constraints."
            )

    parallel_groups = dep_graph.get("parallel_groups", [])
    multi_groups = [g for g in parallel_groups if len(g) > 1]
    if multi_groups:
        notes.append(
            f"{len(multi_groups)} parallel execution group(s) identified — "
            f"these can run concurrently to accelerate delivery."
        )

    return notes
