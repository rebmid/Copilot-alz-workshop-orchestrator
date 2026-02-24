"""Dependency Engine — strict architectural ordering for remediation items.

Layer 1 of the 3-layer deterministic decision engine.

This module derives item-level ordering ENTIRELY from the
control-level dependency graph in the Knowledge Graph (Kahn's topo sort).
No risk weighting, no ease-of-implementation bias — pure architectural
prerequisite enforcement.

Rules:
  - A remediation item cannot start before ALL items whose controls
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
    Build a deterministic item-level dependency graph from
    control-level dependencies.

    Parameters
    ----------
    initiatives : list[dict]
        Remediation items (keyed by checklist_id).  Each has:
          - checklist_id: str
          - controls: list[str]   (control GUIDs)
          - dependencies: list[str]  (checklist IDs — fallback only)
    control_dependencies : dict[str, list[str]] | None
        Map of control_id → [prerequisite_control_ids] from the knowledge graph.
        If None, falls back to item-declared dependencies.

    Returns
    -------
    dict with:
      - initiative_order: list[str]  — topologically sorted checklist IDs
      - initiative_deps: dict[str, list[str]]  — checklist_id → prerequisite checklist IDs
      - phase_assignment: dict[str, str]  — checklist_id → "30_days" | "60_days" | "90_days"
      - parallel_groups: list[list[str]]  — groups of items that can run concurrently
      - dependency_violations: list[str]  — any ordering that contradicts architectural deps
    """
    init_index = _build_item_index(initiatives)

    # Step 1: Map each control to its owning item
    control_to_item = _map_controls_to_items(initiatives)

    # Step 2: Derive item-level deps from control-level deps
    if control_dependencies:
        init_deps = _derive_item_deps_from_controls(
            initiatives, control_dependencies, control_to_item
        )
    else:
        # Fallback: use declared dependencies
        init_deps = {
            item.get("checklist_id", ""): list(item.get("dependencies", []))
            for item in initiatives
            if item.get("checklist_id")
        }

    # Step 3: Topological sort (Kahn's algorithm)
    initiative_order = _topo_sort_items(
        [i.get("checklist_id", "") for i in initiatives if i.get("checklist_id")],
        init_deps,
    )

    # Step 4: Assign phases based on dependency depth
    phase_assignment = _assign_phases(initiative_order, init_deps)

    # Step 5: Identify parallel execution groups within each phase
    parallel_groups = _build_parallel_groups(initiative_order, init_deps, phase_assignment)

    # Step 6: Detect violations where declared ordering contradicts architectural deps
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
    Rewrite the roadmap_30_60_90 to respect the
    deterministic phase assignments from the dependency engine.

    Moves items between phases if the dependency engine says
    they belong in a different phase.
    Does NOT add or remove items — only reorders.

    Returns a new roadmap_30_60_90 dict.
    """
    phase_assignment = dep_graph.get("phase_assignment", {})
    initiative_order = dep_graph.get("initiative_order", [])

    # Collect all roadmap entries by checklist_id
    all_entries: dict[str, dict] = {}
    for phase_key in ("30_days", "60_days", "90_days"):
        for entry in roadmap_30_60_90.get(phase_key, []):
            cid = entry.get("checklist_id", "")
            if cid:
                all_entries[cid] = entry

    # Redistribute into correct phases
    new_phases: dict[str, list[dict]] = {"30_days": [], "60_days": [], "90_days": []}
    for cid in initiative_order:
        target_phase = phase_assignment.get(cid, "90_days")
        entry = all_entries.get(cid)
        if entry:
            new_phases[target_phase].append(entry)

    # Add any entries not in the dependency graph (preserve them)
    seen = set(initiative_order)
    for phase_key in ("30_days", "60_days", "90_days"):
        for entry in roadmap_30_60_90.get(phase_key, []):
            cid = entry.get("checklist_id", "")
            if cid and cid not in seen:
                new_phases[phase_key].append(entry)

    return new_phases


# ── Internal helpers ──────────────────────────────────────────────

def _build_item_index(items: list[dict]) -> dict[str, dict]:
    return {
        item.get("checklist_id", ""): item
        for item in items
        if item.get("checklist_id")
    }


def _map_controls_to_items(items: list[dict]) -> dict[str, str]:
    """Map control_id → checklist_id (first match wins).

    Logs a warning when a control appears in multiple items,
    which may indicate overlapping checklist coverage.
    """
    mapping: dict[str, str] = {}
    for item in items:
        cid = item.get("checklist_id", "")
        for ctrl_id in item.get("controls", []):
            if ctrl_id in mapping:
                _log.warning(
                    "Control %s appears in multiple items: %s and %s. "
                    "First-match (%s) wins for dependency derivation.",
                    ctrl_id, mapping[ctrl_id], cid, mapping[ctrl_id],
                )
            else:
                mapping[ctrl_id] = cid
    return mapping


def _derive_item_deps_from_controls(
    items: list[dict],
    control_deps: dict[str, list[str]],
    control_to_item: dict[str, str],
) -> dict[str, list[str]]:
    """
    Derive item-level dependencies from control-level dependencies.

    If control C1 depends on control C2, and C1 is in item A01.01 while
    C2 is in item B02.03, then A01.01 depends on B02.03.

    Self-dependencies (item depends on itself) are excluded.
    """
    item_deps: dict[str, list[str]] = {}

    for item in items:
        cid = item.get("checklist_id", "")
        if not cid:
            continue

        deps: set[str] = set()
        for ctrl_id in item.get("controls", []):
            # Look up what controls this control depends on
            prereqs = control_deps.get(ctrl_id, [])
            for prereq_id in prereqs:
                prereq_item = control_to_item.get(prereq_id)
                if prereq_item and prereq_item != cid:
                    deps.add(prereq_item)

        # Also preserve declared dependencies that don't contradict
        for declared_dep in item.get("dependencies", []):
            if declared_dep != cid and declared_dep in control_to_item.values():
                deps.add(declared_dep)

        item_deps[cid] = sorted(deps)

    return item_deps


def _topo_sort_items(
    item_ids: list[str],
    item_deps: dict[str, list[str]],
) -> list[str]:
    """Kahn's algorithm for item-level topological sort."""
    id_set = set(item_ids)

    in_degree: dict[str, int] = {cid: 0 for cid in id_set}
    adj: dict[str, list[str]] = {cid: [] for cid in id_set}

    for cid in id_set:
        for dep in item_deps.get(cid, []):
            if dep in id_set:
                adj[dep].append(cid)
                in_degree[cid] += 1

    # Stable sort: break ties by checklist_id for determinism
    queue = deque(sorted(cid for cid, d in in_degree.items() if d == 0))
    result: list[str] = []

    while queue:
        current = queue.popleft()
        result.append(current)
        for child in sorted(adj.get(current, [])):
            in_degree[child] -= 1
            if in_degree[child] == 0:
                queue.append(child)

    # Cycle detection: append remaining nodes
    remaining = sorted(cid for cid in id_set if cid not in set(result))
    result.extend(remaining)

    return result


