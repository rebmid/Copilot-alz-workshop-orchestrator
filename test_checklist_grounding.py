"""Tests for alz.checklist_grounding — authority-grounded initiative derivation.

Tests that:
  1. Controls resolve to their correct checklist items via checklist_ids
  2. Initiatives accumulate deduplicated checklist items from their controls
  3. Pipeline validation flags initiatives with zero checklist grounding
  4. Controls.json mapping is complete — all 48 controls have checklist_ids
  5. All checklist_ids in controls.json actually exist in the ALZ checklist
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


# ── Fixtures ──────────────────────────────────────────────────────

CONTROLS_JSON_PATH = (
    Path(__file__).resolve().parent
    / "control_packs" / "alz" / "v1.0" / "controls.json"
)


@pytest.fixture
def controls_json() -> dict[str, dict]:
    """Load raw controls from the pack."""
    with open(CONTROLS_JSON_PATH, encoding="utf-8") as f:
        pack = json.load(f)
    return pack["controls"]


@pytest.fixture
def sample_initiative_with_controls() -> dict:
    """A synthetic initiative referencing multiple controls."""
    return {
        "initiative_id": "INIT-test0001",
        "title": "Harden Network Perimeter",
        "controls": ["e6c4cfd3", "088137f5", "nsg-cove"],
        "dependencies": [],
    }


@pytest.fixture
def sample_initiative_no_controls() -> dict:
    """An initiative with no controls → should flag violation."""
    return {
        "initiative_id": "INIT-orphan01",
        "title": "Orphaned Initiative",
        "controls": [],
        "dependencies": [],
    }


@pytest.fixture
def sample_initiative_with_unmapped_control() -> dict:
    """An initiative with a control_id that doesn't exist in the pack."""
    return {
        "initiative_id": "INIT-unknown1",
        "title": "Initiative With Unknown Control",
        "controls": ["not-a-real-control"],
        "dependencies": [],
    }


# ── Test: controls.json completeness ─────────────────────────────

class TestControlsJsonMappingCompleteness:
    """Ensure every control in the pack has checklist_ids."""

    def test_all_48_controls_have_checklist_ids(self, controls_json: dict):
        unmapped = [
            cid for cid, ctrl in controls_json.items()
            if not ctrl.get("checklist_ids")
        ]
        assert not unmapped, (
            f"{len(unmapped)} controls missing checklist_ids: {unmapped}"
        )

    def test_all_48_controls_have_checklist_guids(self, controls_json: dict):
        unmapped = [
            cid for cid, ctrl in controls_json.items()
            if not ctrl.get("checklist_guids")
        ]
        assert not unmapped, (
            f"{len(unmapped)} controls missing checklist_guids: {unmapped}"
        )

    def test_checklist_ids_and_guids_same_length(self, controls_json: dict):
        for cid, ctrl in controls_json.items():
            ids = ctrl.get("checklist_ids", [])
            guids = ctrl.get("checklist_guids", [])
            assert len(ids) == len(guids), (
                f"Control {cid}: checklist_ids length ({len(ids)}) "
                f"!= checklist_guids length ({len(guids)})"
            )


# ── Test: checklist_ids exist in ALZ checklist ────────────────────

class TestChecklistIdsExistInALZ:
    """Verify all referenced checklist_ids are real ALZ checklist items."""

    def test_validate_controls_checklist_mapping_no_violations(self, controls_json):
        from alz.checklist_grounding import validate_controls_checklist_mapping
        violations = validate_controls_checklist_mapping(controls_json)
        assert not violations, (
            f"Checklist mapping violations: {violations}"
        )


# ── Test: resolve_control_to_checklist ────────────────────────────

class TestResolveControlToChecklist:
    """Test single-control checklist resolution."""

    def test_uuid_control_resolves(self, controls_json):
        """e6c4cfd3 (Azure Firewall Presence) → D07.01"""
        from alz.checklist_grounding import resolve_control_to_checklist
        refs = resolve_control_to_checklist("e6c4cfd3", controls_json)
        assert len(refs) >= 1
        assert refs[0]["checklist_id"] == "D07.01"

    def test_slug_control_resolves(self, controls_json):
        """storage- (Storage Account Posture) → G04.01, G04.02"""
        from alz.checklist_grounding import resolve_control_to_checklist
        refs = resolve_control_to_checklist("storage-", controls_json)
        assert len(refs) == 2
        ids = {r["checklist_id"] for r in refs}
        assert "G04.01" in ids
        assert "G04.02" in ids

    def test_unknown_control_returns_empty(self, controls_json):
        from alz.checklist_grounding import resolve_control_to_checklist
        refs = resolve_control_to_checklist("no-such-ctrl", controls_json)
        assert refs == []

    def test_result_shape(self, controls_json):
        from alz.checklist_grounding import resolve_control_to_checklist
        refs = resolve_control_to_checklist("e6c4cfd3", controls_json)
        ref = refs[0]
        assert "checklist_id" in ref
        assert "guid" in ref
        assert "text" in ref
        assert "severity" in ref
        assert "category" in ref


# ── Test: derive_checklist_for_initiative ─────────────────────────

