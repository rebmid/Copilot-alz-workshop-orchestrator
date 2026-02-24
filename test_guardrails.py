"""Acceptance tests for anti-drift guardrails.

These tests MUST fail the build if any guardrail violation is detected.
Run:  pytest test_guardrails.py -v

Test matrix:
  T-1  evidence_refs empty on any derived item          → FAIL
  T-2  cost number when mode != tool_backed              → FAIL
  T-3  compliance pass/fail language                     → FAIL
  T-4  'High confidence' without computed basis          → FAIL
  T-5  recommendation without doc_ref                    → FAIL
  T-6  scaling simulation without rule_id                → FAIL
  T-7  drift model deterministic with known inputs       → deterministic output
  T-8  decision impact deterministic with known inputs   → deterministic output
  T-9  cost simulation no dollar amounts in category mode→ PASS
  T-10 full pipeline validate_anti_drift passes clean    → PASS
"""
from __future__ import annotations

import json
import pytest
from pathlib import Path

from engine.guardrails import (
    empty_evidence_refs,
    merge_evidence_refs,
    evidence_is_empty,
    insufficient_evidence_marker,
    compute_derived_confidence,
    check_no_compliance_claims,
    check_no_cost_numbers,
    check_confidence_has_basis,
    validate_evidence_refs,
    validate_doc_refs,
    validate_anti_drift,
)
from engine.scaling_rules import build_scaling_simulation, SCALING_RULES
from engine.drift_model import build_drift_model
from engine.cost_simulation import build_cost_simulation
from engine.decision_impact import build_decision_impact_model


# ── Fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def sample_results():
    """Minimal control results for testing."""
    return [
        {
            "control_id": "CTRL-GOV-001",
            "section": "Identity & Access",
            "status": "Fail",
            "confidence_score": 0.7,
            "signals_used": ["rbac_hygiene"],
        },
        {
            "control_id": "CTRL-NET-001",
            "section": "Networking",
            "status": "Fail",
            "confidence_score": 0.6,
            "signals_used": ["azure_firewall", "vnets"],
        },
        {
            "control_id": "CTRL-NET-002",
            "section": "Networking",
            "status": "Pass",
            "confidence_score": 0.9,
            "signals_used": ["vnets"],
        },
        {
            "control_id": "CTRL-MGMT-001",
            "section": "Management",
            "status": "Fail",
            "confidence_score": 0.5,
            "signals_used": ["diag_coverage_sample"],
        },
        {
            "control_id": "CTRL-SEC-001",
            "section": "Security",
            "status": "Manual",
            "confidence_score": 0.3,
            "signals_used": [],
        },
    ]


@pytest.fixture
def sample_signals():
    """Minimal signal dict for testing."""
    return {
        "mg_hierarchy": {"status": "ok", "data": {"depth": 2}},
        "diag_coverage_sample": {"status": "ok", "data": {"coverage_pct": 30}},
        "azure_firewall": {"status": "ok", "data": {"count": 0}},
        "assignments": {"status": "ok", "data": []},
        "rbac_hygiene": {"status": "ok", "data": {"custom_role_count": 0}},
        "vnets": {"status": "ok", "data": {"count": 3, "peered_count": 0}},
        "pricings": {"status": "ok", "data": [
            {"name": "VirtualMachines", "pricingTier": "Free"},
        ]},
        "resource_locks": {"status": "ok", "data": {"lock_count": 0}},
    }


@pytest.fixture
def sample_initiatives():
    """Minimal remediation item list for testing."""
    return [
        {
            "checklist_id": "D07.01",
            "title": "Deploy hub-spoke network with Azure Firewall",
            "priority": 1,
            "blast_radius": "High",
            "caf_discipline": "Network Topology & Connectivity",
            "controls": ["CTRL-NET-001", "CTRL-NET-002"],
            "dependencies": [],
        },
        {
            "checklist_id": "E01.01",
            "title": "Centralise logging and monitoring",
            "priority": 2,
            "blast_radius": "High",
            "caf_discipline": "Management",
            "controls": ["CTRL-MGMT-001"],
            "dependencies": ["D07.01"],
        },
        {
            "checklist_id": "F01.01",
            "title": "Enable Microsoft Defender for Cloud",
            "priority": 3,
            "blast_radius": "Medium",
            "caf_discipline": "Security",
            "controls": ["CTRL-SEC-001"],
            "dependencies": ["E01.01"],
        },
    ]


