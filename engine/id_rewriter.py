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


# ── Regex matching initiative IDs ─────────────────────────────────
# Ordinal: INIT-001, INIT-002, ...
# Hash:    INIT-a1b2c3d4
_INIT_ID_RE = re.compile(r"INIT-\d{3,}")
_INIT_HASH_RE = re.compile(r"^INIT-[0-9a-f]{8}(?:-\d+)?$")


# ── Single-entry-point normalisation ─────────────────────────────

def normalize_initiative_id(raw_id: str, id_map: dict[str, str]) -> str | None:
    """Resolve *any* initiative-ID string to its canonical hash-based form.

    Parameters
    ----------
    raw_id : str
        An initiative ID in any format — ordinal ``INIT-001`` or
        hash ``INIT-a1b2c3d4``.
    id_map : dict[str, str]
        The old→new map produced by ``build_id_map``.

    Returns
    -------
    str | None
        The canonical hash-based ID, or ``None`` if the ID cannot be
        resolved (not in the map and not already valid hash-format).
    """
    if not raw_id:
        return None
    # Already in canonical hash form?
    if _INIT_HASH_RE.match(raw_id):
        return raw_id
    # Mapped ordinal → hash?
    return id_map.get(raw_id)


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
    blocker_mapping: dict[str, str | None],
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
        maps blocker category (lowercase) → initiative_id or None.
    """
    if not blocker_mapping or not readiness:
        return

    blockers = readiness.get("blockers", [])
    for blocker in blockers:
        category = blocker.get("category", "").lower()
        if category in blocker_mapping:
            resolved = blocker_mapping[category]
            if resolved is not None:
                blocker["resolving_initiative"] = resolved
            else:
                # No deterministic match — set null + assumption
                blocker["resolving_initiative"] = None
                assumptions = blocker.get("assumptions", [])
                assumptions.append(
                    "No deterministic mapping available — "
                    "no initiative controls overlap this blocker category."
                )
                blocker["assumptions"] = assumptions


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


# ── Readiness score normalisation ─────────────────────────────────

READINESS_SCORE_MAX = 100


def clamp_readiness_score(readiness: dict | None) -> None:
    """Clamp readiness_score to [0, READINESS_SCORE_MAX] in-place.

    If the raw value exceeds the maximum, it is clamped and an
    assumption note is appended explaining the adjustment.
    """
    if not readiness:
        return
    raw = readiness.get("readiness_score")
    if raw is None:
        return
    if not isinstance(raw, (int, float)):
        return

    clamped = max(0, min(int(raw), READINESS_SCORE_MAX))
    if clamped != int(raw):
        readiness["readiness_score"] = clamped
        assumptions = readiness.setdefault("assumptions", [])
        assumptions.append(
            f"readiness_score clamped from {int(raw)} to {clamped} "
            f"(valid range 0\u2013{READINESS_SCORE_MAX})."
        )
    else:
        readiness["readiness_score"] = clamped


# ── Pipeline validation report ────────────────────────────────────

def validate_pipeline_integrity(
    readiness: dict | None,
    initiatives: list[dict],
    blocker_mapping: dict[str, str | None],
    decision_impact: dict,
) -> list[str]:
    """Run structural integrity checks and return a list of violation strings.

    Prints a summary report during generation.  Returns violations so
    callers can embed them in the output JSON.
    """
    violations: list[str] = []
    valid_ids = {i.get("initiative_id") for i in initiatives if i.get("initiative_id")}

    # \u2500\u2500 1. Blocker \u2192 initiative referential integrity \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    blockers = (readiness or {}).get("blockers", [])
    valid_blocker_refs = 0
    invalid_blocker_refs = 0

    for b in blockers:
        ref = b.get("resolving_initiative")
        if ref is None:
            continue  # explicitly null \u2014 unmappable, acceptable
        if ref in valid_ids:
            valid_blocker_refs += 1
        else:
            invalid_blocker_refs += 1
            violations.append(
                f"Blocker '{b.get('category', '?')}': "
                f"resolving_initiative '{ref}' not in initiatives list."
            )

    # \u2500\u2500 2. Blocker category \u2194 initiative alignment (advisory) \u2500\u2500\u2500
    for b in blockers:
        ref = b.get("resolving_initiative")
        if ref is None or ref not in valid_ids:
            continue
        bcat = b.get("category", "").lower()
        from schemas.taxonomy import BLOCKER_CATEGORY_TO_SECTIONS
        expected_sections = BLOCKER_CATEGORY_TO_SECTIONS.get(bcat, [])
        if not expected_sections:
            continue
        init = next((i for i in initiatives if i.get("initiative_id") == ref), None)
        if not init:
            continue
        init_caf = (init.get("caf_discipline") or "").lower()
        init_area = (init.get("alz_design_area") or "").lower()
        has_overlap = (
            bcat in init_caf
            or bcat in init_area
            or any(s.lower() in init_area for s in expected_sections)
            or any(s.lower() in init_caf for s in expected_sections)
            or len(init.get("controls", [])) > 0
        )
        if not has_overlap:
            violations.append(
                f"Blocker '{bcat}': mapped to '{ref}' which may not "
                f"cover expected sections {expected_sections}."
            )

    # \u2500\u2500 3. Decision impact: controls > 0 implies confidence > 0 \u2500\u2500
    zero_conf_with_controls = 0
    for item in decision_impact.get("items", []):
        controls = item.get("evidence_refs", {}).get("controls", [])
        conf_val = item.get("confidence", {}).get("value", 0.0)
        if len(controls) > 0 and conf_val == 0.0:
            zero_conf_with_controls += 1
            violations.append(
                f"Decision impact '{item.get('initiative_id', '?')}': "
                f"{len(controls)} controls but confidence=0.0."
            )

    # \u2500\u2500 4. Initiative ID format consistency \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    mixed_format = 0
    for i in initiatives:
        iid = i.get("initiative_id", "")
        if iid and not _INIT_HASH_RE.match(iid) and not _INIT_ID_RE.match(iid):
            mixed_format += 1
            violations.append(f"Initiative ID '{iid}' has unrecognised format.")

    # \u2500\u2500 Print report \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    print("\\n  \u2500\u2500 Pipeline Integrity Validation Report \u2500\u2500")
    print(f"    Blockers: {valid_blocker_refs} valid refs, "
          f"{invalid_blocker_refs} invalid refs, "
          f"{sum(1 for b in blockers if b.get('resolving_initiative') is None)} null (unmappable)")
    print(f"    Decision impact: {zero_conf_with_controls} items with "
          f"non-empty controls but zero confidence (target: 0)")
    print(f"    Initiative IDs: {len(valid_ids)} total, "
          f"{mixed_format} format violations")
    if violations:
        print(f"    \u26a0 {len(violations)} validation issue(s):")
        for v in violations[:15]:
            print(f"      \u2022 {v}")
    else:
        print("    \u2713 All structural integrity checks passed")

    return violations
