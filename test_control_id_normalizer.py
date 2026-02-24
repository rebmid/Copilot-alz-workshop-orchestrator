"""Tests for canonical control ID normalization (engine.id_rewriter).

Verifies:
  - Exact match: canonical 8-char keys pass through unchanged
  - Prefix match: long-form IDs resolve to their 8-char canonical key
  - Reject: unknown IDs are removed and logged as violations
  - Deduplication: duplicate resolved IDs are collapsed
  - Edge cases: empty controls, missing field, empty items list
"""
from __future__ import annotations

import pytest

from engine.id_rewriter import (
    _resolve_control_id,
    normalize_control_ids,
    _load_canonical_keys,
)


# ── Canonical key set for testing ─────────────────────────────────
# Subset of actual keys from controls.json for deterministic tests.

CANONICAL_KEYS = {
    "e6c4cfd3",
    "e8bbac75",
    "storage-",
    "rbac-hyg",
    "cost-for",
    "monitor-",
    "breakgla",
    "pim-matu",
    "backup-c",
    "private-",
    "acr-post",
    "update-m",
    "change-t",
}


# ── _resolve_control_id ──────────────────────────────────────────


class TestResolveControlId:
    """Unit tests for the single-ID resolver."""

    def test_exact_match(self):
        resolved, status = _resolve_control_id("e6c4cfd3", CANONICAL_KEYS)
        assert resolved == "e6c4cfd3"
        assert status == "exact"

    def test_exact_match_slug(self):
        resolved, status = _resolve_control_id("storage-", CANONICAL_KEYS)
        assert resolved == "storage-"
        assert status == "exact"

    def test_prefix_match_uuid(self):
        """Full UUID resolves to its 8-char prefix."""
        resolved, status = _resolve_control_id(
            "e6c4cfd3-e504-4547-a244-7ec66138a720", CANONICAL_KEYS
        )
        assert resolved == "e6c4cfd3"
        assert status == "prefix"

    def test_prefix_match_slug_long(self):
        """Long slug resolves to its 8-char prefix."""
        resolved, status = _resolve_control_id(
            "storage-posture-001", CANONICAL_KEYS
        )
        assert resolved == "storage-"
        assert status == "prefix"

    def test_prefix_match_rbac(self):
        resolved, status = _resolve_control_id(
            "rbac-hygiene-001", CANONICAL_KEYS
        )
        assert resolved == "rbac-hyg"
        assert status == "prefix"

    def test_prefix_match_cost(self):
        resolved, status = _resolve_control_id(
            "cost-forecast-001", CANONICAL_KEYS
        )
        assert resolved == "cost-for"
        assert status == "prefix"

    def test_prefix_match_monitor(self):
        resolved, status = _resolve_control_id(
            "monitor-workspace-topology-001", CANONICAL_KEYS
        )
        assert resolved == "monitor-"
        assert status == "prefix"

    def test_prefix_match_breakglass(self):
        resolved, status = _resolve_control_id(
            "breakglass-validation-001", CANONICAL_KEYS
        )
        assert resolved == "breakgla"
        assert status == "prefix"

    def test_prefix_match_pim(self):
        resolved, status = _resolve_control_id(
            "pim-maturity-001", CANONICAL_KEYS
        )
        assert resolved == "pim-matu"
        assert status == "prefix"

    def test_prefix_match_backup(self):
        resolved, status = _resolve_control_id(
            "backup-coverage-001", CANONICAL_KEYS
        )
        assert resolved == "backup-c"
        assert status == "prefix"

    def test_prefix_match_update_manager(self):
        resolved, status = _resolve_control_id(
            "update-manager-001", CANONICAL_KEYS
        )
        assert resolved == "update-m"
        assert status == "prefix"

    def test_prefix_match_change_tracking(self):
        resolved, status = _resolve_control_id(
            "change-tracking-001", CANONICAL_KEYS
        )
        assert resolved == "change-t"
        assert status == "prefix"

    def test_reject_unknown(self):
        """Completely unknown ID is rejected."""
        resolved, status = _resolve_control_id(
            "nonexistent-control-xyz", CANONICAL_KEYS
        )
        assert status == "reject"

    def test_reject_empty(self):
        resolved, status = _resolve_control_id("", CANONICAL_KEYS)
        assert status == "reject"


# ── normalize_control_ids ─────────────────────────────────────────