class TestDeriveChecklistForInitiative:
    """Test initiative-level checklist derivation."""

    def test_initiative_aggregates_controls(
        self, controls_json, sample_initiative_with_controls,
    ):
        from alz.checklist_grounding import derive_checklist_for_initiative
        refs = derive_checklist_for_initiative(
            sample_initiative_with_controls, controls_json,
        )
        # e6c4cfd3→D07.01, 088137f5→D05.06, nsg-cove→D09.04
        ids = {r["checklist_id"] for r in refs}
        assert "D07.01" in ids
        assert "D05.06" in ids
        assert "D09.04" in ids

    def test_initiative_deduplicates(self, controls_json):
        """Two controls mapping to same checklist item → no duplicates."""
        init = {
            "controls": ["sql-post", "appservi"],  # both → G03.05
        }
        from alz.checklist_grounding import derive_checklist_for_initiative
        refs = derive_checklist_for_initiative(init, controls_json)
        ids = [r["checklist_id"] for r in refs]
        assert ids.count("G03.05") == 1

    def test_initiative_no_controls_empty(self, controls_json, sample_initiative_no_controls):
        from alz.checklist_grounding import derive_checklist_for_initiative
        refs = derive_checklist_for_initiative(
            sample_initiative_no_controls, controls_json,
        )
        assert refs == []

    def test_initiative_unknown_controls_empty(
        self, controls_json, sample_initiative_with_unmapped_control,
    ):
        from alz.checklist_grounding import derive_checklist_for_initiative
        refs = derive_checklist_for_initiative(
            sample_initiative_with_unmapped_control, controls_json,
        )
        assert refs == []

    def test_results_sorted_by_checklist_id(
        self, controls_json, sample_initiative_with_controls,
    ):
        from alz.checklist_grounding import derive_checklist_for_initiative
        refs = derive_checklist_for_initiative(
            sample_initiative_with_controls, controls_json,
        )
        ids = [r["checklist_id"] for r in refs]
        assert ids == sorted(ids)


# ── Test: ground_initiatives_to_checklist ─────────────────────────

class TestGroundInitiativesToChecklist:
    """Test the pipeline entry point."""

    def test_mutates_in_place(self, controls_json, sample_initiative_with_controls):
        from alz.checklist_grounding import ground_initiatives_to_checklist
        initiatives = [sample_initiative_with_controls]
        result = ground_initiatives_to_checklist(initiatives, controls_json)
        assert result is initiatives
        assert "derived_from_checklist" in initiatives[0]

    def test_all_grounded_initiatives_have_field(self, controls_json):
        from alz.checklist_grounding import ground_initiatives_to_checklist
        initiatives = [
            {"initiative_id": "i1", "controls": ["e6c4cfd3"]},
            {"initiative_id": "i2", "controls": ["storage-"]},
        ]
        ground_initiatives_to_checklist(initiatives, controls_json)
        for init in initiatives:
            assert "derived_from_checklist" in init
            assert len(init["derived_from_checklist"]) > 0


# ── Test: validate_checklist_coverage ─────────────────────────────

class TestValidateChecklistCoverage:
    """Test pipeline violation detection."""

    def test_grounded_initiative_no_violation(self, controls_json):
        from alz.checklist_grounding import (
            ground_initiatives_to_checklist,
            validate_checklist_coverage,
        )
        initiatives = [
            {"initiative_id": "INIT-ok01", "title": "Good", "controls": ["e6c4cfd3"]},
        ]
        ground_initiatives_to_checklist(initiatives, controls_json)
        violations = validate_checklist_coverage(initiatives)
        assert violations == []

    def test_ungrounded_initiative_produces_violation(self):
        from alz.checklist_grounding import validate_checklist_coverage
        initiatives = [
            {"initiative_id": "INIT-bad01", "title": "Orphan", "derived_from_checklist": []},
        ]
        violations = validate_checklist_coverage(initiatives)
        assert len(violations) == 1
        assert "INIT-bad01" in violations[0]
        assert "no checklist grounding" in violations[0]

    def test_missing_field_produces_violation(self):
        from alz.checklist_grounding import validate_checklist_coverage
        initiatives = [
            {"initiative_id": "INIT-miss01", "title": "No Field"},
        ]
        violations = validate_checklist_coverage(initiatives)
        assert len(violations) == 1


# ── Test: ControlDefinition checklist fields ──────────────────────

class TestControlDefinitionChecklistFields:
    """Verify ControlDefinition dataclass carries checklist fields."""

    def test_control_definition_has_checklist_fields(self, controls_json):
        from schemas.taxonomy import ControlDefinition
        cid = "e6c4cfd3"
        ctrl = controls_json[cid]
        cd = ControlDefinition.from_json(cid, ctrl)
        assert hasattr(cd, "checklist_ids")
        assert hasattr(cd, "checklist_guids")
        assert isinstance(cd.checklist_ids, tuple)
        assert isinstance(cd.checklist_guids, tuple)

    def test_control_definition_ids_populated(self, controls_json):
        from schemas.taxonomy import ControlDefinition
        cid = "storage-"
        ctrl = controls_json[cid]
        cd = ControlDefinition.from_json(cid, ctrl)
        assert len(cd.checklist_ids) == 2
        assert "G04.01" in cd.checklist_ids
        assert "G04.02" in cd.checklist_ids

    def test_control_definition_defaults_empty(self):
        """If checklist fields missing in JSON, defaults to empty tuple."""
        from schemas.taxonomy import ControlDefinition
        raw = {
            "name": "test",
            "full_id": "test-full-00000001",
            "design_area": "network",
            "sub_area": "test",
            "waf_pillar": "Security",
            "control_type": "ALZ",
            "severity": "High",
            "evaluation_logic": "automated",
            "evaluator_module": "test",
            "required_signals": [],
        }
        cd = ControlDefinition.from_json("test", raw)
        assert cd.checklist_ids == ()
        assert cd.checklist_guids == ()