@pytest.fixture
def sample_top_risks():
    return [
        {
            "title": "Network exposure risk",
            "business_impact": "Unauthorised access",
            "technical_cause": "No firewall",
            "severity": "Critical",
            "affected_controls": ["CTRL-NET-001"],
        },
    ]


@pytest.fixture
def sample_blockers():
    return [
        {
            "category": "Networking",
            "description": "No hub-spoke topology",
            "severity": "Critical",
            "resolving_checklist_ids": ["D07.01"],
        },
    ]


@pytest.fixture
def sample_section_scores():
    return [
        {"section": "Networking", "maturity_percent": 33},
        {"section": "Management", "maturity_percent": 20},
        {"section": "Security", "maturity_percent": 50},
        {"section": "Identity & Access", "maturity_percent": 40},
    ]


# ── T-1: evidence_refs empty → FAIL ─────────────────────────────

class TestEvidenceRefs:
    def test_empty_evidence_refs_detected(self):
        item = {"evidence_refs": empty_evidence_refs(), "assumptions": []}
        violations = validate_evidence_refs(item, "test_item")
        assert len(violations) > 0, "Should flag empty evidence_refs"

    def test_populated_evidence_refs_pass(self):
        item = {
            "evidence_refs": {
                "controls": ["CTRL-001"],
                "risks": [],
                "blockers": [],
                "signals": ["signal:rbac_hygiene"],
                "mcp_queries": [],
            },
            "assumptions": ["Test assumption"],
        }
        violations = validate_evidence_refs(item, "test_item")
        assert violations == [], f"Should pass but got: {violations}"

    def test_missing_assumptions_flagged(self):
        item = {
            "evidence_refs": {
                "controls": ["CTRL-001"],
                "risks": [],
                "blockers": [],
                "signals": [],
                "mcp_queries": [],
            },
            # No "assumptions" key
        }
        violations = validate_evidence_refs(item, "test_item")
        assert any("assumptions" in v for v in violations)

    def test_merge_evidence_refs(self):
        a = {"controls": ["C1"], "risks": ["R1"], "blockers": [], "signals": [], "mcp_queries": []}
        b = {"controls": ["C1", "C2"], "risks": [], "blockers": ["B1"], "signals": [], "mcp_queries": []}
        merged = merge_evidence_refs(a, b)
        assert "C1" in merged["controls"]
        assert "C2" in merged["controls"]
        assert merged["controls"].count("C1") == 1, "Should deduplicate"
        assert "R1" in merged["risks"]
        assert "B1" in merged["blockers"]


# ── T-2: cost numbers in category_only mode → FAIL ──────────────

class TestCostGuardrail:
    def test_dollar_amount_flagged_in_category_mode(self):
        violations = check_no_cost_numbers(
            "This will cost approximately $500/month for the firewall.",
            "category_only",
        )
        assert len(violations) > 0, "Dollar amount should be flagged"

    def test_dollar_amount_allowed_in_tool_backed(self):
        violations = check_no_cost_numbers(
            "Azure Firewall costs $500/month based on pricing API.",
            "tool_backed",
        )
        assert violations == [], "Dollar amounts allowed when tool_backed"

    def test_category_label_passes(self):
        violations = check_no_cost_numbers(
            "Estimated cost category: High",
            "category_only",
        )
        assert violations == [], "Category labels should pass"

    def test_cost_simulation_category_mode(self, sample_initiatives, sample_results):
        sim = build_cost_simulation(sample_initiatives, sample_results, mcp_pricing_available=False)
        assert sim["mode"] == "category_only"
        for driver in sim["drivers"]:
            # No dollar amounts in any field
            for field_val in driver.values():
                if isinstance(field_val, str):
                    violations = check_no_cost_numbers(field_val, sim["mode"])
                    assert violations == [], f"Cost number in {field_val}"


# ── T-3: compliance pass/fail language → FAIL ────────────────────

