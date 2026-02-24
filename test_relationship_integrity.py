"""Tests for relationship integrity validation and deterministic enforcement."""
from __future__ import annotations
import pytest

from engine.relationship_integrity import (
    validate_relationship_integrity,
    require_relationship_integrity,
    IntegrityError,
    _looks_like_title,
)
from engine.maturity_trajectory import compute_maturity_trajectory


# ═══════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════

def _make_output(
    *,
    blockers=None,
    initiatives=None,
    roadmap_30=None,
    roadmap_60=None,
    roadmap_90=None,
    trajectory=None,
    results=None,
    blocker_mapping=None,
):
    """Build a minimal pipeline output dict for testing."""
    inits = initiatives or []
    return {
        "results": results or [],
        "ai": {
            "enterprise_scale_readiness": {
                "blockers": blockers or [],
            },
            "initiatives": inits,
            "transformation_roadmap": {
                "roadmap_30_60_90": {
                    "30_days": roadmap_30 or [],
                    "60_days": roadmap_60 or [],
                    "90_days": roadmap_90 or [],
                },
            },
            "deterministic_trajectory": trajectory or {},
            "blocker_initiative_mapping": blocker_mapping or {},
        },
    }


# ═══════════════════════════════════════════════════════════════════
#  1. validate_relationship_integrity — structural checks
# ═══════════════════════════════════════════════════════════════════

class TestRelationshipIntegrityPass:
    """Cases where integrity should pass with zero violations."""

    def test_empty_output_passes(self):
        output = _make_output()
        ok, violations = validate_relationship_integrity(output)
        assert ok is True
        assert violations == []

    def test_valid_blocker_initiative_link(self):
        output = _make_output(
            blockers=[{
                "category": "Networking",
                "resolving_initiative": "INIT-aabbccdd",
                "severity": "Critical",
            }],
            initiatives=[{
                "initiative_id": "INIT-aabbccdd",
                "title": "Fix networking",
                "controls": ["ctrl-1"],
                "derived_from_checklist": [{"checklist_id": "D07.01"}],
            }],
            roadmap_30=[{
                "initiative_id": "INIT-aabbccdd",
                "action": "Fix networking",
            }],
        )
        ok, violations = validate_relationship_integrity(output)
        assert ok is True
        assert violations == []

    def test_multiple_initiatives_all_valid(self):
        output = _make_output(
            blockers=[
                {"category": "Security", "resolving_initiative": "INIT-11111111"},
                {"category": "Identity", "resolving_initiative": "INIT-22222222"},
            ],
            initiatives=[
                {
                    "initiative_id": "INIT-11111111",
                    "title": "Security baseline",
                    "controls": ["sec-1"],
                    "derived_from_checklist": [{"checklist_id": "G01.01"}],
                },
                {
                    "initiative_id": "INIT-22222222",
                    "title": "Identity hygiene",
                    "controls": ["iam-1"],
                    "derived_from_checklist": [{"checklist_id": "B01.01"}],
                },
            ],
            roadmap_30=[
                {"initiative_id": "INIT-11111111"},
                {"initiative_id": "INIT-22222222"},
            ],
        )
        ok, violations = validate_relationship_integrity(output)
        assert ok is True


