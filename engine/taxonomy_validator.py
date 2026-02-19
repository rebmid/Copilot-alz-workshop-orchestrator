# engine/taxonomy_validator.py — Fail-fast taxonomy enforcement.
"""Foundation Layer 1 + 4: Taxonomy Integrity & Control Schema Formalization.

Every control that enters the assessment pipeline MUST carry a complete,
valid taxonomy.  There is **zero** fallback logic.  If a field is missing,
has an invalid value, or cannot be mapped — the system refuses to run.

This protects maturity math.

Layer 4 addition: ``validate_and_build_controls()`` validates the raw JSON
dicts and then constructs frozen ``ControlDefinition`` instances.  This is
the **only** code path that creates ``ControlDefinition`` objects.

Usage
~~~~~
    from engine.taxonomy_validator import validate_and_build_controls, TaxonomyViolation

    typed_controls = validate_and_build_controls(raw_controls, design_areas)
    # Returns dict[str, ControlDefinition]  — or raises TaxonomyViolation

Wire-in
~~~~~~~
Called by ``control_packs.loader.load_pack()`` before constructing the pack.
"""
from __future__ import annotations

from typing import Any

from schemas.taxonomy import (
    ALL_CONTROL_TYPES,
    ALL_DESIGN_AREAS,
    ALL_EVALUATION_LOGIC,
    ALL_SEVERITIES,
    ALL_WAF_PILLARS,
    DESIGN_AREA_SECTION,
    REQUIRED_CONTROL_FIELDS,
    ControlDefinition,
)


# ── Exception ─────────────────────────────────────────────────────

class TaxonomyViolation(Exception):
    """Raised when one or more controls have invalid taxonomy metadata.

    Contains a structured list of violations so callers can format them
    however they like (CLI table, JSON report, etc.).
    """

    def __init__(self, violations: list[dict[str, str]]) -> None:
        self.violations = violations
        lines = [f"  ✗ [{v['control_id']}] {v['field']}: {v['detail']}" for v in violations]
        msg = (
            f"{len(violations)} taxonomy violation(s) — fix before scanning:\n"
            + "\n".join(lines)
        )
        super().__init__(msg)


# ── Enum validators ───────────────────────────────────────────────

_ENUM_VALIDATORS: dict[str, tuple[str, ...]] = {
    "design_area":      ALL_DESIGN_AREAS,
    "waf_pillar":       ALL_WAF_PILLARS,
    "control_type":     ALL_CONTROL_TYPES,
    "severity":         ALL_SEVERITIES,
    "evaluation_logic": ALL_EVALUATION_LOGIC,
}


# ── Single control validation ────────────────────────────────────

def validate_control(control_id: str, ctrl: dict[str, Any]) -> list[dict[str, str]]:
    """Validate a single control dict against the canonical taxonomy.

    Returns a (possibly empty) list of violation dicts:
        [{"control_id": "...", "field": "...", "detail": "..."}]
    """
    violations: list[dict[str, str]] = []

    def _fail(field: str, detail: str) -> None:
        violations.append({
            "control_id": control_id,
            "field": field,
            "detail": detail,
        })

    # ── 1.  Required field presence ───────────────────────────────
    for field in REQUIRED_CONTROL_FIELDS:
        val = ctrl.get(field)
        if val is None or (isinstance(val, str) and val.strip() == ""):
            _fail(field, f"Missing or empty (required by REQUIRED_CONTROL_FIELDS)")

    # ── 2.  Enum value validation ─────────────────────────────────
    for field, allowed in _ENUM_VALIDATORS.items():
        val = ctrl.get(field)
        if val is not None and val not in allowed:
            _fail(field, f"'{val}' not in {list(allowed)}")

    # ── 3.  design_area → section map completeness ────────────────
    area = ctrl.get("design_area")
    if area and area not in DESIGN_AREA_SECTION:
        _fail(
            "design_area",
            f"'{area}' has no entry in DESIGN_AREA_SECTION — scoring will break",
        )

    # ── 4.  required_signals must be a non-empty list ─────────────
    sigs = ctrl.get("required_signals")
    if not isinstance(sigs, list) or len(sigs) == 0:
        _fail("required_signals", "Must be a non-empty list of signal names")

    # ── 5.  full_id must not be empty ─────────────────────────────
    fid = ctrl.get("full_id")
    if not fid or not isinstance(fid, str) or fid.strip() == "":
        _fail("full_id", "Must be a non-empty stable identifier")

    return violations