def _assign_phases(
    item_order: list[str],
    item_deps: dict[str, list[str]],
) -> dict[str, str]:
    """
    Assign items to 30/60/90 phases based on dependency depth.

    Depth 0 (no dependencies) → 30_days
    Depth 1 (depends on depth-0 only) → 60_days
    Depth 2+ → 90_days
    """
    phases = ("30_days", "60_days", "90_days")

    # Compute depth for each item
    depth: dict[str, int] = {}
    for cid in item_order:
        deps = item_deps.get(cid, [])
        if not deps:
            depth[cid] = 0
        else:
            max_parent_depth = max(depth.get(d, 0) for d in deps)
            depth[cid] = max_parent_depth + 1

    # Map depth to phase
    assignment: dict[str, str] = {}
    for cid in item_order:
        d = depth.get(cid, 0)
        phase_idx = min(d, len(phases) - 1)
        assignment[cid] = phases[phase_idx]

    return assignment


def _build_parallel_groups(
    item_order: list[str],
    item_deps: dict[str, list[str]],
    phase_assignment: dict[str, str],
) -> list[list[str]]:
    """
    Identify groups of items that can execute in parallel.

    Two items can run in parallel if:
      - They are in the same phase
      - Neither depends on the other (directly or transitively)
    """
    # Group by phase
    by_phase: dict[str, list[str]] = defaultdict(list)
    for cid in item_order:
        phase = phase_assignment.get(cid, "90_days")
        by_phase[phase].append(cid)

    groups: list[list[str]] = []
    for phase in ("30_days", "60_days", "90_days"):
        phase_items = by_phase.get(phase, [])
        if not phase_items:
            continue

        # Within a phase, split into independent sets
        # Two items conflict if one depends on the other
        current_group: list[str] = []
        group_deps: set[str] = set()

        for cid in phase_items:
            deps = set(item_deps.get(cid, []))
            # Check if this item depends on anything in the current group
            if deps & set(current_group):
                # Start a new group
                if current_group:
                    groups.append(current_group)
                current_group = [cid]
                group_deps = deps
            else:
                current_group.append(cid)
                group_deps.update(deps)

        if current_group:
            groups.append(current_group)

    return groups


def _detect_violations(
    items: list[dict],
    item_deps: dict[str, list[str]],
) -> list[str]:
    """
    Detect where declared item ordering contradicts
    the architecturally-derived dependency graph.
    """
    violations: list[str] = []

    for item in items:
        cid = item.get("checklist_id", "")
        declared_deps = set(item.get("dependencies", []))
        arch_deps = set(item_deps.get(cid, []))

        # Missing architectural deps (not declared)
        missing = arch_deps - declared_deps
        for dep in sorted(missing):
            violations.append(
                f"{cid} missing architectural dependency on {dep} "
                f"(control prereqs require it)"
            )

    return violations