class TestRelationshipIntegrityFail:
    """Cases where integrity should detect violations."""

    def test_blocker_references_nonexistent_initiative(self):
        output = _make_output(
            blockers=[{
                "category": "Governance",
                "resolving_initiative": "INIT-deadbeef",
                "severity": "Critical",
            }],
            initiatives=[{
                "initiative_id": "INIT-aabbccdd",
                "title": "Something else",
                "controls": ["ctrl-1"],
                "derived_from_checklist": [{"checklist_id": "E01.01"}],
            }],
        )
        ok, violations = validate_relationship_integrity(output)
        assert ok is False
        assert any("BLOCKER_REF" in v for v in violations)

    def test_blocker_references_title_string(self):
        output = _make_output(
            blockers=[{
                "category": "Networking",
                "resolving_initiative": "Implement hub-spoke network topology",
                "severity": "Critical",
            }],
            initiatives=[{
                "initiative_id": "INIT-aabbccdd",
                "title": "Implement hub-spoke network topology",
                "controls": ["net-1"],
                "derived_from_checklist": [{"checklist_id": "D07.01"}],
            }],
        )
        ok, violations = validate_relationship_integrity(output)
        assert ok is False
        assert any("BLOCKER_TITLE_REF" in v for v in violations)

    def test_blocker_null_resolving_initiative(self):
        output = _make_output(
            blockers=[{
                "category": "Identity",
                "resolving_initiative": None,
                "severity": "High",
            }],
            initiatives=[{
                "initiative_id": "INIT-aabbccdd",
                "controls": ["ctrl-1"],
                "derived_from_checklist": [{"checklist_id": "B01.01"}],
            }],
        )
        ok, violations = validate_relationship_integrity(output)
        assert ok is False
        assert any("BLOCKER_NULL_REF" in v for v in violations)

    def test_initiative_no_controls(self):
        output = _make_output(
            initiatives=[{
                "initiative_id": "INIT-aabbccdd",
                "title": "Empty init",
                "controls": [],
                "derived_from_checklist": [{"checklist_id": "D07.01"}],
            }],
        )
        ok, violations = validate_relationship_integrity(output)
        assert ok is False
        assert any("INIT_NO_CONTROLS" in v for v in violations)

    def test_initiative_empty_derived_from_checklist(self):
        """Rule D: derived_from_checklist must not be empty."""
        output = _make_output(
            initiatives=[{
                "initiative_id": "INIT-aabbccdd",
                "title": "Missing checklist",
                "controls": ["ctrl-1"],
                "derived_from_checklist": [],
            }],
        )
        ok, violations = validate_relationship_integrity(output)
        assert ok is False
        assert any("INIT_NO_CHECKLIST" in v for v in violations)

    def test_initiative_missing_derived_from_checklist_key(self):
        """Rule D: missing derived_from_checklist key treated as empty."""
        output = _make_output(
            initiatives=[{
                "initiative_id": "INIT-aabbccdd",
                "title": "No checklist key",
                "controls": ["ctrl-1"],
            }],
        )
        ok, violations = validate_relationship_integrity(output)
        assert ok is False
        assert any("INIT_NO_CHECKLIST" in v for v in violations)

    def test_roadmap_references_nonexistent_initiative(self):
        output = _make_output(
            initiatives=[{
                "initiative_id": "INIT-aabbccdd",
                "controls": ["c-1"],
                "derived_from_checklist": [{"checklist_id": "D07.01"}],
            }],
            roadmap_30=[{
                "initiative_id": "INIT-nonexist",
                "action": "something",
            }],
        )
        ok, violations = validate_relationship_integrity(output)
        assert ok is False
        assert any("ROADMAP_REF" in v for v in violations)

    def test_roadmap_entry_missing_initiative_id(self):
        output = _make_output(
            initiatives=[{
                "initiative_id": "INIT-aabbccdd",
                "controls": ["c-1"],
                "derived_from_checklist": [{"checklist_id": "D07.01"}],
            }],
            roadmap_60=[{"action": "no id here"}],
        )
        ok, violations = validate_relationship_integrity(output)
        assert ok is False
        assert any("ROADMAP_NO_ID" in v for v in violations)


class TestRequireRelationshipIntegrity:
    """Test the raise-on-failure convenience wrapper."""

    def test_raises_on_violation(self):
        output = _make_output(
            blockers=[{
                "category": "Test",
                "resolving_initiative": None,
            }],
        )
        with pytest.raises(IntegrityError) as exc_info:
            require_relationship_integrity(output)
        assert len(exc_info.value.violations) > 0

    def test_returns_empty_on_pass(self):
        output = _make_output()
        result = require_relationship_integrity(output)
        assert result == []


# ═══════════════════════════════════════════════════════════════════
#  2. _looks_like_title heuristic
# ═══════════════════════════════════════════════════════════════════

class TestLooksLikeTitle:
    def test_hash_id_not_title(self):
        assert _looks_like_title("INIT-aabbccdd") is False

    def test_ordinal_id_not_title(self):
        assert _looks_like_title("INIT-001") is False

    def test_title_with_spaces(self):
        assert _looks_like_title("Implement hub-spoke network topology") is True

    def test_empty_string(self):
        assert _looks_like_title("") is False


# ═══════════════════════════════════════════════════════════════════
#  3. Maturity trajectory — Rule C enforcement
# ═══════════════════════════════════════════════════════════════════

