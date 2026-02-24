"""Tests for engine.id_rewriter — checklist-canonical ID utilities.

Verifies:
  - Blocker patching with deterministic mapping (patch_blocker_items)
  - Readiness score clamping
  - Pipeline integrity validation (checklist_id format)
"""
from __future__ import annotations

from typing import Any

import pytest

from engine.id_rewriter import (
    patch_blocker_items,
    patch_blocker_initiatives,  # backward-compat alias
    clamp_readiness_score,
    READINESS_SCORE_MAX,
    validate_pipeline_integrity,
)


# ── Fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def sample_readiness():
    """Enterprise-scale readiness with blockers."""
    return {
        "overall_readiness": "Conditional",
        "blockers": [
            {
                "category": "governance",
                "description": "No MG hierarchy",
                "resolving_checklist_ids": ["B02.01"],
            },
            {
                "category": "security",
                "description": "Defender not enabled",
                "resolving_checklist_ids": ["D01.03"],
            },
        ],
    }


# ── Blocker patching ─────────────────────────────────────────────

class TestPatchBlockerItems:
    def test_patches_by_category(self, sample_readiness):
        mapping = {"governance": ["A01.01"], "security": ["D02.05"]}
        patch_blocker_items(sample_readiness, mapping)
        assert sample_readiness["blockers"][0]["resolving_checklist_ids"] == ["A01.01"]
        assert sample_readiness["blockers"][1]["resolving_checklist_ids"] == ["D02.05"]

    def test_noop_on_empty_mapping(self, sample_readiness):
        original = sample_readiness["blockers"][0]["resolving_checklist_ids"]
        patch_blocker_items(sample_readiness, {})
        assert sample_readiness["blockers"][0]["resolving_checklist_ids"] == original

    def test_noop_on_none_readiness(self):
        patch_blocker_items(None, {"governance": ["A01.01"]})  # no crash

    def test_backward_compat_alias(self):
        """patch_blocker_initiatives is an alias for patch_blocker_items."""
        assert patch_blocker_initiatives is patch_blocker_items

    def test_empty_mapping_sets_empty_list_and_assumption(self):
        """When blocker_item_map has empty list, set [] + assumption."""
        readiness = {
            "blockers": [
                {"category": "Governance", "resolving_checklist_ids": ["A01.01"]},
            ],
        }
        mapping: dict[str, list[str]] = {"governance": []}
        patch_blocker_items(readiness, mapping)
        b = readiness["blockers"][0]
        assert b["resolving_checklist_ids"] == []
        assert any("No deterministic mapping" in a for a in b.get("assumptions", []))

    def test_valid_mapping_applied(self):
        """Non-empty list mappings are applied normally."""
        readiness = {
            "blockers": [
                {"category": "Governance", "resolving_checklist_ids": ["old-ref"]},
            ],
        }
        mapping: dict[str, list[str]] = {"governance": ["A01.01"]}
        patch_blocker_items(readiness, mapping)
        assert readiness["blockers"][0]["resolving_checklist_ids"] == ["A01.01"]

    def test_legacy_resolving_initiative_field(self):
        """Handles legacy resolving_initiative field via mapping override."""
        readiness = {
            "blockers": [
                {"category": "governance", "resolving_initiative": "old-init"},
            ],
        }
        mapping = {"governance": ["A01.01"]}
        patch_blocker_items(readiness, mapping)
        assert readiness["blockers"][0]["resolving_checklist_ids"] == ["A01.01"]


# ── clamp_readiness_score ────────────────────────────────────────


class TestClampReadinessScore:
    """Tests for clamp_readiness_score()."""

    def test_score_within_range(self):
        """Scores already within range are kept (as int)."""
        r = {"readiness_score": 75}
        clamp_readiness_score(r)
        assert r["readiness_score"] == 75
        assert "assumptions" not in r

    def test_score_above_max(self):
        """Scores above max are clamped with assumption."""
        r: dict[str, Any] = {"readiness_score": 150}
        clamp_readiness_score(r)
        assert r["readiness_score"] == READINESS_SCORE_MAX
        assert any("clamped" in a for a in r["assumptions"])

    def test_score_below_zero(self):
        """Negative scores are clamped to 0."""
        r: dict[str, Any] = {"readiness_score": -5}
        clamp_readiness_score(r)
        assert r["readiness_score"] == 0
        assert any("clamped" in a for a in r["assumptions"])

    def test_none_readiness(self):
        """None input does not crash."""
        clamp_readiness_score(None)  # no exception

    def test_missing_score(self):
        """Dict without readiness_score is a no-op."""
        r = {"blockers": []}
        clamp_readiness_score(r)
        assert "readiness_score" not in r

    def test_float_score(self):
        """Float score is truncated to int."""
        r = {"readiness_score": 72.8}
        clamp_readiness_score(r)
        assert r["readiness_score"] == 72

    def test_non_numeric_score(self):
        """Non-numeric score is left untouched."""
        r = {"readiness_score": "high"}
        clamp_readiness_score(r)
        assert r["readiness_score"] == "high"

    def test_max_constant(self):
        """READINESS_SCORE_MAX is 100 (matching prompt contract)."""
        assert READINESS_SCORE_MAX == 100


# ── validate_pipeline_integrity ──────────────────────────────────


class TestValidatePipelineIntegrity:
    """Tests for validate_pipeline_integrity()."""

    def test_clean_pipeline(self):
        """No violations on well-formed data with checklist_id format."""
        items = [
            {"checklist_id": "A01.01", "controls": ["C1"], "caf_discipline": "Governance"},
        ]
        readiness = {
            "readiness_score": 50,
            "blockers": [
                {"category": "governance", "resolving_checklist_ids": ["A01.01"]},
            ],
        }
        blocker_map = {"governance": ["A01.01"]}
        decision_impact = {
            "items": [
                {"checklist_id": "A01.01", "evidence_refs": {"controls": ["C1"]}, "confidence": {"value": 0.6}},
            ],
        }
        violations = validate_pipeline_integrity(readiness, items, blocker_map, decision_impact)
        invalid_refs = [v for v in violations if "not in" in v.lower()]
        assert len(invalid_refs) == 0

    def test_invalid_blocker_ref(self):
        """Blocker pointing to non-existent item is flagged."""
        items = [{"checklist_id": "A01.01", "controls": ["C1"]}]
        readiness = {
            "blockers": [
                {"category": "governance", "resolving_checklist_ids": ["Z99.99"]},
            ],
        }
        violations = validate_pipeline_integrity(readiness, items, {}, {"items": []})
        assert any("Z99.99" in v for v in violations)

    def test_null_blocker_ref_is_ok(self):
        """Empty resolving_checklist_ids is acceptable (unmappable)."""
        readiness = {
            "blockers": [
                {"category": "governance", "resolving_checklist_ids": []},
            ],
        }
        violations = validate_pipeline_integrity(readiness, [], {}, {"items": []})
        assert not any("not in" in v.lower() for v in violations)

    def test_none_readiness(self):
        """None readiness doesn't crash."""
        violations = validate_pipeline_integrity(None, [], {}, {"items": []})
        assert isinstance(violations, list)
