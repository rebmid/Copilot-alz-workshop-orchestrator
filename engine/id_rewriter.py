"""Initiative ID Rewriter — hash-based deterministic initiative IDs.

Structural Consistency Layer
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Replaces LLM-generated ordinal initiative IDs (INIT-001 .. INIT-NNN)
with deterministic hash-based IDs derived from each initiative's
control set: ``INIT-{sha256(sorted(controls))[:8]}``.

This guarantees:
  - Same control cluster → same ID across runs
  - LLM reordering doesn't break downstream joins
  - All references (roadmap, blockers, dep-graph, parallel groups)
    are remapped in a single pass from one canonical id_map

Usage::

    from engine.id_rewriter import rewrite_initiative_ids

    id_map = rewrite_initiative_ids(
        initiatives=initiatives,
        roadmap_raw=roadmap_raw,
        readiness=readiness,
    )
"""
from __future__ import annotations

import hashlib
import re
from typing import Any


# ── Regex matching INIT-NNN ordinal IDs ──────────────────────────
_INIT_ID_RE = re.compile(r"INIT-\d{3,}")


def _hash_controls(controls: list[str]) -> str:
    """Compute a stable 8-char hex hash from a sorted control set."""
    canonical = "|".join(sorted(controls))
    return hashlib.sha256(canonical.encode()).hexdigest()[:8]


def compute_initiative_id(controls: list[str]) -> str:
    """Return a deterministic initiative ID from a control set.

    Format: ``INIT-{8-hex-chars}``

    If the control list is empty, returns a hash of the empty string
    (stable but unlikely to collide with real initiatives).
    """
    return f"INIT-{_hash_controls(controls)}"


def build_id_map(initiatives: list[dict]) -> dict[str, str]:
    """Build old_id → new_id mapping for all initiatives.

    Parameters
    ----------
    initiatives : list[dict]
        Initiative objects with ``initiative_id`` and ``controls`` fields.

    Returns
    -------
    dict mapping ordinal IDs (e.g. "INIT-001") to hash-based IDs
    (e.g. "INIT-a1b2c3d4").  Only entries where old ≠ new are included.
    """
    id_map: dict[str, str] = {}
    seen_new: dict[str, str] = {}  # new_id → old_id (collision detection)

    for init in initiatives:
        old_id = init.get("initiative_id", "")
        controls = init.get("controls", [])
        if not old_id:
            continue

        new_id = compute_initiative_id(controls)

        # Handle hash collisions (extremely unlikely with 8 hex chars)
        if new_id in seen_new and seen_new[new_id] != old_id:
            # Append a disambiguator
            suffix = 1
            while f"{new_id}-{suffix}" in seen_new:
                suffix += 1
            new_id = f"{new_id}-{suffix}"

        seen_new[new_id] = old_id
        if old_id != new_id:
            id_map[old_id] = new_id

    return id_map


def _remap_value(value: str, id_map: dict[str, str]) -> str:
    """Replace any INIT-NNN tokens in a string with their hash-based IDs."""
    def replacer(match: re.Match) -> str:
        old: str = match.group(0)
        return id_map.get(old) or old
    return _INIT_ID_RE.sub(replacer, value)


def _remap_tree(obj: Any, id_map: dict[str, str]) -> Any:
    """Recursively walk a JSON-like tree and remap initiative IDs.

    Handles dicts, lists, and strings.  Returns a new object — does not
    mutate the input.
    """
    if isinstance(obj, dict):
        return {k: _remap_tree(v, id_map) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_remap_tree(item, id_map) for item in obj]
    if isinstance(obj, str):
        return _remap_value(obj, id_map)
    return obj


def remap_initiatives_in_place(
    initiatives: list[dict],
    id_map: dict[str, str],
) -> None:
    """Remap initiative_id and dependency references in-place."""
    for init in initiatives:
        old_id = init.get("initiative_id", "")
        if old_id in id_map:
            init["initiative_id"] = id_map[old_id]

        # Remap dependencies
        if "dependencies" in init:
            init["dependencies"] = [
                id_map.get(dep, dep) for dep in init["dependencies"]
            ]


def remap_roadmap_raw(
    roadmap_raw: dict,
    id_map: dict[str, str],
) -> dict:
    """Remap all initiative ID references in the raw roadmap output.

    Covers:
      - roadmap_30_60_90 entries (initiative_id, dependency_on)
      - dependency_graph entries (add initiative_id, convert depends_on)
      - parallel_execution_groups
      - initiative_execution_plan
      - top_risks
      - backlog.epics
    """
    if not id_map:
        return roadmap_raw

    return _remap_tree(roadmap_raw, id_map)