class TestMaturityTrajectoryRuleC:
    """Verify the strict maturity formula."""

    def _make_results(self, pass_count, fail_count, total=None):
        """Create simple results with given pass/fail/total counts."""
        results = []
        for i in range(pass_count):
            results.append({
                "control_id": f"pass-{i}",
                "status": "Pass",
                "severity": "Medium",
            })
        for i in range(fail_count):
            results.append({
                "control_id": f"fail-{i}",
                "status": "Fail",
                "severity": "Medium",
            })
        # If total > pass+fail, add Manual controls to pad
        total = total or (pass_count + fail_count)
        manual_count = total - pass_count - fail_count
        for i in range(manual_count):
            results.append({
                "control_id": f"manual-{i}",
                "status": "Manual",
                "severity": "Low",
            })
        return results

    def test_formula_uses_total_controls(self):
        """new_maturity = (passing + resolved) / total_controls * 100"""
        results = self._make_results(pass_count=5, fail_count=5, total=100)
        initiatives = [{
            "initiative_id": "INIT-aaaaaaaa",
            "controls": ["fail-0", "fail-1"],
        }]
        phase_assignment = {"INIT-aaaaaaaa": "30_days"}

        traj = compute_maturity_trajectory(
            initiatives, results,
            phase_assignment=phase_assignment,
            current_maturity_percent=5.0,
            total_controls=100,
        )

        # 5 passing + 2 resolved = 7, / 100 = 7.0%
        assert traj["post_30_day_percent"] == 7.0

    def test_unchanged_when_zero_resolved(self):
        """Rule C: if controls_resolved_by_phase == 0, unchanged."""
        results = self._make_results(pass_count=5, fail_count=5, total=100)
        # No initiatives → 0 controls resolved in any phase
        initiatives = []
        phase_assignment = {}

        traj = compute_maturity_trajectory(
            initiatives, results,
            phase_assignment=phase_assignment,
            current_maturity_percent=5.0,
            total_controls=100,
        )

        # All projections must equal current
        assert traj["post_30_day_percent"] == 5.0
        assert traj["post_60_day_percent"] == 5.0
        assert traj["post_90_day_percent"] == 5.0

    def test_partial_phase_resolution(self):
        """Only the phase with resolutions changes; others hold."""
        results = self._make_results(pass_count=10, fail_count=10, total=100)
        initiatives = [{
            "initiative_id": "INIT-aaaaaaaa",
            "controls": ["fail-0", "fail-1", "fail-2"],
        }]
        # All resolutions in 60-day phase
        phase_assignment = {"INIT-aaaaaaaa": "60_days"}

        traj = compute_maturity_trajectory(
            initiatives, results,
            phase_assignment=phase_assignment,
            current_maturity_percent=10.0,
            total_controls=100,
        )

        # 30d: no resolution → unchanged from current 10.0%
        assert traj["post_30_day_percent"] == 10.0
        # 60d: 10 + 3 = 13 / 100 = 13.0%
        assert traj["post_60_day_percent"] == 13.0
        # 90d: no additional → stays at 13.0%
        assert traj["post_90_day_percent"] == 13.0

    def test_audit_fields_present(self):
        """Trajectory must include _total_controls and _current_passing."""
        results = self._make_results(pass_count=5, fail_count=5, total=50)
        traj = compute_maturity_trajectory(
            [], results,
            phase_assignment={},
            current_maturity_percent=10.0,
            total_controls=50,
        )
        assert traj["_total_controls"] == 50
        assert traj["_current_passing"] == 5

    def test_total_controls_parameter(self):
        """total_controls overrides len(results)."""
        results = self._make_results(pass_count=5, fail_count=5, total=10)
        # Pass total_controls=243 (much larger than 10 results)
        traj = compute_maturity_trajectory(
            [], results,
            phase_assignment={},
            current_maturity_percent=2.0,
            total_controls=243,
        )
        assert traj["_total_controls"] == 243


# ═══════════════════════════════════════════════════════════════════
#  4. Trajectory integrity check in validator
# ═══════════════════════════════════════════════════════════════════