# ── Pack-level validation ─────────────────────────────────────────

def _validate_design_areas_index(
    raw_controls: dict[str, dict[str, Any]],
    design_areas: dict[str, dict[str, Any]],
    violations: list[dict[str, str]],
) -> None:
    """Cross-check design_areas index against raw controls dict.

    Appends any violations found to *violations* in-place.
    """
    indexed_ids: set[str] = set()
    for area_name, area_def in design_areas.items():
        if area_name not in ALL_DESIGN_AREAS:
            violations.append({
                "control_id": f"design_areas.{area_name}",
                "field": "design_area",
                "detail": f"'{area_name}' is not a valid ALZDesignArea",
            })
        for cid_ref in area_def.get("controls", []):
            indexed_ids.add(cid_ref)

    # Controls listed in design_areas but missing from controls dict
    missing_from_controls = indexed_ids - set(raw_controls.keys())
    for mid in sorted(missing_from_controls):
        violations.append({
            "control_id": mid,
            "field": "design_areas",
            "detail": "Listed in design_areas index but not defined in controls",
        })

    # Controls in controls dict but not indexed in any design_area
    unindexed = set(raw_controls.keys()) - indexed_ids
    for uid in sorted(unindexed):
        violations.append({
            "control_id": uid,
            "field": "design_areas",
            "detail": "Defined in controls but not listed in any design_area index",
        })


def validate_and_build_controls(
    raw_controls: dict[str, dict[str, Any]],
    design_areas: dict[str, dict[str, Any]],
) -> dict[str, ControlDefinition]:
    """Validate raw JSON control dicts and return typed ControlDefinition instances.

    This is the **only** code path that creates ``ControlDefinition`` objects.
    Two-phase approach:
      1. Validate raw dicts (nice per-field error messages via ``validate_control``).
      2. Cross-check design_areas index.
      3. If all clear, construct frozen ``ControlDefinition`` instances.

    Raises ``TaxonomyViolation`` if ANY control or cross-check has ANY violation.

    Parameters
    ----------
    raw_controls : dict[str, dict]
        The ``controls`` section from controls.json — key = 8-char short id.
    design_areas : dict[str, dict]
        The ``design_areas`` section from controls.json.

    Returns
    -------
    dict[str, ControlDefinition]
        Frozen, typed control definitions keyed by short id.
    """
    if not raw_controls:
        raise TaxonomyViolation([{
            "control_id": "*",
            "field": "controls",
            "detail": "Control pack has zero controls — nothing to assess",
        }])

    all_violations: list[dict[str, str]] = []

    # ── Phase 1: per-control field validation ─────────────────────
    for cid, ctrl in raw_controls.items():
        all_violations.extend(validate_control(cid, ctrl))

    # ── Phase 2: design_areas cross-check ─────────────────────────
    if design_areas:
        _validate_design_areas_index(raw_controls, design_areas, all_violations)

    if all_violations:
        raise TaxonomyViolation(all_violations)

    # ── Phase 3: construct frozen ControlDefinition instances ─────
    # Validation already passed — construction should not fail.
    typed: dict[str, ControlDefinition] = {}
    for cid, raw in raw_controls.items():
        typed[cid] = ControlDefinition.from_json(cid, raw)

    return typed


def validate_pack(pack: Any) -> None:
    """Legacy wrapper — validates a ControlPack with raw dict controls.

    .. deprecated::
        Use ``validate_and_build_controls()`` instead.  This wrapper
        exists only for backward compatibility with code that passes
        a ControlPack whose ``.controls`` is still ``dict[str, dict]``.
    """
    raw_controls = pack.controls
    design_areas = getattr(pack, "design_areas", {})

    # If controls are already ControlDefinition instances, skip
    first = next(iter(raw_controls.values()), None) if raw_controls else None
    if isinstance(first, ControlDefinition):
        return  # already validated and typed

    validate_and_build_controls(raw_controls, design_areas)
