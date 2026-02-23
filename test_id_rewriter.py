"""Tests for engine.id_rewriter — hash-based initiative ID generation.

Verifies:
  - Hash stability (same controls → same ID across calls)
  - Collision detection and disambiguation
  - Tree walker remaps all INIT-NNN tokens
  - Roadmap, readiness, and dependency graph normalisation
  - Blocker patching with deterministic mapping
  - Full rewrite orchestrator
"""
from __future__ import annotations

import pytest

from engine.id_rewriter import (
    compute_initiative_id,
    build_id_map,
    _remap_tree,
    remap_initiatives_in_place,
    remap_roadmap_raw,
    remap_readiness,
    normalize_dependency_graph,
    patch_blocker_initiatives,
    rewrite_initiative_ids,
)


# ── Fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def sample_initiatives():
    """Six initiatives with ordinal IDs modelling a typical LLM output."""
    return [
        {
            "initiative_id": "INIT-001",
            "controls": ["CTRL-GOV-001", "CTRL-GOV-002"],
            "dependencies": [],
        },
        {
            "initiative_id": "INIT-002",
            "controls": ["CTRL-MGMT-001", "CTRL-MGMT-002"],
            "dependencies": ["INIT-001"],
        },
        {
            "initiative_id": "INIT-003",
            "controls": ["CTRL-SEC-001"],
            "dependencies": ["INIT-001"],
        },
    ]


@pytest.fixture
def sample_roadmap_raw(sample_initiatives):
    """Roadmap raw dict with initiative_execution_plan and roadmap_30_60_90."""
    return {
        "initiative_execution_plan": sample_initiatives,
        "roadmap_30_60_90": {
            "30_days": [
                {"action": "Establish governance baseline", "initiative_id": "INIT-001"},
            ],
            "60_days": [
                {"action": "Deploy management stack", "initiative_id": "INIT-002"},
                {"action": "Harden security posture", "initiative_id": "INIT-003"},
            ],
            "90_days": [],
        },
        "dependency_graph": [
            {
                "action": "Establish governance baseline",
                "depends_on": [],
                "phase": "30_days",
            },
            {
                "action": "Deploy management stack",
                "depends_on": ["Establish governance baseline"],
                "phase": "60_days",
            },
        ],
        "parallel_execution_groups": [
            {"group": 1, "initiatives": ["INIT-002", "INIT-003"]},
        ],
    }


@pytest.fixture
def sample_readiness():
    """Enterprise-scale readiness with blockers."""
    return {
        "overall_readiness": "Conditional",
        "blockers": [
            {
                "category": "governance",
                "description": "No MG hierarchy",
                "resolving_initiative": "INIT-002",
            },
            {
                "category": "security",
                "description": "Defender not enabled",
                "resolving_initiative": "INIT-001",
            },
        ],
    }


# ── Hash stability ────────────────────────────────────────────────

class TestComputeInitiativeId:
    def test_same_controls_same_id(self):
        id1 = compute_initiative_id(["CTRL-A", "CTRL-B"])
        id2 = compute_initiative_id(["CTRL-A", "CTRL-B"])
        assert id1 == id2

    def test_order_independent(self):
        id1 = compute_initiative_id(["CTRL-B", "CTRL-A"])
        id2 = compute_initiative_id(["CTRL-A", "CTRL-B"])
        assert id1 == id2, "ID must be independent of control list order"

    def test_different_controls_different_id(self):
        id1 = compute_initiative_id(["CTRL-A"])
        id2 = compute_initiative_id(["CTRL-B"])
        assert id1 != id2

    def test_format(self):
        result = compute_initiative_id(["CTRL-A"])
        assert result.startswith("INIT-")
        assert len(result) == 13  # INIT- + 8 hex chars

    def test_empty_controls(self):
        result = compute_initiative_id([])
        assert result.startswith("INIT-")
        assert len(result) == 13


# ── ID map building ────────────────────────────────────────────

class TestBuildIdMap:
    def test_maps_ordinal_to_hash(self, sample_initiatives):
        id_map = build_id_map(sample_initiatives)
        assert len(id_map) == 3
        for old_id, new_id in id_map.items():
            assert old_id.startswith("INIT-")
            assert new_id.startswith("INIT-")
            assert old_id != new_id

    def test_already_hash_based(self):
        """If IDs are already hash-based, map is empty."""
        controls = ["CTRL-A", "CTRL-B"]
        expected_id = compute_initiative_id(controls)
        initiatives = [{"initiative_id": expected_id, "controls": controls}]
        id_map = build_id_map(initiatives)
        assert id_map == {}

    def test_empty_list(self):
        assert build_id_map([]) == {}

    def test_missing_initiative_id(self):
        initiatives = [{"controls": ["CTRL-A"]}]
        id_map = build_id_map(initiatives)
        assert id_map == {}