class TestComplianceGuardrail:
    def test_passes_hipaa_flagged(self):
        violations = check_no_compliance_claims("This configuration passes HIPAA requirements.")
        assert len(violations) > 0

    def test_fails_pci_flagged(self):
        violations = check_no_compliance_claims("Your setup fails PCI-DSS controls.")
        assert len(violations) > 0

    def test_compliant_with_soc2_flagged(self):
        violations = check_no_compliance_claims("The environment is compliant with SOC 2.")
        assert len(violations) > 0

    def test_regulated_environment_language_passes(self):
        violations = check_no_compliance_claims(
            "This configuration is commonly required in regulated environments."
        )
        assert violations == []

    def test_general_security_language_passes(self):
        violations = check_no_compliance_claims(
            "Improve your security posture with Defender for Cloud."
        )
        assert violations == []


# ── T-4: 'High confidence' without computed basis → FAIL ────────

class TestConfidenceGuardrail:
    def test_high_confidence_without_basis_flagged(self):
        violations = check_confidence_has_basis(
            "We have high confidence that this will work.",
            None,
        )
        assert len(violations) > 0

    def test_high_confidence_with_basis_passes(self):
        violations = check_confidence_has_basis(
            "We have high confidence that this will work.",
            {"value": 0.85, "basis": "avg_control=0.9, coverage=70%", "label": "High"},
        )
        assert violations == []

    def test_no_confidence_mention_passes(self):
        violations = check_confidence_has_basis(
            "Deploy Azure Firewall for centralized inspection.",
            None,
        )
        assert violations == []

    def test_computed_confidence_formula(self):
        conf = compute_derived_confidence([0.8, 0.9, 0.7], 80.0)
        assert 0.0 <= conf["value"] <= 1.0
        assert conf["label"] in ("None", "Low", "Medium", "High")
        assert "avg_control" in conf["basis"]
        assert "signal_coverage" in conf["basis"]

    def test_empty_controls_returns_none(self):
        conf = compute_derived_confidence([], 50.0)
        assert conf["value"] == 0.0
        assert conf["label"] == "None"


# ── T-5: recommendation without doc_ref → FAIL ──────────────────

class TestDocRefGuardrail:
    def test_empty_doc_refs_flagged(self):
        violations = validate_doc_refs("Identity", [])
        assert len(violations) > 0

    def test_doc_ref_missing_url_flagged(self):
        violations = validate_doc_refs("Identity", [{"title": "Test"}])
        assert any("url" in v for v in violations)

    def test_valid_doc_ref_passes(self):
        violations = validate_doc_refs("Identity", [
            {"title": "RBAC Best Practices", "url": "https://learn.microsoft.com/azure/rbac"}
        ])
        assert violations == []


# ── T-6: scaling simulation requires rule_id ─────────────────────

class TestScalingSimulation:
    def test_all_impacts_have_rule_id(self, sample_results, sample_signals):
        sim = build_scaling_simulation(sample_results, sample_signals, {"subscription_count_visible": 1})
        for scenario in sim["scenarios"]:
            for impact in scenario["derived_impacts"]:
                assert "rule_id" in impact, f"Missing rule_id in {impact}"
                assert impact["rule_id"].startswith("RULE-"), f"Invalid rule_id: {impact['rule_id']}"

    def test_all_impacts_have_evidence_refs(self, sample_results, sample_signals):
        sim = build_scaling_simulation(sample_results, sample_signals, {"subscription_count_visible": 1})
        for scenario in sim["scenarios"]:
            for impact in scenario["derived_impacts"]:
                refs = impact["evidence_refs"]
                assert "controls" in refs
                assert "signals" in refs
                assert len(refs["signals"]) > 0, "Scaling impact must reference at least one signal"

    def test_all_impacts_have_assumptions(self, sample_results, sample_signals):
        sim = build_scaling_simulation(sample_results, sample_signals, {"subscription_count_visible": 1})
        for scenario in sim["scenarios"]:
            for impact in scenario["derived_impacts"]:
                assert "assumptions" in impact
                assert len(impact["assumptions"]) > 0

    def test_skips_scenarios_at_or_below_current(self, sample_results, sample_signals):
        sim = build_scaling_simulation(sample_results, sample_signals, {"subscription_count_visible": 10})
        scenario_names = [s["scenario"] for s in sim["scenarios"]]
        assert "5_subscriptions" not in scenario_names
        assert "10_subscriptions" not in scenario_names
        assert "50_subscriptions" in scenario_names

    def test_rule_ids_are_valid(self):
        """All rules in the ruleset follow the RULE-XXX-NNN pattern."""
        import re
        pattern = re.compile(r"^RULE-[A-Z]+-\d{3}$")
        for rule_id in SCALING_RULES:
            assert pattern.match(rule_id), f"Invalid rule_id: {rule_id}"