class TestTrajectoryIntegrityCheck:
    """Validate that trajectory drift is detected by the validator."""

    def test_trajectory_drift_detected(self):
        """If 0 controls resolved in a phase but maturity changes → violation."""
        output = _make_output(
            initiatives=[{
                "initiative_id": "INIT-aabbccdd",
                "controls": ["c-1"],
                "derived_from_checklist": [{"checklist_id": "D07.01"}],
            }],
            trajectory={
                "current_percent": 30.0,
                "post_30_day_percent": 45.0,  # drift: changed but 0 resolved
                "post_60_day_percent": 45.0,
                "post_90_day_percent": 45.0,
                "controls_resolved_by_phase": {
                    "30_days": 0,  # <-- zero resolved
                    "60_days": 0,
                    "90_days": 0,
                },
                "_total_controls": 100,
                "_current_passing": 30,
            },
        )
        ok, violations = validate_relationship_integrity(output)
        assert ok is False
        assert any("TRAJECTORY_DRIFT" in v for v in violations)

    def test_trajectory_no_drift_when_resolved(self):
        """No drift violation when controls are actually resolved."""
        output = _make_output(
            initiatives=[{
                "initiative_id": "INIT-aabbccdd",
                "controls": ["c-1"],
                "derived_from_checklist": [{"checklist_id": "D07.01"}],
            }],
            trajectory={
                "current_percent": 30.0,
                "post_30_day_percent": 35.0,
                "post_60_day_percent": 35.0,
                "post_90_day_percent": 35.0,
                "controls_resolved_by_phase": {
                    "30_days": 5,
                    "60_days": 0,
                    "90_days": 0,
                },
            },
        )
        ok, violations = validate_relationship_integrity(output)
        # Should pass (the only resolved phase has a change)
        trajectory_violations = [v for v in violations if "TRAJECTORY" in v]
        assert len(trajectory_violations) == 0


# ═══════════════════════════════════════════════════════════════════
#  5. Render.py integrity gate
# ═══════════════════════════════════════════════════════════════════

class TestRenderIntegrityGate:
    """Verify generate_report aborts on integrity failure."""

    def test_report_aborts_on_integrity_failure(self, tmp_path):
        """generate_report returns violations list when integrity fails."""
        from reporting.render import generate_report

        bad_output = _make_output(
            blockers=[{
                "category": "Test",
                "resolving_initiative": "INIT-nonexist",
                "severity": "Critical",
            }],
            initiatives=[{
                "initiative_id": "INIT-aabbccdd",
                "controls": ["c-1"],
                "derived_from_checklist": [{"checklist_id": "D07.01"}],
            }],
        )

        out_path = str(tmp_path / "report.html")
        result = generate_report(bad_output, out_path=out_path)
        assert result is not None
        assert isinstance(result, list)
        assert len(result) > 0
        # Error HTML should be written
        with open(out_path) as f:
            html = f.read()
        assert "Integrity" in html

    def test_report_succeeds_on_integrity_pass(self, tmp_path):
        """generate_report returns None when integrity passes."""
        from reporting.render import generate_report

        good_output = _make_output(
            initiatives=[{
                "initiative_id": "INIT-aabbccdd",
                "title": "Good initiative",
                "controls": ["ctrl-1"],
                "derived_from_checklist": [{"checklist_id": "D07.01"}],
            }],
            roadmap_30=[{"initiative_id": "INIT-aabbccdd"}],
        )
        # Add required scoring keys for template rendering
        good_output["scoring"] = {
            "overall_maturity_percent": 50.0,
            "automation_coverage": {"automated_controls": 1, "total_controls": 10},
            "section_scores": [],
        }
        good_output["meta"] = {"run_id": "test"}

        out_path = str(tmp_path / "report.html")
        result = generate_report(good_output, out_path=out_path)
        # On success, generate_report returns None (writes HTML to file)
        assert result is None


# ═══════════════════════════════════════════════════════════════════
#  6. Combined violation counting
# ═══════════════════════════════════════════════════════════════════

class TestMultipleViolations:
    """Ensure all violation types are collected in a single pass."""

    def test_all_violation_types_in_one_pass(self):
        output = _make_output(
            blockers=[
                {"category": "Bad", "resolving_initiative": "INIT-nonexist"},
                {"category": "Worse", "resolving_initiative": None},
                {"category": "Title ref", "resolving_initiative": "Apply policies for compliance"},
            ],
            initiatives=[
                {
                    "initiative_id": "INIT-aabbccdd",
                    "title": "Good",
                    "controls": [],  # no controls
                    "derived_from_checklist": [],  # empty checklist
                },
            ],
            roadmap_30=[
                {"initiative_id": ""},  # no id
                {"initiative_id": "INIT-ffffffff"},  # doesn't exist
            ],
        )
        ok, violations = validate_relationship_integrity(output)
        assert ok is False

        violation_types = set()
        for v in violations:
            # Extract type prefix (e.g., BLOCKER_REF from "BLOCKER_REF: ...")
            prefix = v.split(":")[0]
            violation_types.add(prefix)

        assert "BLOCKER_REF" in violation_types
        assert "BLOCKER_NULL_REF" in violation_types
        assert "BLOCKER_TITLE_REF" in violation_types
        assert "INIT_NO_CONTROLS" in violation_types
        assert "INIT_NO_CHECKLIST" in violation_types
        assert "ROADMAP_NO_ID" in violation_types
        assert "ROADMAP_REF" in violation_types