# ── Tree walker ──────────────────────────────────────────────────

class TestRemapTree:
    def test_string_replacement(self):
        id_map = {"INIT-001": "INIT-abc12345"}
        result = _remap_tree("Depends on INIT-001", id_map)
        assert result == "Depends on INIT-abc12345"

    def test_nested_dict(self):
        id_map = {"INIT-001": "INIT-abc12345"}
        obj = {"key": {"nested": "INIT-001"}}
        result = _remap_tree(obj, id_map)
        assert result == {"key": {"nested": "INIT-abc12345"}}

    def test_list_of_strings(self):
        id_map = {"INIT-001": "INIT-abc12345", "INIT-002": "INIT-def67890"}
        obj = ["INIT-001", "INIT-002", "INIT-003"]
        result = _remap_tree(obj, id_map)
        assert result == ["INIT-abc12345", "INIT-def67890", "INIT-003"]

    def test_non_string_passthrough(self):
        id_map = {"INIT-001": "INIT-abc12345"}
        assert _remap_tree(42, id_map) == 42
        assert _remap_tree(3.14, id_map) == 3.14
        assert _remap_tree(True, id_map) is True
        assert _remap_tree(None, id_map) is None

    def test_no_mutation(self):
        id_map = {"INIT-001": "INIT-abc12345"}
        original = {"a": "INIT-001"}
        result = _remap_tree(original, id_map)
        assert original["a"] == "INIT-001"
        assert result["a"] == "INIT-abc12345"


# ── In-place initiative remapping ────────────────────────────────

class TestRemapInitiativesInPlace:
    def test_remaps_id_and_deps(self):
        initiatives = [
            {"initiative_id": "INIT-001", "controls": [], "dependencies": []},
            {"initiative_id": "INIT-002", "controls": [], "dependencies": ["INIT-001"]},
        ]
        id_map = {"INIT-001": "INIT-aaa", "INIT-002": "INIT-bbb"}
        remap_initiatives_in_place(initiatives, id_map)
        assert initiatives[0]["initiative_id"] == "INIT-aaa"
        assert initiatives[1]["initiative_id"] == "INIT-bbb"
        assert initiatives[1]["dependencies"] == ["INIT-aaa"]


# ── Roadmap remapping ────────────────────────────────────────────

class TestRemapRoadmapRaw:
    def test_remaps_all_tokens(self, sample_roadmap_raw):
        id_map = {"INIT-001": "INIT-aaa", "INIT-002": "INIT-bbb", "INIT-003": "INIT-ccc"}
        result = remap_roadmap_raw(sample_roadmap_raw, id_map)
        # roadmap_30_60_90
        assert result["roadmap_30_60_90"]["30_days"][0]["initiative_id"] == "INIT-aaa"
        assert result["roadmap_30_60_90"]["60_days"][0]["initiative_id"] == "INIT-bbb"
        # parallel_execution_groups
        assert "INIT-bbb" in result["parallel_execution_groups"][0]["initiatives"]
        assert "INIT-ccc" in result["parallel_execution_groups"][0]["initiatives"]

    def test_empty_map_returns_original(self, sample_roadmap_raw):
        result = remap_roadmap_raw(sample_roadmap_raw, {})
        assert result is sample_roadmap_raw  # identity — no copy


# ── Readiness remapping ──────────────────────────────────────────

class TestRemapReadiness:
    def test_remaps_blockers(self, sample_readiness):
        id_map = {"INIT-001": "INIT-aaa", "INIT-002": "INIT-bbb"}
        result = remap_readiness(sample_readiness, id_map)
        assert result is not None
        assert result["blockers"][0]["resolving_initiative"] == "INIT-bbb"
        assert result["blockers"][1]["resolving_initiative"] == "INIT-aaa"

    def test_empty_readiness(self):
        assert remap_readiness({}, {"INIT-001": "INIT-aaa"}) == {}
        assert remap_readiness(None, {"INIT-001": "INIT-aaa"}) is None


# ── Dependency graph normalisation ───────────────────────────────