# ── T-7: drift model deterministic ──────────────────────────────

class TestDriftModel:
    def test_deterministic_output(self, sample_results, sample_signals):
        dm1 = build_drift_model(sample_results, sample_signals)
        dm2 = build_drift_model(sample_results, sample_signals)
        assert dm1["drift_score"] == dm2["drift_score"], "Drift model must be deterministic"
        assert dm1["drift_likelihood"] == dm2["drift_likelihood"]

    def test_has_required_fields(self, sample_results, sample_signals):
        dm = build_drift_model(sample_results, sample_signals)
        for field in ("mode", "drift_likelihood", "drift_score", "active_factors",
                       "confidence", "evidence_refs", "assumptions"):
            assert field in dm, f"Missing field: {field}"

    def test_evidence_refs_populated(self, sample_results, sample_signals):
        dm = build_drift_model(sample_results, sample_signals)
        violations = validate_evidence_refs(dm, "drift_model")
        assert violations == [], f"Drift model evidence violations: {violations}"

    def test_drift_score_range(self, sample_results, sample_signals):
        dm = build_drift_model(sample_results, sample_signals)
        assert 0.0 <= dm["drift_score"] <= 1.0

    def test_static_mode_without_activity_log(self, sample_results, sample_signals):
        dm = build_drift_model(sample_results, sample_signals)
        assert dm["mode"] == "static"

    def test_activity_log_backed_mode(self, sample_results, sample_signals):
        activity = {"status": "ok", "data": {"change_count_30d": 100}}
        dm = build_drift_model(sample_results, sample_signals, activity_log_signal=activity)
        assert dm["mode"] == "activity_log_backed"


# ── T-8: decision impact deterministic ───────────────────────────

class TestDecisionImpact:
    def test_deterministic_output(self, sample_initiatives, sample_results,
                                   sample_top_risks, sample_blockers,
                                   sample_section_scores, sample_signals):
        dim1 = build_decision_impact_model(
            sample_initiatives, sample_results, sample_top_risks,
            sample_blockers, sample_section_scores, sample_signals,
        )
        dim2 = build_decision_impact_model(
            sample_initiatives, sample_results, sample_top_risks,
            sample_blockers, sample_section_scores, sample_signals,
        )
        assert len(dim1["items"]) == len(dim2["items"])
        for i1, i2 in zip(dim1["items"], dim2["items"]):
            assert i1["checklist_id"] == i2["checklist_id"]
            assert i1["confidence"]["value"] == i2["confidence"]["value"]

    def test_all_items_have_evidence_refs(self, sample_initiatives, sample_results,
                                           sample_top_risks, sample_blockers,
                                           sample_section_scores, sample_signals):
        dim = build_decision_impact_model(
            sample_initiatives, sample_results, sample_top_risks,
            sample_blockers, sample_section_scores, sample_signals,
        )
        for item in dim["items"]:
            violations = validate_evidence_refs(item, f"DIM[{item['checklist_id']}]")
            assert violations == [], f"Violations: {violations}"

    def test_blocker_maps_to_enterprise_blocked(self, sample_initiatives, sample_results,
                                                  sample_top_risks, sample_blockers,
                                                  sample_section_scores, sample_signals):
        dim = build_decision_impact_model(
            sample_initiatives, sample_results, sample_top_risks,
            sample_blockers, sample_section_scores, sample_signals,
        )
        item_d07 = next(i for i in dim["items"] if i["checklist_id"] == "D07.01")
        assert item_d07["if_not_implemented"]["enterprise_scale_blocked"] is True

    def test_dependency_blocking(self, sample_initiatives, sample_results,
                                  sample_top_risks, sample_blockers,
                                  sample_section_scores, sample_signals):
        dim = build_decision_impact_model(
            sample_initiatives, sample_results, sample_top_risks,
            sample_blockers, sample_section_scores, sample_signals,
        )
        item_d07 = next(i for i in dim["items"] if i["checklist_id"] == "D07.01")
        assert "E01.01" in item_d07["if_not_implemented"]["blocked_items"]


# ── T-9: cost simulation no dollars in category mode ─────────────

