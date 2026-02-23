"""Dependency Engine — strict architectural ordering for initiatives.

Layer 1 of the 3-layer deterministic decision engine.

This module derives initiative-level ordering ENTIRELY from the
control-level dependency graph in the Knowledge Graph (Kahn's topo sort).
No risk weighting, no ease-of-implementation bias — pure architectural
prerequisite enforcement.

Rules:
  - An initiative cannot start before ALL initiatives whose controls
    are prerequisites of its own controls.
  - Sentinel cannot precede centralized logging.
  - Private endpoints cannot precede secure network topology.
  - RBAC hygiene cannot precede MG hierarchy.
  - Phase assignment (30/60/90) respects dependency depth.
"""
from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

import logging

_log = logging.getLogger(__name__)


# ── Public API ────────────────────────────────────────────────────

def build_initiative_dependency_graph(
    initiatives: list[dict],
    control_dependencies: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    """
    Build a deterministic initiative-level dependency graph from
    control-level dependencies.

    Parameters
    ----------
    initiatives : list[dict]
        Initiative list from the roadmap pass.  Each has:
          - initiative_id: str
          - controls: list[str]   (control GUIDs)
          - dependencies: list[str]  (initiative IDs — LLM-generated, used as fallback only)
    control_dependencies : dict[str, list[str]] | None
        Map of control_id → [prerequisite_control_ids] from the knowledge graph.
        If None, falls back to initiative-declared dependencies.

    Returns
    -------
    dict with:
      - initiative_order: list[str]  — topologically sorted initiative IDs
      - initiative_deps: dict[str, list[str]]  — initiative_id → prerequisite initiative IDs
      - phase_assignment: dict[str, str]  — initiative_id → "30_days" | "60_days" | "90_days"
      - parallel_groups: list[list[str]]  — groups of initiatives that can run concurrently
      - dependency_violations: list[str]  — any LLM ordering that contradicts architectural deps
    """
    init_index = _build_initiative_index(initiatives)

    # Step 1: Map each control to its owning initiative
    control_to_initiative = _map_controls_to_initiatives(initiatives)

    # Step 2: Derive initiative-level deps from control-level deps
    if control_dependencies:
        init_deps = _derive_initiative_deps_from_controls(
            initiatives, control_dependencies, control_to_initiative
        )
    else:
        # Fallback: use LLM-declared initiative.dependencies
        init_deps = {
            init.get("initiative_id", ""): list(init.get("dependencies", []))
            for init in initiatives
            if init.get("initiative_id")
        }

    # Step 3: Topological sort of initiatives (Kahn's algorithm)
    initiative_order = _topo_sort_initiatives(
        [i.get("initiative_id", "") for i in initiatives if i.get("initiative_id")],
        init_deps,
    )

    # Step 4: Assign phases based on dependency depth
    phase_assignment = _assign_phases(initiative_order, init_deps)

    # Step 5: Identify parallel execution groups within each phase
    parallel_groups = _build_parallel_groups(initiative_order, init_deps, phase_assignment)

    # Step 6: Detect violations where LLM ordering contradicts architectural deps
    dependency_violations = _detect_violations(initiatives, init_deps)

    return {
        "initiative_order": initiative_order,
        "initiative_deps": init_deps,
        "phase_assignment": phase_assignment,
        "parallel_groups": parallel_groups,
        "dependency_violations": dependency_violations,
    }


def reorder_roadmap_phases(
    roadmap_30_60_90: dict[str, list[dict]],
    dep_graph: dict[str, Any],
) -> dict[str, list[dict]]:
    """
    Rewrite the LLM-generated roadmap_30_60_90 to respect the
    deterministic phase assignments from the dependency engine.

    Moves initiatives between phases if the dependency engine says
    they belong in a different phase than the LLM placed them.
    Does NOT add or remove initiatives — only reorders.

    Returns a new roadmap_30_60_90 dict.
    """
    phase_assignment = dep_graph.get("phase_assignment", {})
    initiative_order = dep_graph.get("initiative_order", [])

    # Collect all roadmap entries by initiative_id
    all_entries: dict[str, dict] = {}
    for phase_key in ("30_days", "60_days", "90_days"):
        for entry in roadmap_30_60_90.get(phase_key, []):
            iid = entry.get("initiative_id", "")
            if iid:
                all_entries[iid] = entry

    # Redistribute into correct phases
    new_phases: dict[str, list[dict]] = {"30_days": [], "60_days": [], "90_days": []}
    for iid in initiative_order:
        target_phase = phase_assignment.get(iid, "90_days")
        entry = all_entries.get(iid)
        if entry:
            new_phases[target_phase].append(entry)

    # Add any entries not in the dependency graph (preserve them)
    seen = set(initiative_order)
    for phase_key in ("30_days", "60_days", "90_days"):
        for entry in roadmap_30_60_90.get(phase_key, []):
            iid = entry.get("initiative_id", "")
            if iid and iid not in seen:
                new_phases[phase_key].append(entry)

    return new_phases


# ── Internal helpers ──────────────────────────────────────────────

def _build_initiative_index(initiatives: list[dict]) -> dict[str, dict]:
    return {
        init.get("initiative_id", ""): init
        for init in initiatives
        if init.get("initiative_id")
    }


def _map_controls_to_initiatives(initiatives: list[dict]) -> dict[str, str]:
    """Map control_id → initiative_id (first match wins).

    Logs a warning when a control appears in multiple initiatives,
    which may indicate an LLM clustering overlap.
    """
    mapping: dict[str, str] = {}
    for init in initiatives:
        iid = init.get("initiative_id", "")
        for ctrl_id in init.get("controls", []):
            if ctrl_id in mapping:
                _log.warning(
                    "Control %s appears in multiple initiatives: %s and %s. "
                    "First-match (%s) wins for dependency derivation.",
                    ctrl_id, mapping[ctrl_id], iid, mapping[ctrl_id],
                )
            else:
                mapping[ctrl_id] = iid
    return mapping


def _derive_initiative_deps_from_controls(
    initiatives: list[dict],
    control_deps: dict[str, list[str]],
    control_to_initiative: dict[str, str],
) -> dict[str, list[str]]:
    """
    Derive initiative-level dependencies from control-level dependencies.

    If control C1 depends on control C2, and C1 is in INIT-003 while
    C2 is in INIT-001, then INIT-003 depends on INIT-001.

    Self-dependencies (initiative depends on itself) are excluded.
    """
    init_deps: dict[str, list[str]] = {}

    for init in initiatives:
        iid = init.get("initiative_id", "")
        if not iid:
            continue

        deps: set[str] = set()
        for ctrl_id in init.get("controls", []):
            # Look up what controls this control depends on
            prereqs = control_deps.get(ctrl_id, [])
            for prereq_id in prereqs:
                prereq_initiative = control_to_initiative.get(prereq_id)
                if prereq_initiative and prereq_initiative != iid:
                    deps.add(prereq_initiative)

        # Also preserve LLM-declared dependencies that don't contradict
        for llm_dep in init.get("dependencies", []):
            if llm_dep != iid and llm_dep in control_to_initiative.values():
                deps.add(llm_dep)

        init_deps[iid] = sorted(deps)

    return init_deps


def _topo_sort_initiatives(
    initiative_ids: list[str],
    init_deps: dict[str, list[str]],
) -> list[str]:
    """Kahn's algorithm for initiative-level topological sort."""
    id_set = set(initiative_ids)

    in_degree: dict[str, int] = {iid: 0 for iid in id_set}
    adj: dict[str, list[str]] = {iid: [] for iid in id_set}

    for iid in id_set:
        for dep in init_deps.get(iid, []):
            if dep in id_set:
                adj[dep].append(iid)
                in_degree[iid] += 1

    # Stable sort: break ties by initiative_id for determinism
    queue = deque(sorted(iid for iid, d in in_degree.items() if d == 0))
    result: list[str] = []

    while queue:
        current = queue.popleft()
        result.append(current)
        for child in sorted(adj.get(current, [])):
            in_degree[child] -= 1
            if in_degree[child] == 0:
                queue.append(child)

    # Cycle detection: append remaining nodes
    remaining = sorted(iid for iid in id_set if iid not in set(result))
    result.extend(remaining)

    return result


def _assign_phases(
    initiative_order: list[str],
    init_deps: dict[str, list[str]],
) -> dict[str, str]:
    """
    Assign initiatives to 30/60/90 phases based on dependency depth.

    Depth 0 (no dependencies) → 30_days
    Depth 1 (depends on depth-0 only) → 60_days
    Depth 2+ → 90_days
    """
    phases = ("30_days", "60_days", "90_days")

    # Compute depth for each initiative
    depth: dict[str, int] = {}
    for iid in initiative_order:
        deps = init_deps.get(iid, [])
        if not deps:
            depth[iid] = 0
        else:
            max_parent_depth = max(depth.get(d, 0) for d in deps)
            depth[iid] = max_parent_depth + 1

    # Map depth to phase
    assignment: dict[str, str] = {}
    for iid in initiative_order:
        d = depth.get(iid, 0)
        phase_idx = min(d, len(phases) - 1)
        assignment[iid] = phases[phase_idx]

    return assignment


def _build_parallel_groups(
    initiative_order: list[str],
    init_deps: dict[str, list[str]],
    phase_assignment: dict[str, str],
) -> list[list[str]]:
    """
    Identify groups of initiatives that can execute in parallel.

    Two initiatives can run in parallel if:
      - They are in the same phase
      - Neither depends on the other (directly or transitively)
    """
    # Group by phase
    by_phase: dict[str, list[str]] = defaultdict(list)
    for iid in initiative_order:
        phase = phase_assignment.get(iid, "90_days")
        by_phase[phase].append(iid)

    groups: list[list[str]] = []
    for phase in ("30_days", "60_days", "90_days"):
        phase_inits = by_phase.get(phase, [])
        if not phase_inits:
            continue

        # Within a phase, split into independent sets
        # Two initiatives conflict if one depends on the other
        current_group: list[str] = []
        group_deps: set[str] = set()

        for iid in phase_inits:
            deps = set(init_deps.get(iid, []))
            # Check if this initiative depends on anything in the current group
            if deps & set(current_group):
                # Start a new group
                if current_group:
                    groups.append(current_group)
                current_group = [iid]
                group_deps = deps
            else:
                current_group.append(iid)
                group_deps.update(deps)

        if current_group:
            groups.append(current_group)

    return groups


def _detect_violations(
    initiatives: list[dict],
    init_deps: dict[str, list[str]],
) -> list[str]:
    """
    Detect where the LLM's declared initiative ordering contradicts
    the architecturally-derived dependency graph.
    """
    violations: list[str] = []

    for init in initiatives:
        iid = init.get("initiative_id", "")
        llm_deps = set(init.get("dependencies", []))
        arch_deps = set(init_deps.get(iid, []))

        # Missing architectural deps (LLM didn't declare them)
        missing = arch_deps - llm_deps
        for dep in sorted(missing):
            violations.append(
                f"{iid} missing architectural dependency on {dep} "
                f"(control prereqs require it)"
            )

    return violations
