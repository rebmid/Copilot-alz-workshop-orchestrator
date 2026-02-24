"""Checklist grounding — derives ``derived_from_checklist`` for each initiative.

This module is the bridge between the deterministic control pack (48 controls)
and the authoritative Azure/review-checklists ALZ checklist (243 items).

Architecture
~~~~~~~~~~~~
Each **control** carries ``checklist_ids`` / ``checklist_guids`` — a mapping
verified at pack-load time against the cached ALZ checklist.

Each **initiative** references a list of controls.  This module:
  1. Resolves the controls in an initiative to their checklist items.
  2. Attaches ``derived_from_checklist`` (list of checklist item dicts)
     to the initiative object.
  3. Validates that every initiative maps to ≥1 checklist item; returns
     pipeline violations for any initiative that doesn't.

The primary entry point is ``ground_initiatives_to_checklist()``.

No checklist IDs are fabricated.  Every mapping comes from the
``checklist_ids`` field already embedded in ``controls.json``.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from alz.loader import get_checklist_items


# ── Controls.json static reference ────────────────────────────────
_CONTROLS_JSON_PATH = (
    Path(__file__).resolve().parent.parent
    / "control_packs" / "alz" / "v1.0" / "controls.json"
)

_CONTROLS_CACHE: dict[str, dict] | None = None


def _load_controls_json() -> dict[str, dict]:
    """Load the raw controls section from controls.json (cached)."""
    global _CONTROLS_CACHE
    if _CONTROLS_CACHE is None:
        with open(_CONTROLS_JSON_PATH, encoding="utf-8") as f:
            pack = json.load(f)
        _CONTROLS_CACHE = pack.get("controls", {})
    assert _CONTROLS_CACHE is not None  # narrowing for type checker
    return _CONTROLS_CACHE


# ── Checklist index (built once per process) ──────────────────────

_CHECKLIST_BY_ID: dict[str, dict] | None = None
_CHECKLIST_BY_GUID: dict[str, dict] | None = None


def _ensure_index() -> tuple[dict[str, dict], dict[str, dict]]:
    """Build in-memory indices over the ALZ checklist, lazily."""
    global _CHECKLIST_BY_ID, _CHECKLIST_BY_GUID
    if _CHECKLIST_BY_ID is None:
        items = get_checklist_items()
        _CHECKLIST_BY_ID = {it["id"]: it for it in items}
        _CHECKLIST_BY_GUID = {it["guid"]: it for it in items}
    assert _CHECKLIST_BY_ID is not None  # narrowing for type checker
    assert _CHECKLIST_BY_GUID is not None
    return _CHECKLIST_BY_ID, _CHECKLIST_BY_GUID


# ── Control → checklist resolution ────────────────────────────────

def resolve_control_to_checklist(
    control_id: str,
    controls_json: dict[str, dict] | None = None,
) -> list[dict]:
    """Return the checklist items that ground a single control.

    Parameters
    ----------
    control_id : str
        Short control ID (e.g. ``"e6c4cfd3"``, ``"storage-"``).
    controls_json : dict, optional
        The ``controls`` section of the loaded control pack — raw dicts.
        If *None*, loads from the default ``controls.json``.

    Returns
    -------
    list[dict]
        Each entry is ``{"checklist_id": "D07.01", "guid": "...", "text": "..."}``
        — a compact reference to the checklist item.
        Empty list if the control has no checklist mapping.
    """
    if controls_json is None:
        controls_json = _load_controls_json()
    by_id, by_guid = _ensure_index()

    ctrl = controls_json.get(control_id, {})
    ids = ctrl.get("checklist_ids", [])
    guids = ctrl.get("checklist_guids", [])

    refs: list[dict] = []

    # Prefer lookup by ID (more human-readable), fall back to GUID
    for cid in ids:
        if cid in by_id:
            it = by_id[cid]
            refs.append({
                "checklist_id": it["id"],
                "guid": it["guid"],
                "text": it.get("text", "")[:200],
                "severity": it.get("severity", ""),
                "category": it.get("category", ""),
            })

    # If no ID-based matches, try GUID-based
    if not refs:
        for guid in guids:
            if guid in by_guid:
                it = by_guid[guid]
                refs.append({
                    "checklist_id": it["id"],
                    "guid": it["guid"],
                    "text": it.get("text", "")[:200],
                    "severity": it.get("severity", ""),
                    "category": it.get("category", ""),
                })

    return refs


# ── Initiative-level checklist derivation ─────────────────────────

def derive_checklist_for_initiative(
    initiative: dict,
    controls_json: dict[str, dict] | None = None,
) -> list[dict]:
    """Compute ``derived_from_checklist`` for a single initiative.

    Aggregates checklist items from all controls in the initiative,
    deduplicates by ``checklist_id``, and returns a stable-sorted list.

    Parameters
    ----------
    initiative : dict
        An initiative dict with at least a ``controls`` list.
    controls_json : dict, optional
        The raw controls section of the control pack.
        If *None*, loads from the default ``controls.json``.

    Returns
    -------
    list[dict]
        Deduplicated, sorted list of checklist item references.
    """
    if controls_json is None:
        controls_json = _load_controls_json()
    seen: set[str] = set()
    checklist_refs: list[dict] = []

    for cid in initiative.get("controls", []):
        for ref in resolve_control_to_checklist(cid, controls_json):
            if ref["checklist_id"] not in seen:
                seen.add(ref["checklist_id"])
                checklist_refs.append(ref)

    # Stable sort by checklist ID for deterministic output
    checklist_refs.sort(key=lambda r: r["checklist_id"])
    return checklist_refs


# ── Pipeline entry point ──────────────────────────────────────────

def ground_initiatives_to_checklist(
    initiatives: list[dict],
    controls_json: dict[str, dict] | None = None,
) -> list[dict]:
    """Attach ``derived_from_checklist`` to every initiative.

    Modifies initiatives in-place and returns the list.

    Parameters
    ----------
    initiatives : list[dict]
        The initiative list from the roadmap pass.
    controls_json : dict, optional
        The raw controls section of the control pack.
        If *None*, loads from the default ``controls.json``.

    Returns
    -------
    list[dict]
        The same ``initiatives`` list, mutated with ``derived_from_checklist``.
    """
    if controls_json is None:
        controls_json = _load_controls_json()

    for init in initiatives:
        refs = derive_checklist_for_initiative(init, controls_json)
        init["derived_from_checklist"] = refs

    return initiatives


def validate_checklist_coverage(
    initiatives: list[dict],
) -> list[str]:
    """Return pipeline violation messages for initiatives missing checklist grounding.

    Call this AFTER ``ground_initiatives_to_checklist()`` has run.

    Returns
    -------
    list[str]
        One violation string per initiative that has an empty
        ``derived_from_checklist`` list.
    """
    violations: list[str] = []
    for init in initiatives:
        iid = init.get("initiative_id", "UNKNOWN")
        title = init.get("title", "untitled")
        refs = init.get("derived_from_checklist", [])
        if not refs:
            violations.append(
                f"Initiative {iid} ('{title}') has no checklist grounding — "
                f"none of its controls map to ALZ review-checklist items"
            )
    return violations


# ── Control-pack-level validation ─────────────────────────────────

def validate_controls_checklist_mapping(
    controls_json: dict[str, dict] | None = None,
) -> list[str]:
    """Validate that every control's checklist_ids exist in the cached ALZ checklist.

    Call at control-pack load time to catch stale or invalid mappings.

    Parameters
    ----------
    controls_json : dict, optional
        The raw controls section.  If *None*, loads from ``controls.json``.

    Returns
    -------
    list[str]
        One violation string per invalid checklist ID reference.
    """
    if controls_json is None:
        controls_json = _load_controls_json()
    by_id, by_guid = _ensure_index()
    violations: list[str] = []

    for cid, ctrl in controls_json.items():
        for chk_id in ctrl.get("checklist_ids", []):
            if chk_id not in by_id:
                violations.append(
                    f"Control {cid}: checklist_id '{chk_id}' not found "
                    f"in ALZ review-checklist"
                )
        for guid in ctrl.get("checklist_guids", []):
            if guid not in by_guid:
                violations.append(
                    f"Control {cid}: checklist_guid '{guid}' not found "
                    f"in ALZ review-checklist"
                )

    return violations