class TestCostSimulationIntegration:
    def test_no_dollar_amounts(self, sample_initiatives, sample_results):
        sim = build_cost_simulation(sample_initiatives, sample_results, mcp_pricing_available=False)
        assert sim["mode"] == "category_only"
        # Walk all string values
        def walk_strings(obj):
            if isinstance(obj, str):
                yield obj
            elif isinstance(obj, dict):
                for v in obj.values():
                    yield from walk_strings(v)
            elif isinstance(obj, (list, tuple)):
                for v in obj:
                    yield from walk_strings(v)

        for text in walk_strings(sim):
            violations = check_no_cost_numbers(text, "category_only")
            assert violations == [], f"Dollar amount in cost_simulation: {violations}"

    def test_all_drivers_have_evidence_refs(self, sample_initiatives, sample_results):
        sim = build_cost_simulation(sample_initiatives, sample_results)
        for driver in sim["drivers"]:
            violations = validate_evidence_refs(driver, f"cost[{driver['checklist_id']}]")
            assert violations == [], f"Violations: {violations}"


# ── T-10: full pipeline validate_anti_drift ──────────────────────

class TestFullPipelineValidation:
    def test_clean_output_passes(self, sample_results, sample_signals,
                                   sample_initiatives, sample_top_risks,
                                   sample_blockers, sample_section_scores):
        """Build all 4 derived models and validate the assembled output."""
        scaling = build_scaling_simulation(
            sample_results, sample_signals, {"subscription_count_visible": 1},
        )
        drift = build_drift_model(sample_results, sample_signals)
        cost = build_cost_simulation(sample_initiatives, sample_results)
        impact = build_decision_impact_model(
            sample_initiatives, sample_results, sample_top_risks,
            sample_blockers, sample_section_scores, sample_signals,
        )

        output = {
            "scaling_simulation": scaling,
            "drift_model": drift,
            "cost_simulation": cost,
            "decision_impact_model": impact,
        }

        violations = validate_anti_drift(output)
        assert violations == [], f"Anti-drift violations:\n" + "\n".join(violations)

    def test_injected_compliance_language_caught(self, sample_results, sample_signals,
                                                   sample_initiatives, sample_top_risks,
                                                   sample_blockers, sample_section_scores):
        """Insert compliance language and prove the guardrail catches it."""
        drift = build_drift_model(sample_results, sample_signals)
        # Inject violation
        drift["assumptions"].append("This configuration passes HIPAA requirements.")

        output = {
            "scaling_simulation": {"scenarios": []},
            "drift_model": drift,
            "cost_simulation": {"mode": "category_only", "drivers": []},
            "decision_impact_model": {"items": []},
        }

        violations = validate_anti_drift(output)
        assert any("HIPAA" in v for v in violations), \
            f"Should catch HIPAA compliance claim but got: {violations}"

    def test_empty_evidence_refs_caught(self):
        """An item with empty evidence_refs must be flagged."""
        output = {
            "scaling_simulation": {"scenarios": []},
            "drift_model": {
                "mode": "static",
                "drift_likelihood": "Low",
                "drift_score": 0.0,
                "active_factors": [],
                "confidence": {"value": 0.5, "basis": "test", "label": "Medium"},
                "evidence_refs": empty_evidence_refs(),  # ALL EMPTY
                "assumptions": ["test"],
            },
            "cost_simulation": {"mode": "category_only", "drivers": []},
            "decision_impact_model": {"items": []},
        }

        violations = validate_anti_drift(output)
        assert any("evidence_refs is empty" in v for v in violations)


# ── Schema compliance ────────────────────────────────────────────

class TestSchemaCompliance:
    def test_schema_has_new_objects(self):
        """Verify copilot_output.schema.json includes all 4 new top-level objects."""
        schema_path = Path(__file__).parent / "ai" / "schemas" / "copilot_output.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        props = schema["properties"]
        for key in ("decision_impact_model", "scaling_simulation", "drift_model", "cost_simulation", "evidence_refs"):
            assert key in props, f"Schema missing '{key}' property"

    def test_evidence_refs_schema_structure(self):
        schema_path = Path(__file__).parent / "ai" / "schemas" / "copilot_output.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        er = schema["properties"]["evidence_refs"]
        assert "controls" in er["properties"]
        assert "signals" in er["properties"]
        assert er["required"] == ["controls", "signals"]
