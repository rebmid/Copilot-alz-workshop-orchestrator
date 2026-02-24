"""Pipeline Utilities — readiness normalization, blocker patching, integrity checks.

Formerly the "Initiative ID Rewriter" — the synthetic INIT-xxx layer has been
removed.  Checklist IDs from the Azure review-checklists repository are now
the canonical identifiers.

Retained utilities:
  - ``normalize_control_ids``       — canonical control ID normalization at AI ingestion
  - ``clamp_readiness_score``       — clamp readiness score to valid range
  - ``patch_blocker_items``         — patch blockers with resolving checklist_id
  - ``validate_pipeline_integrity`` — structural integrity check suite
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# Valid checklist_id pattern: letter(s) + digits + dot + digits (e.g. A01.01)
_CHECKLIST_ID_RE = re.compile(r"^[A-Z]\d{2}\.\d{2}$")

# Synthetic ID patterns that must NEVER appear in canonical fields.
# Catches: INIT-xxx, slug-001 style, UUIDs, and any non-checklist format.
_SYNTHETIC_ID_PATTERNS = [
    re.compile(r"^INIT-\d+$", re.IGNORECASE),                    # INIT-001, INIT-005
    re.compile(r"^[a-z]+-[a-z]+-\d+$", re.IGNORECASE),           # monitor-workspace-001
    re.compile(r"^[a-z]+-[a-z]+-[a-z]+-\d+$", re.IGNORECASE),    # cost-forecast-baseline-001
    re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-", re.IGNORECASE),      # UUID-style
]


def is_synthetic_id(value: str) -> bool:
    """Return True if the value matches a known synthetic ID pattern."""
    return any(p.match(value) for p in _SYNTHETIC_ID_PATTERNS)


# ── Canonical Control ID Normalization ────────────────────────────
# The deterministic layer must never tolerate identifier drift.
# AI output may emit full-length control IDs (e.g. "cost-forecast-001",
# "e6c4cfd3-e504-4547-a244-7ec66138a720") but the canonical control
# pack uses 8-character truncated keys (e.g. "cost-for", "e6c4cfd3").
#
# Strategy:
#   1. Exact match     → keep as-is (already canonical)
#   2. Prefix match    → rewrite to canonical key (first 8 chars match
#                         exactly one canonical key)
#   3. Ambiguous/none  → reject with structural violation

_CONTROLS_JSON_PATH = (
    Path(__file__).resolve().parent.parent
    / "control_packs" / "alz" / "v1.0" / "controls.json"
)

_CANONICAL_KEYS: set[str] | None = None


def _load_canonical_keys() -> set[str]:
    """Load the set of canonical control keys from controls.json (cached)."""
    global _CANONICAL_KEYS
    if _CANONICAL_KEYS is None:
        with open(_CONTROLS_JSON_PATH, encoding="utf-8") as f:
            pack = json.load(f)
        _CANONICAL_KEYS = set(pack.get("controls", {}).keys())
    return _CANONICAL_KEYS


def _resolve_control_id(raw_id: str, canonical_keys: set[str]) -> tuple[str, str]:
    """Resolve a single raw control ID to its canonical form.

    Returns
    -------
    tuple[str, str]
        (resolved_id, status) where status is one of:
        - "exact"    — already canonical
        - "prefix"   — resolved via 8-char prefix
        - "reject"   — no match or ambiguous match
    """
    # 1. Exact match
    if raw_id in canonical_keys:
        return raw_id, "exact"

    # 2. Prefix match — the canonical keys are 8-char truncated.
    #    Take the first 8 characters of the raw ID and check for a
    #    unique match among canonical keys.
    prefix = raw_id[:8]
    matches = [k for k in canonical_keys if k == prefix]
    if len(matches) == 1:
        return matches[0], "prefix"

    # 3. No match
    return raw_id, "reject"


def normalize_control_ids(
    items: list[dict],
    canonical_keys: set[str] | None = None,
) -> list[str]:
    """Normalize control IDs in AI-generated items to canonical 8-char keys.

    Modifies items in-place.  Each item's ``controls`` list is rewritten
    so that every entry is a canonical key from ``controls.json``.

    Rejected IDs are removed from the controls list and recorded as
    pipeline violations.

    Parameters
    ----------
    items : list[dict]
        Remediation items from the AI roadmap pass, each with a
        ``controls`` list.
    canonical_keys : set[str], optional
        The canonical control keys.  If *None*, loads from
        ``controls.json``.

    Returns
    -------
    list[str]
        Pipeline violation messages for rejected or rewritten IDs.
    """
    if canonical_keys is None:
        canonical_keys = _load_canonical_keys()

    violations: list[str] = []
    total_exact = 0
    total_prefix = 0
    total_reject = 0

    for item in items:
        raw_controls = item.get("controls", [])
        if not raw_controls:
            continue

        normalized: list[str] = []
        item_id = item.get("checklist_id", item.get("initiative_id", "UNKNOWN"))

        for raw_id in raw_controls:
            resolved, status = _resolve_control_id(raw_id, canonical_keys)

            if status == "exact":
                normalized.append(resolved)
                total_exact += 1

            elif status == "prefix":
                normalized.append(resolved)
                total_prefix += 1
                log.info(
                    "Control ID normalized: '%s' → '%s' (item %s)",
                    raw_id, resolved, item_id,
                )
                violations.append(
                    f"CONTROL_ID_NORMALIZED: '{raw_id}' → '{resolved}' "
                    f"in item {item_id} (prefix match)"
                )

            else:  # reject
                total_reject += 1
                log.warning(
                    "Control ID rejected: '%s' in item %s — "
                    "no canonical match found",
                    raw_id, item_id,
                )
                violations.append(
                    f"CONTROL_ID_REJECTED: '{raw_id}' in item {item_id} — "
                    f"no canonical match in controls.json"
                )

        # Deduplicate while preserving order
        seen: set[str] = set()
        deduped: list[str] = []
        for cid in normalized:
            if cid not in seen:
                seen.add(cid)
                deduped.append(cid)

        item["controls"] = deduped

    # Summary log
    print(
        f"        → control ID normalization: "
        f"{total_exact} exact, {total_prefix} prefix-resolved, "
        f"{total_reject} rejected"
    )

    return violations


def patch_blocker_items(
    readiness: dict | None,
    blocker_mapping: "dict[str, list[str]]",
) -> None:
    """Patch enterprise_scale_readiness blockers with deterministic
    resolving_checklist_ids from the decision_impact blocker mapping.

    Modifies readiness in-place.

    Parameters
    ----------
    readiness : dict
        The enterprise_scale_readiness output (contains ``blockers``).
    blocker_mapping : dict
        Output of ``resolve_blockers_to_items()`` —
        maps blocker category (lowercase) → list of checklist_ids.
    """
    if not blocker_mapping or not readiness:
        return

    blockers = readiness.get("blockers", [])
    for blocker in blockers:
        category = blocker.get("category", "").lower()
        if category in blocker_mapping:
            resolved = blocker_mapping[category]
            if resolved:
                blocker["resolving_checklist_ids"] = resolved
            else:
                # No deterministic match — set empty list + assumption
                blocker["resolving_checklist_ids"] = []
                assumptions = blocker.get("assumptions", [])
                assumptions.append(
                    "No deterministic mapping available — "
                    "no item controls overlap this blocker category."
                )
                blocker["assumptions"] = assumptions


# Keep old name as alias for backward compatibility during transition
patch_blocker_initiatives = patch_blocker_items


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
    items: list[dict],
    blocker_mapping: "dict[str, list[str]]",
    decision_impact: dict,
) -> list[str]:
    """Run structural integrity checks and return a list of violation strings.

    Prints a summary report during generation.  Returns violations so
    callers can embed them in the output JSON.

    Parameters
    ----------
    readiness : dict | None
        Enterprise-scale readiness output (with blockers).
    items : list[dict]
        Remediation items (each with checklist_id).
    blocker_mapping : dict
        Output of ``resolve_blockers_to_items()`` —
        maps blocker category → list of checklist_ids.
    decision_impact : dict
        Output of ``build_decision_impact_model()``.
    """
    violations: list[str] = []
    valid_ids = {i.get("checklist_id") for i in items if i.get("checklist_id")}

    # \u2500\u2500 1. Blocker \u2192 item referential integrity \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    blockers = (readiness or {}).get("blockers", [])
    valid_blocker_refs = 0
    invalid_blocker_refs = 0

    for b in blockers:
        refs = b.get("resolving_checklist_ids", None)
        # Legacy fallback for old data
        if refs is None:
            legacy = b.get("resolving_item", b.get("resolving_initiative"))
            refs = [legacy] if legacy else []
        if not refs:
            continue  # empty list — unmappable, acceptable
        for ref in refs:
            if ref in valid_ids:
                valid_blocker_refs += 1
            else:
                invalid_blocker_refs += 1
                violations.append(
                    f"Blocker '{b.get('category', '?')}': "
                    f"resolving_checklist_ids entry '{ref}' not in remediation items list."
                )

    # \u2500\u2500 2. Decision impact: controls > 0 implies confidence > 0 \u2500\u2500
    zero_conf_with_controls = 0
    for item in decision_impact.get("items", []):
        controls = item.get("evidence_refs", {}).get("controls", [])
        conf_val = item.get("confidence", {}).get("value", 0.0)
        if len(controls) > 0 and conf_val == 0.0:
            zero_conf_with_controls += 1
            violations.append(
                f"Decision impact '{item.get('checklist_id', '?')}': "
                f"{len(controls)} controls but confidence=0.0."
            )

    # \u2500\u2500 3. Checklist ID format consistency \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    invalid_format = 0
    for i in items:
        cid = i.get("checklist_id", "")
        if cid and not _CHECKLIST_ID_RE.match(cid):
            invalid_format += 1
            violations.append(f"Checklist ID '{cid}' has invalid format (expected e.g. A01.01).")

    # \u2500\u2500 Print report \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    print("\\n  \u2500\u2500 Pipeline Integrity Validation Report \u2500\u2500")
    print(f"    Blockers: {valid_blocker_refs} valid refs, "
          f"{invalid_blocker_refs} invalid refs, "
          f"{sum(1 for b in blockers if not b.get('resolving_checklist_ids'))} unmapped")
    print(f"    Decision impact: {zero_conf_with_controls} items with "
          f"non-empty controls but zero confidence (target: 0)")
    print(f"    Checklist IDs: {len(valid_ids)} total, "
          f"{invalid_format} format violations")
    if violations:
        print(f"    \u26a0 {len(violations)} validation issue(s):")
        for v in violations[:15]:
            print(f"      \u2022 {v}")
    else:
        print("    \u2713 All structural integrity checks passed")

    return violations