def remap_readiness(
    readiness: dict | None,
    id_map: dict[str, str],
) -> dict | None:
    """Remap resolving_initiative in readiness blockers."""
    if not id_map or not readiness:
        return readiness
    return _remap_tree(readiness, id_map)


def normalize_dependency_graph(
    dep_graph_entries: list[dict],
    roadmap_30_60_90: dict[str, list[dict]],
) -> list[dict]:
    """Add initiative_id to dependency_graph entries and
    convert text-based depends_on to initiative ID arrays.

    The LLM dependency_graph uses action TEXT for depends_on.  This
    normalizer cross-references the roadmap_30_60_90 to resolve
    action text → initiative_id.

    Returns a new list — does not mutate the input.
    """
    # Build action text → initiative_id lookup from roadmap phases
    action_to_id: dict[str, str] = {}
    for phase_key in ("30_days", "60_days", "90_days"):
        for entry in roadmap_30_60_90.get(phase_key, []):
            action = entry.get("action", "")
            iid = entry.get("initiative_id", "")
            if action and iid:
                action_to_id[action] = iid

    normalized: list[dict] = []
    for entry in dep_graph_entries:
        new_entry = dict(entry)
        action = entry.get("action", "")

        # Add initiative_id if not present
        if "initiative_id" not in new_entry:
            new_entry["initiative_id"] = action_to_id.get(action, "")

        # Convert depends_on from text to initiative IDs
        raw_deps = entry.get("depends_on", [])
        id_deps: list[str] = []
        for dep in raw_deps:
            resolved = action_to_id.get(dep, "")
            if resolved:
                id_deps.append(resolved)
        new_entry["depends_on_ids"] = id_deps
        # Keep original text depends_on for readability

        normalized.append(new_entry)

    return normalized


def patch_blocker_initiatives(
    readiness: dict | None,
    blocker_mapping: dict[str, str],
) -> None:
    """Patch enterprise_scale_readiness blockers with deterministic
    resolving_initiative from the decision_impact blocker mapping.

    Modifies readiness in-place.

    Parameters
    ----------
    readiness : dict
        The enterprise_scale_readiness output (contains ``blockers``).
    blocker_mapping : dict
        Output of ``resolve_blockers_to_initiatives()`` —
        maps blocker description hash or category → initiative_id.
    """
    if not blocker_mapping or not readiness:
        return

    blockers = readiness.get("blockers", [])
    for blocker in blockers:
        category = blocker.get("category", "").lower()
        # The blocker_mapping is keyed by category (lowercase)
        if category in blocker_mapping:
            blocker["resolving_initiative"] = blocker_mapping[category]


def rewrite_initiative_ids(
    initiatives: list[dict],
    roadmap_raw: dict,
    readiness: dict | None = None,
) -> dict[str, str]:
    """Full ID rewrite pass — call after LLM passes, before deterministic layers.

    1. Computes hash-based IDs from each initiative's control set
    2. Builds old→new mapping
    3. Remaps initiatives in-place
    4. Remaps roadmap_raw in-place
    5. Remaps readiness in-place
    6. Normalizes dependency_graph entries

    Returns the id_map for traceability.  If all IDs are already
    hash-based (no remapping needed), returns an empty dict.
    """
    id_map = build_id_map(initiatives)

    if not id_map:
        return id_map

    print(f"        → id_rewriter: remapping {len(id_map)} initiative IDs")
    for old, new in sorted(id_map.items()):
        print(f"            {old} → {new}")

    # Remap initiatives
    remap_initiatives_in_place(initiatives, id_map)

    # Remap roadmap_raw (modifies by replacing the dict contents)
    remapped_roadmap = remap_roadmap_raw(roadmap_raw, id_map)
    roadmap_raw.clear()
    roadmap_raw.update(remapped_roadmap)

    # Remap readiness
    if readiness:
        remapped_readiness = remap_readiness(readiness, id_map)
        if remapped_readiness is not None:
            readiness.clear()
            readiness.update(remapped_readiness)

    # Normalize dependency_graph with initiative IDs
    dep_graph = roadmap_raw.get("dependency_graph", [])
    roadmap_30_60_90 = roadmap_raw.get("roadmap_30_60_90", {})
    if dep_graph and roadmap_30_60_90:
        roadmap_raw["dependency_graph"] = normalize_dependency_graph(
            dep_graph, roadmap_30_60_90,
        )

    return id_map