class TestNormalizeControlIds:
    """Integration tests for the full item-list normalizer."""

    def test_normalizes_all_exact(self):
        """Items with already-canonical IDs pass through unchanged."""
        items = [
            {"checklist_id": "A01.01", "controls": ["e6c4cfd3", "storage-"]},
        ]
        violations = normalize_control_ids(items, CANONICAL_KEYS)
        assert items[0]["controls"] == ["e6c4cfd3", "storage-"]
        # No normalization violations (only rejects generate violations
        # or prefix matches generate informational ones)
        assert not any("REJECTED" in v for v in violations)

    def test_normalizes_long_form(self):
        """Long-form IDs are rewritten to 8-char canonical keys."""
        items = [
            {
                "checklist_id": "G01.01",
                "controls": [
                    "storage-posture-001",
                    "private-endpoint-001",
                    "acr-posture-001",
                ],
            },
        ]
        violations = normalize_control_ids(items, CANONICAL_KEYS)
        assert items[0]["controls"] == ["storage-", "private-", "acr-post"]
        assert len([v for v in violations if "NORMALIZED" in v]) == 3

    def test_normalizes_mixed(self):
        """Mix of exact, prefix-match, and unknown controls."""
        items = [
            {
                "checklist_id": "C03.01",
                "controls": [
                    "e6c4cfd3",                                    # exact
                    "e8bbac75-7155-49ab-a153-e8908ae28c84",        # prefix
                    "totally-unknown-control-id",                  # reject
                ],
            },
        ]
        violations = normalize_control_ids(items, CANONICAL_KEYS)
        # Only exact + prefix survive
        assert "e6c4cfd3" in items[0]["controls"]
        assert "e8bbac75" in items[0]["controls"]
        assert "totally-unknown-control-id" not in items[0]["controls"]
        assert len(items[0]["controls"]) == 2
        assert any("REJECTED" in v for v in violations)
        assert any("NORMALIZED" in v for v in violations)

    def test_deduplication(self):
        """Duplicate resolved IDs are collapsed."""
        items = [
            {
                "checklist_id": "A01.01",
                "controls": [
                    "e6c4cfd3",
                    "e6c4cfd3-e504-4547-a244-7ec66138a720",
                ],
            },
        ]
        violations = normalize_control_ids(items, CANONICAL_KEYS)
        assert items[0]["controls"] == ["e6c4cfd3"]

    def test_empty_controls(self):
        """Item with no controls is skipped gracefully."""
        items = [{"checklist_id": "A01.01", "controls": []}]
        violations = normalize_control_ids(items, CANONICAL_KEYS)
        assert items[0]["controls"] == []
        assert violations == []

    def test_missing_controls_key(self):
        """Item without controls key is skipped."""
        items = [{"checklist_id": "A01.01"}]
        violations = normalize_control_ids(items, CANONICAL_KEYS)
        assert violations == []

    def test_empty_items_list(self):
        """Empty items list produces no violations."""
        violations = normalize_control_ids([], CANONICAL_KEYS)
        assert violations == []

    def test_real_assessment_control_ids(self):
        """Validates against the actual AI output from the assessment.

        These are the exact control IDs the AI emitted, which must all
        resolve to canonical keys via prefix matching.
        """
        items = [
            {"checklist_id": "A03.03", "controls": ["cost-forecast-001"]},
            {"checklist_id": "E01.01", "controls": ["monitor-workspace-topology-001"]},
            {"checklist_id": "B03.01", "controls": ["rbac-hygiene-001"]},
            {"checklist_id": "B03.15", "controls": ["breakglass-validation-001"]},
            {"checklist_id": "B03.07", "controls": ["pim-maturity-001"]},
            {
                "checklist_id": "C03.01",
                "controls": [
                    "e6c4cfd3-e504-4547-a244-7ec66138a720",
                    "e8bbac75-7155-49ab-a153-e8908ae28c84",
                ],
            },
            {"checklist_id": "F01.01", "controls": ["backup-coverage-001"]},
            {"checklist_id": "E02.01", "controls": ["update-manager-001", "change-tracking-001"]},
            {
                "checklist_id": "G01.01",
                "controls": [
                    "storage-posture-001",
                    "private-endpoint-001",
                    "acr-posture-001",
                ],
            },
        ]
        violations = normalize_control_ids(items, CANONICAL_KEYS)

        # Every control should be resolved — no rejects
        rejects = [v for v in violations if "REJECTED" in v]
        assert rejects == [], f"Unexpected rejects: {rejects}"

        # Verify specific resolutions
        assert items[0]["controls"] == ["cost-for"]
        assert items[1]["controls"] == ["monitor-"]
        assert items[2]["controls"] == ["rbac-hyg"]
        assert items[3]["controls"] == ["breakgla"]
        assert items[4]["controls"] == ["pim-matu"]
        assert "e6c4cfd3" in items[5]["controls"]
        assert "e8bbac75" in items[5]["controls"]
        assert items[6]["controls"] == ["backup-c"]
        assert items[7]["controls"] == ["update-m", "change-t"]
        assert items[8]["controls"] == ["storage-", "private-", "acr-post"]


# ── _load_canonical_keys ──────────────────────────────────────────


class TestLoadCanonicalKeys:
    """Test that canonical keys can be loaded from controls.json."""

    def test_loads_48_keys(self):
        keys = _load_canonical_keys()
        assert len(keys) == 48

    def test_all_keys_are_8_chars_or_less(self):
        keys = _load_canonical_keys()
        for k in keys:
            assert len(k) == 8, f"Key '{k}' is {len(k)} chars, expected 8"

    def test_known_keys_present(self):
        keys = _load_canonical_keys()
        for expected in ["e6c4cfd3", "storage-", "rbac-hyg", "cost-for"]:
            assert expected in keys, f"Expected key '{expected}' not found"