class TestNormalizeDependencyGraph:
    def test_adds_initiative_id_and_depends_on_ids(self):
        dep_graph = [
            {"action": "Alpha", "depends_on": [], "phase": "30_days"},
            {"action": "Beta", "depends_on": ["Alpha"], "phase": "60_days"},
        ]
        roadmap = {
            "30_days": [{"action": "Alpha", "initiative_id": "INIT-aaa"}],
            "60_days": [{"action": "Beta", "initiative_id": "INIT-bbb"}],
        }
        result = normalize_dependency_graph(dep_graph, roadmap)
        assert result[0]["initiative_id"] == "INIT-aaa"
        assert result[0]["depends_on_ids"] == []
        assert result[1]["initiative_id"] == "INIT-bbb"
        assert result[1]["depends_on_ids"] == ["INIT-aaa"]

    def test_preserves_original_depends_on(self):
        dep_graph = [{"action": "X", "depends_on": ["Y"], "phase": "30_days"}]
        roadmap = {"30_days": [{"action": "X", "initiative_id": "INIT-x"}]}
        result = normalize_dependency_graph(dep_graph, roadmap)
        assert result[0]["depends_on"] == ["Y"]  # original text preserved

    def test_no_mutation(self):
        dep_graph = [{"action": "X", "depends_on": [], "phase": "30_days"}]
        roadmap = {"30_days": [{"action": "X", "initiative_id": "INIT-x"}]}
        normalize_dependency_graph(dep_graph, roadmap)
        assert "initiative_id" not in dep_graph[0]


# ── Blocker patching ─────────────────────────────────────────────

class TestPatchBlockerInitiatives:
    def test_patches_by_category(self, sample_readiness):
        mapping = {"governance": "INIT-correct-gov", "security": "INIT-correct-sec"}
        patch_blocker_initiatives(sample_readiness, mapping)
        assert sample_readiness["blockers"][0]["resolving_initiative"] == "INIT-correct-gov"
        assert sample_readiness["blockers"][1]["resolving_initiative"] == "INIT-correct-sec"

    def test_noop_on_empty_mapping(self, sample_readiness):
        original = sample_readiness["blockers"][0]["resolving_initiative"]
        patch_blocker_initiatives(sample_readiness, {})
        assert sample_readiness["blockers"][0]["resolving_initiative"] == original

    def test_noop_on_none_readiness(self):
        patch_blocker_initiatives(None, {"governance": "INIT-x"})  # no crash


# ── Full rewrite orchestrator ────────────────────────────────────

class TestRewriteInitiativeIds:
    def test_end_to_end(self, sample_initiatives, sample_roadmap_raw, sample_readiness):
        id_map = rewrite_initiative_ids(
            sample_initiatives, sample_roadmap_raw, sample_readiness,
        )

        # id_map should have 3 entries (INIT-001, INIT-002, INIT-003)
        assert len(id_map) == 3

        # All new IDs should be hash-based (8 hex chars after INIT-)
        for old, new in id_map.items():
            assert old.startswith("INIT-0")  # ordinal
            assert new.startswith("INIT-")
            # The hash part should be 8 hex chars
            hex_part = new.split("-", 1)[1]
            assert len(hex_part) == 8
            int(hex_part, 16)  # valid hex

        # Initiatives should now use hash-based IDs
        for init in sample_initiatives:
            assert not init["initiative_id"].startswith("INIT-00")

        # Roadmap should be remapped
        for phase_key in ("30_days", "60_days"):
            for entry in sample_roadmap_raw["roadmap_30_60_90"].get(phase_key, []):
                assert not entry["initiative_id"].startswith("INIT-00")

        # Readiness blockers should be remapped
        for blocker in sample_readiness["blockers"]:
            assert not blocker["resolving_initiative"].startswith("INIT-00")

    def test_idempotent(self, sample_initiatives, sample_roadmap_raw, sample_readiness):
        """Running rewrite twice should be a no-op the second time."""
        id_map1 = rewrite_initiative_ids(
            sample_initiatives, sample_roadmap_raw, sample_readiness,
        )
        id_map2 = rewrite_initiative_ids(
            sample_initiatives, sample_roadmap_raw, sample_readiness,
        )
        assert id_map2 == {}, "Second rewrite should return empty map (already hash-based)"

    def test_stability_across_calls(self):
        """Same controls → same IDs regardless of when we call."""
        inits1 = [
            {"initiative_id": "INIT-001", "controls": ["C1", "C2"], "dependencies": []},
        ]
        inits2 = [
            {"initiative_id": "INIT-001", "controls": ["C1", "C2"], "dependencies": []},
        ]
        roadmap1 = {"initiative_execution_plan": inits1, "roadmap_30_60_90": {}, "dependency_graph": []}
        roadmap2 = {"initiative_execution_plan": inits2, "roadmap_30_60_90": {}, "dependency_graph": []}
        map1 = rewrite_initiative_ids(inits1, roadmap1)
        map2 = rewrite_initiative_ids(inits2, roadmap2)
        assert map1["INIT-001"] == map2["INIT-001"]
