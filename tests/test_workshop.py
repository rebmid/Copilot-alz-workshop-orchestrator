# tests/test_workshop.py — Minimal workshop tool tests
#
# 4 tests:
#   1. load_results("latest") returns valid metadata
#   2. ensure_out_path rejects paths outside out/
#   3. summarize_findings respects design_area filter
#   4. Smoke: session module imports and exposes exactly 4 tools
# ──────────────────────────────────────────────────────────────────

import json
import os
import sys
from pathlib import Path

import pytest

# Ensure project root is importable
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ══════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def _seed_demo_run(tmp_path, monkeypatch):
    """Copy demo_run.json into a temporary out/ dir and patch OUT_DIR."""
    import src.workshop_tools as workshop_tools

    demo_src = ROOT / "demo" / "demo_run.json"
    if not demo_src.exists():
        pytest.skip("demo/demo_run.json not found")

    out = tmp_path / "out"
    out.mkdir()
    dest = out / "run-20260214-0000.json"
    dest.write_text(demo_src.read_text(encoding="utf-8"), encoding="utf-8")

    # Patch OUT_DIR and clear run cache between tests
    monkeypatch.setattr(workshop_tools, "OUT_DIR", out.resolve())
    workshop_tools._run_cache.clear()
    yield


# ══════════════════════════════════════════════════════════════════
# Test 1 — load_results("latest")
# ══════════════════════════════════════════════════════════════════

def test_load_results_latest():
    from src.workshop_tools import load_results, LoadResultsParams

    result = json.loads(load_results(LoadResultsParams(run_id="latest")))

    assert "error" not in result
    assert result["run_id"] == "DEMO-LAB-ALZ-ASSESSMENT"
    assert result["total_controls"] == 243
    assert result["cached"] is True


# ══════════════════════════════════════════════════════════════════
# Test 2 — guardrail rejects paths outside out/
# ══════════════════════════════════════════════════════════════════

def test_guardrail_rejects_outside_out():
    from src.workshop_tools import ensure_out_path

    with pytest.raises(ValueError, match="Write outside out/ directory not allowed"):
        ensure_out_path(Path.home() / "Desktop" / "evil.json")


# ══════════════════════════════════════════════════════════════════
# Test 3 — summarize_findings respects design_area filter
# ══════════════════════════════════════════════════════════════════

def test_summarize_filter_design_area():
    from src.workshop_tools import summarize_findings, SummarizeFindingsParams

    result = json.loads(summarize_findings(SummarizeFindingsParams(
        run_id="latest",
        design_area="Security",
    )))

    assert "error" not in result
    assert result["matched"] <= result["total_controls"]
    # Every returned item must belong to our filter
    for item in result["top_items"]:
        assert item["section"].lower() == "security", (
            f"Item {item['control_id']} has section {item['section']!r}, expected 'Security'"
        )


# ══════════════════════════════════════════════════════════════════
# Test 4 — Smoke: module imports, exposes exactly 4 tools
# ══════════════════════════════════════════════════════════════════

def test_session_smoke_4_tools():
    import src.workshop_copilot as workshop_copilot

    assert hasattr(workshop_copilot, "TOOLS")
    assert len(workshop_copilot.TOOLS) == 4

    expected_names = {"run_scan", "load_results", "summarize_findings", "generate_outputs"}
    actual_names = {t.name for t in workshop_copilot.TOOLS}
    assert actual_names == expected_names

    # Verify caching state vars exist
    assert hasattr(workshop_copilot, "active_run_id")
    assert hasattr(workshop_copilot, "active_results")
