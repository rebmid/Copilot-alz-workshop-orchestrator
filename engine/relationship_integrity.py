"""Relationship Integrity Validator — compiler-grade structural checks.

Enforces deterministic relationships across the entire pipeline output:
  - Blocker → initiative referential integrity
  - Initiative → control mapping completeness
  - Roadmap → initiative existence
  - derived_from_checklist non-empty enforcement
  - Maturity trajectory formula integrity

If any check fails, rendering and downstream processing MUST halt.

Usage::

    from engine.relationship_integrity import validate_relationship_integrity

    ok, violations = validate_relationship_integrity(output)
    if not ok:
        # abort — do not render, do not proceed
        for v in violations:
            print(v)
"""
from __future__ import annotations

from typing import Any


class IntegrityError(Exception):
    """Raised when relationship integrity validation fails."""

    def __init__(self, violations: list[str]):
        self.violations = violations
        super().__init__(
            f"Relationship integrity failed: {len(violations)} violation(s)"
        )


# ── Core validator ────────────────────────────────────────────────

def validate_relationship_integrity(output: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate all cross-references in the pipeline output.

    Prints diagnostic tables and returns (ok, violations).

    Parameters
    ----------
    output : dict
        Full pipeline output (either the top-level run dict or just
        the ``ai`` sub-dict).  The function auto-detects whether
        ``ai`` is nested or flat.

    Returns
    -------
    (ok, violations) : tuple[bool, list[str]]
        ``ok`` is True when zero violations are found.
    """
    # Normalise: accept both run-level dict and ai-level dict
    ai = output.get("ai", output)

    violations: list[str] = []

    esr = ai.get("enterprise_scale_readiness") or {}
    blockers = esr.get("blockers", [])
    initiatives = ai.get("initiatives", [])
    init_by_id: dict[str, dict] = {
        i["initiative_id"]: i
        for i in initiatives
        if "initiative_id" in i
    }
    roadmap_src = ai.get("transformation_roadmap") or {}
    roadmap_phases = roadmap_src.get("roadmap_30_60_90") or {}
    results = output.get("results", [])
    results_by_id = {r["control_id"]: r for r in results if "control_id" in r}
    trajectory = ai.get("deterministic_trajectory") or {}

    # ── Table 1: Blocker → Initiative integrity ───────────────────
    print("\n  ── Relationship Integrity: Blocker → Initiative ──")
    print(f"  {'Category':<30} {'resolving_initiative':<22} {'exists':<8} {'by_id':<6}")
    print(f"  {'─'*30} {'─'*22} {'─'*8} {'─'*6}")

    for b in blockers:
        category = b.get("category", "?")
        ref = b.get("resolving_initiative")
        exists = ref in init_by_id if ref else False
        by_id = bool(ref and not _looks_like_title(ref))

        flag = "✓" if exists else "✗"
        id_flag = "✓" if by_id else "✗"
        print(f"  {category:<30} {str(ref):<22} {flag:<8} {id_flag:<6}")

        if ref and not exists:
            violations.append(
                f"BLOCKER_REF: blocker '{category}' references "
                f"'{ref}' which does not exist in initiatives[]."
            )
        if ref and _looks_like_title(ref):
            violations.append(
                f"BLOCKER_TITLE_REF: blocker '{category}' references "
                f"a title string '{ref}' instead of initiative_id."
            )
        if ref is None:
            violations.append(
                f"BLOCKER_NULL_REF: blocker '{category}' has no "
                f"resolving_initiative."
            )

    # ── Table 2: Initiative → Control mappings ────────────────────
    print("\n  ── Relationship Integrity: Initiative → Controls ──")
    print(f"  {'initiative_id':<22} {'controls':<10} {'failing':<10} {'checklist':<10}")
    print(f"  {'─'*22} {'─'*10} {'─'*10} {'─'*10}")

    for init in initiatives:
        iid = init.get("initiative_id", "?")
        controls = init.get("controls", [])
        failing = sum(
            1 for c in controls
            if results_by_id.get(c, {}).get("status") in ("Fail", "Partial")
        )
        dfc = init.get("derived_from_checklist", [])
        dfc_count = len(dfc)

        print(f"  {iid:<22} {len(controls):<10} {failing:<10} {dfc_count:<10}")

        if not controls:
            violations.append(
                f"INIT_NO_CONTROLS: initiative '{iid}' has no controls[]."
            )
        if not dfc:
            violations.append(
                f"INIT_NO_CHECKLIST: initiative '{iid}' has empty "
                f"derived_from_checklist — violates Rule D."
            )

    # ── Table 3: Roadmap → Initiative references ──────────────────
    print("\n  ── Relationship Integrity: Roadmap → Initiatives ──")
    print(f"  {'phase':<12} {'initiative_id':<22} {'exists':<8}")
    print(f"  {'─'*12} {'─'*22} {'─'*8}")

    for phase_key in ("30_days", "60_days", "90_days"):
        entries = roadmap_phases.get(phase_key, [])
        for entry in entries:
            eid = entry.get("initiative_id", "")
            exists = eid in init_by_id

            flag = "✓" if exists else "✗"
            print(f"  {phase_key:<12} {eid:<22} {flag:<8}")

            if not eid:
                violations.append(
                    f"ROADMAP_NO_ID: roadmap entry in {phase_key} "
                    f"has no initiative_id."
                )
            elif not exists:
                violations.append(
                    f"ROADMAP_REF: roadmap entry '{eid}' in {phase_key} "
                    f"does not exist in initiatives[]."
                )

    # ── Maturity trajectory formula check ─────────────────────────
    if trajectory:
        total_controls = trajectory.get("_total_controls", 0)
        current_passing = trajectory.get("_current_passing", 0)
        controls_resolved = trajectory.get("controls_resolved_by_phase", {})

        for phase_key in ("30_days", "60_days", "90_days"):
            resolved = controls_resolved.get(phase_key, 0)
            if resolved == 0:
                # Verify that the trajectory didn't change for this phase
                _check_trajectory_unchanged(
                    trajectory, phase_key, violations
                )

    # ── Summary ───────────────────────────────────────────────────
    ok = len(violations) == 0
    status = "✓ PASS" if ok else f"✗ FAIL ({len(violations)} violations)"
    print(f"\n  ── Relationship Integrity Result: {status} ──")
    if not ok:
        for v in violations:
            print(f"    • {v}")

    return ok, violations


def _check_trajectory_unchanged(
    trajectory: dict, phase_key: str, violations: list[str]
) -> None:
    """Verify trajectory stays flat when no controls are resolved in a phase."""
    phase_map = {
        "30_days": ("current_percent", "post_30_day_percent"),
        "60_days": ("post_30_day_percent", "post_60_day_percent"),
        "90_days": ("post_60_day_percent", "post_90_day_percent"),
    }
    prev_key, curr_key = phase_map.get(phase_key, ("", ""))
    if not prev_key:
        return

    prev_val = trajectory.get(prev_key)
    curr_val = trajectory.get(curr_key)
    if prev_val is not None and curr_val is not None:
        if abs(float(curr_val) - float(prev_val)) > 0.01:
            violations.append(
                f"TRAJECTORY_DRIFT: {curr_key}={curr_val} differs from "
                f"{prev_key}={prev_val} but controls_resolved_by_phase"
                f".{phase_key}=0. Trajectory MUST remain unchanged."
            )


def _looks_like_title(ref: str) -> bool:
    """Heuristic: does a resolving_initiative value look like a title
    rather than a structured ID?

    IDs match patterns like INIT-001, INIT-a1b2c3d4.
    Titles typically contain spaces, are longer, or don't match ID patterns.
    """
    if not ref:
        return False
    # Valid ID patterns
    import re
    if re.match(r"^INIT-[0-9a-f]{8}(?:-\d+)?$", ref):
        return False
    if re.match(r"^INIT-\d{3,}$", ref):
        return False
    # If it contains spaces or is > 30 chars, it's likely a title
    if " " in ref or len(ref) > 30:
        return True
    return False


# ── Convenience: raise on failure ─────────────────────────────────

def require_relationship_integrity(output: dict[str, Any]) -> list[str]:
    """Validate and raise ``IntegrityError`` if any violations exist.

    Returns the (empty) violation list on success.
    """
    ok, violations = validate_relationship_integrity(output)
    if not ok:
        raise IntegrityError(violations)
    return violations
