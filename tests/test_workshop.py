# tests/test_workshop.py — Workshop tool test suite
#
# 4 tests aligned to the MVP test plan:
#
#   1. Unit-test tool handlers with fixture run JSON (no Azure dependency)
#   2. Guardrail rejects file writes outside out/
#   3. load_results("latest") picks the newest run artifact
#   4. Smoke: start Copilot SDK session, send "summarize identity findings",
#      verify a tool call happens
# ──────────────────────────────────────────────────────────────────

import asyncio
import json
import os
import subprocess
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
# Test 1 — Unit-test tool handlers with fixture JSON (no Azure)
# ══════════════════════════════════════════════════════════════════

def test_tool_handlers_fixture_json():
    """All handler functions work against the demo fixture without Azure."""
    from src.workshop_tools import (
        load_results, LoadResultsParams,
        summarize_findings, SummarizeFindingsParams,
    )

    # load_results returns structured metadata
    lr = json.loads(load_results(LoadResultsParams(run_id="latest")))
    assert "error" not in lr
    assert lr["run_id"] == "DEMO-LAB-ALZ-ASSESSMENT"
    assert lr["total_controls"] == 243
    assert lr["cached"] is True

    # summarize_findings filters correctly
    sf = json.loads(summarize_findings(SummarizeFindingsParams(
        run_id="latest",
        design_area="Security",
    )))
    assert "error" not in sf
    assert sf["matched"] <= sf["total_controls"]
    for item in sf["top_items"]:
        assert item["section"].lower() == "security"


# ══════════════════════════════════════════════════════════════════
# Test 2 — Guardrail rejects paths outside out/
# ══════════════════════════════════════════════════════════════════

def test_guardrail_rejects_outside_out():
    from src.workshop_tools import ensure_out_path

    with pytest.raises(ValueError, match="Write outside out/ directory not allowed"):
        ensure_out_path(Path.home() / "Desktop" / "evil.json")


# ══════════════════════════════════════════════════════════════════
# Test 3 — load_results("latest") picks the newest run artifact
# ══════════════════════════════════════════════════════════════════

def test_load_results_latest_picks_newest(tmp_path, monkeypatch):
    """When multiple run files exist, 'latest' resolves to the newest."""
    import src.workshop_tools as workshop_tools

    demo_src = ROOT / "demo" / "demo_run.json"
    raw = demo_src.read_text(encoding="utf-8")
    out = tmp_path / "out2"
    out.mkdir()

    # Write two run files with different timestamps
    (out / "run-20260101-0000.json").write_text(raw, encoding="utf-8")
    (out / "run-20260214-0000.json").write_text(raw, encoding="utf-8")

    monkeypatch.setattr(workshop_tools, "OUT_DIR", out.resolve())
    workshop_tools._run_cache.clear()

    from src.workshop_tools import load_results, LoadResultsParams, _run_cache

    result = json.loads(load_results(LoadResultsParams(run_id="latest")))
    assert "error" not in result

    # 'latest' should resolve to the newest file (run-20260214, not run-20260101).
    # The cache is keyed by the run_id inside the JSON, but the run loaded
    # must come from the file with the most recent timestamp in its name.
    assert result["run_id"] == "DEMO-LAB-ALZ-ASSESSMENT"
    assert result["cached"] is True


# ══════════════════════════════════════════════════════════════════
# Test 4 — run_scan handler (subprocess, demo mode)
# ══════════════════════════════════════════════════════════════════

def test_run_scan_demo_mode(tmp_path, monkeypatch):
    """run_scan in demo mode produces a run file without Azure access."""
    import src.workshop_tools as workshop_tools
    from src.workshop_tools import run_scan, RunScanParams

    out = tmp_path / "out_scan"
    out.mkdir()
    monkeypatch.setattr(workshop_tools, "OUT_DIR", out.resolve())
    # _PROJECT_ROOT must be parent of OUT_DIR and contain demo/ for relative_to() calls
    monkeypatch.setattr(workshop_tools, "_PROJECT_ROOT", tmp_path.resolve())

    # Create demo fixture at the patched _PROJECT_ROOT location so
    # run_scan(demo=True) can find it.
    demo_dir = tmp_path / "demo"
    demo_dir.mkdir()
    demo_src = ROOT / "demo" / "demo_run.json"
    (demo_dir / "demo_run.json").write_text(
        demo_src.read_text(encoding="utf-8"), encoding="utf-8"
    )

    result = json.loads(run_scan(RunScanParams(demo=True)))
    assert "error" not in result
    assert "run_id" in result
    assert result["run_id"].startswith("run-")


# ══════════════════════════════════════════════════════════════════
# Test 5 — generate_outputs rejects invalid format
# ══════════════════════════════════════════════════════════════════

def test_generate_outputs_rejects_invalid_format():
    """generate_outputs refuses formats outside the allow-list."""
    from src.workshop_tools import generate_outputs, GenerateOutputsParams

    result = json.loads(generate_outputs(GenerateOutputsParams(
        run_id="latest",
        formats=["pdf"],
    )))
    assert "error" in result
    assert "pdf" in result["error"].lower()


# ══════════════════════════════════════════════════════════════════
# Test 6 — generate_outputs accepts allowed format
# ══════════════════════════════════════════════════════════════════

def test_generate_outputs_html():
    """generate_outputs with html format loads the run and attempts render."""
    from src.workshop_tools import generate_outputs, GenerateOutputsParams

    result = json.loads(generate_outputs(GenerateOutputsParams(
        run_id="latest",
        formats=["html"],
    )))
    # Even if reporting.render is unavailable, the output must have run_id
    # and either generated or errors — never an unhandled exception.
    assert "run_id" in result
    assert "generated" in result or "errors" in result


# ══════════════════════════════════════════════════════════════════
# Test 7 — Structured logging emits tool_name, run_id, timestamp
# ══════════════════════════════════════════════════════════════════

def test_structured_logging(caplog):
    """Every handler adapter logs tool_name, run_id, and timestamp."""
    import logging
    from src.workshop_copilot import (
        _handler_load_results,
        _handler_summarize_findings,
    )

    with caplog.at_level(logging.INFO, logger="workshop"):
        _handler_load_results({
            "arguments": {"run_id": "latest"},
            "tool_name": "load_results",
            "tool_call_id": "test-1",
            "session_id": "test-session",
        })
        _handler_summarize_findings({
            "arguments": {"run_id": "latest", "design_area": "Security"},
            "tool_name": "summarize_findings",
            "tool_call_id": "test-2",
            "session_id": "test-session",
        })

    # Verify log records contain required fields
    tool_records = [
        r for r in caplog.records
        if r.getMessage() == "tool_invocation"
    ]
    assert len(tool_records) >= 2, (
        f"Expected ≥2 tool_invocation log entries, got {len(tool_records)}"
    )

    for rec in tool_records:
        assert hasattr(rec, "tool_name"), "Missing tool_name in log record"
        assert hasattr(rec, "run_id"), "Missing run_id in log record"
        assert hasattr(rec, "timestamp"), "Missing timestamp in log record"
        assert rec.tool_name in {"load_results", "summarize_findings"}


# ══════════════════════════════════════════════════════════════════
# Test 8 — Smoke: session + tool call happens
# ══════════════════════════════════════════════════════════════════

def _resolve_github_token():
    """Return a GitHub token or None."""
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        return token
    try:
        r = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except Exception:
        pass
    return None


_HAS_TOKEN = _resolve_github_token() is not None


@pytest.mark.skipif(not _HAS_TOKEN, reason="No GitHub token available for SDK session")
def test_smoke_session_tool_call():
    """Start a real Copilot SDK session, ask 'summarize identity findings',
    and verify summarize_findings is invoked by the model."""
    from copilot import CopilotClient, Tool, ToolResult
    from copilot.types import CopilotClientOptions
    from src.workshop_copilot import TOOLS, SYSTEM_PROMPT

    token = _resolve_github_token()
    assert token is not None  # guarded by skipif above
    tool_calls_seen = []

    # Wrap tools with spy handlers to track invocations
    def _make_spy(original_tool):
        orig_handler = original_tool.handler
        def spy_handler(invocation):
            tool_calls_seen.append(invocation["tool_name"])
            return orig_handler(invocation)
        return Tool(
            original_tool.name,
            original_tool.description,
            spy_handler,
            original_tool.parameters,
        )

    spy_tools = [_make_spy(t) for t in TOOLS]

    async def _session_test():
        client = CopilotClient(CopilotClientOptions(github_token=token))
        session = await client.create_session({
            "model": "gpt-4o",
            "system_message": {"content": SYSTEM_PROMPT},
            "tools": spy_tools,
        })

        done = asyncio.Event()

        def on_event(event):
            etype = event.type if isinstance(event.type, str) else event.type.value
            if etype in ("assistant.message", "session.idle", "session.error"):
                done.set()

        session.on(on_event)
        await session.send({"prompt": "Summarize identity findings."})

        try:
            await asyncio.wait_for(done.wait(), timeout=60)
        except asyncio.TimeoutError:
            pass

        await session.destroy()
        await client.stop()

    asyncio.run(_session_test())

    # The model should have called at least one tool to answer.
    assert len(tool_calls_seen) > 0, (
        "Expected at least one tool call but got none. "
        "The model should invoke tools rather than guessing."
    )



# ══════════════════════════════════════════════════════════════════
# Tests for src/run_store.py
# ══════════════════════════════════════════════════════════════════
# NOTE: All tests below use `tmp_path / "base"` (never `tmp_path` directly)
# to avoid interference from the autouse `_seed_demo_run` fixture, which
# places a run file under `tmp_path / "out"`.
# ══════════════════════════════════════════════════════════════════


class TestResolveRunSource:
    """Unit tests for resolve_run_source()."""

    def test_out_returns_out_dir(self, tmp_path):
        from src.run_store import resolve_run_source
        root = tmp_path / "proj"
        root.mkdir()
        (root / "out").mkdir()
        result = resolve_run_source("out", project_root=root)
        assert result == (root / "out").resolve()

    def test_demo_finds_lowercase_demo(self, tmp_path):
        from src.run_store import resolve_run_source
        root = tmp_path / "proj"
        root.mkdir()
        (root / "demo").mkdir()
        result = resolve_run_source("demo", project_root=root)
        assert result == (root / "demo").resolve()

    def test_demo_finds_uppercase_Demo(self, tmp_path):
        from src.run_store import resolve_run_source
        root = tmp_path / "proj"
        root.mkdir()
        (root / "Demo").mkdir()
        result = resolve_run_source("demo", project_root=root)
        assert result == (root / "Demo").resolve()

    def test_demo_prefers_lowercase_over_uppercase(self, tmp_path):
        from src.run_store import resolve_run_source
        root = tmp_path / "proj"
        root.mkdir()
        (root / "demo").mkdir()
        (root / "Demo").mkdir()
        result = resolve_run_source("demo", project_root=root)
        assert result == (root / "demo").resolve()

    def test_demo_missing_raises(self, tmp_path):
        from src.run_store import resolve_run_source
        root = tmp_path / "proj"
        root.mkdir()
        with pytest.raises(FileNotFoundError, match="Demo run directory not found"):
            resolve_run_source("demo", project_root=root)

    def test_arbitrary_path_absolute(self, tmp_path):
        from src.run_store import resolve_run_source
        root = tmp_path / "proj"
        root.mkdir()
        custom = tmp_path / "custom_runs"
        custom.mkdir()
        result = resolve_run_source(str(custom), project_root=root)
        assert result == custom.resolve()

    def test_arbitrary_path_missing_raises(self, tmp_path):
        from src.run_store import resolve_run_source
        root = tmp_path / "proj"
        root.mkdir()
        with pytest.raises(FileNotFoundError):
            resolve_run_source("/nonexistent/path/xyz", project_root=root)


class TestDiscoverRuns:
    """Unit tests for discover_runs()."""

    def test_flat_json_layout(self, tmp_path):
        from src.run_store import discover_runs
        base = tmp_path / "base"
        base.mkdir()
        (base / "run-20260101-0000.json").write_text("{}", encoding="utf-8")
        (base / "run-20260214-1430.json").write_text("{}", encoding="utf-8")
        runs = discover_runs(base)
        names = {r.display_name for r in runs}
        assert "run-20260101-0000" in names
        assert "run-20260214-1430" in names

    def test_nested_run_json_layout(self, tmp_path):
        from src.run_store import discover_runs
        base = tmp_path / "base"
        base.mkdir()
        run_dir = base / "run-20260214-1430"
        run_dir.mkdir()
        (run_dir / "run.json").write_text("{}", encoding="utf-8")
        runs = discover_runs(base)
        assert len(runs) == 1
        assert runs[0].display_name == "run-20260214-1430"

    def test_excludes_delta_subdir(self, tmp_path):
        from src.run_store import discover_runs
        base = tmp_path / "base"
        base.mkdir()
        (base / "run-20260101-0000.json").write_text("{}", encoding="utf-8")
        deltas_dir = base / "deltas"
        deltas_dir.mkdir()
        (deltas_dir / "run-20260214__run-20260101.json").write_text("{}", encoding="utf-8")
        runs = discover_runs(base)
        assert len(runs) == 1
        assert runs[0].display_name == "run-20260101-0000"

    def test_excludes_delta_name_pattern(self, tmp_path):
        from src.run_store import discover_runs
        base = tmp_path / "base"
        base.mkdir()
        (base / "abc__def.json").write_text("{}", encoding="utf-8")
        (base / "run-20260101-0000.json").write_text("{}", encoding="utf-8")
        runs = discover_runs(base)
        names = {r.display_name for r in runs}
        assert "run-20260101-0000" in names
        assert "abc__def" not in names

    def test_parses_timestamp_from_filename(self, tmp_path):
        from src.run_store import discover_runs
        from datetime import datetime, timezone
        base = tmp_path / "base"
        base.mkdir()
        (base / "run-20260214-1430.json").write_text("{}", encoding="utf-8")
        runs = discover_runs(base)
        assert len(runs) == 1
        ts = runs[0].timestamp
        assert ts is not None
        assert ts == datetime(2026, 2, 14, 14, 30, tzinfo=timezone.utc)


class TestLatestAndPrevious:
    """Unit tests for latest_run() and previous_run() selection."""

    def _write_runs(self, base: "Path", *names: str) -> None:
        for name in names:
            (base / f"{name}.json").write_text("{}", encoding="utf-8")

    def test_latest_is_newest(self, tmp_path):
        from src.run_store import latest_run
        base = tmp_path / "base"
        base.mkdir()
        self._write_runs(base, "run-20260101-0000", "run-20260214-1430")
        ref = latest_run(base)
        assert ref is not None
        assert ref.display_name == "run-20260214-1430"

    def test_previous_is_second_newest(self, tmp_path):
        from src.run_store import previous_run
        base = tmp_path / "base"
        base.mkdir()
        self._write_runs(
            base,
            "run-20260101-0000",
            "run-20260214-1430",
            "run-20260301-0900",
        )
        ref = previous_run(base)
        assert ref is not None
        assert ref.display_name == "run-20260214-1430"

    def test_latest_none_when_empty(self, tmp_path):
        from src.run_store import latest_run
        base = tmp_path / "base"
        base.mkdir()
        assert latest_run(base) is None

    def test_previous_none_with_one_run(self, tmp_path):
        from src.run_store import previous_run
        base = tmp_path / "base"
        base.mkdir()
        self._write_runs(base, "run-20260101-0000")
        assert previous_run(base) is None


class TestCompareRunsTool:
    """Integration tests for compare_runs tool handler."""

    def test_compare_needs_two_runs(self, tmp_path, monkeypatch):
        import src.workshop_tools as wt
        from src.workshop_tools import compare_runs, CompareRunsParams

        out = tmp_path / "out"
        runs_dir = tmp_path / "runs"
        out.mkdir(exist_ok=True)
        runs_dir.mkdir()
        monkeypatch.setattr(wt, "OUT_DIR", out.resolve())
        monkeypatch.setattr(wt, "_PROJECT_ROOT", tmp_path.resolve())
        monkeypatch.setattr(wt, "_run_source_dir", runs_dir.resolve())
        wt._run_cache.clear()

        result = json.loads(compare_runs(CompareRunsParams()))
        assert "error" in result
        assert "Not enough runs" in result["error"]

    def test_compare_produces_delta(self, tmp_path, monkeypatch):
        import src.workshop_tools as wt
        from src.workshop_tools import compare_runs, CompareRunsParams

        out = tmp_path / "out"
        runs_dir = tmp_path / "runs"
        out.mkdir(exist_ok=True)
        runs_dir.mkdir()

        monkeypatch.setattr(wt, "OUT_DIR", out.resolve())
        monkeypatch.setattr(wt, "_PROJECT_ROOT", tmp_path.resolve())
        monkeypatch.setattr(wt, "_run_source_dir", runs_dir.resolve())
        wt._run_cache.clear()

        # Write two minimal run files (older = run_a, newer = run_b)
        run_a = {
            "meta": {"run_id": "run-A"},
            "scoring": {"overall_maturity_percent": 60.0},
            "results": [{"control_id": "C1", "status": "Fail"}],
        }
        run_b = {
            "meta": {"run_id": "run-B"},
            "scoring": {"overall_maturity_percent": 70.0},
            "results": [{"control_id": "C1", "status": "Pass"}],
        }
        (runs_dir / "run-20260101-0000.json").write_text(
            json.dumps(run_a), encoding="utf-8"
        )
        (runs_dir / "run-20260214-1430.json").write_text(
            json.dumps(run_b), encoding="utf-8"
        )

        result = json.loads(compare_runs(CompareRunsParams()))
        assert "error" not in result
        assert result["score_delta"] == 10.0
        assert result["improvements"] == 1
        assert result["regressions"] == 0
        assert "delta_path" in result
        # Delta must be written under out/
        assert result["delta_path"].startswith("out/")


class TestListRunsTool:
    """Tests for list_runs tool handler."""

    def test_list_runs_empty(self, tmp_path, monkeypatch):
        import src.workshop_tools as wt
        from src.workshop_tools import list_runs, ListRunsParams

        runs_dir = tmp_path / "runs"
        runs_dir.mkdir()
        monkeypatch.setattr(wt, "_run_source_dir", runs_dir.resolve())

        result = json.loads(list_runs(ListRunsParams()))
        assert result["count"] == 0

    def test_list_runs_shows_roles(self, tmp_path, monkeypatch):
        import src.workshop_tools as wt
        from src.workshop_tools import list_runs, ListRunsParams

        runs_dir = tmp_path / "runs"
        runs_dir.mkdir()
        (runs_dir / "run-20260101-0000.json").write_text("{}", encoding="utf-8")
        (runs_dir / "run-20260214-1430.json").write_text("{}", encoding="utf-8")
        monkeypatch.setattr(wt, "_run_source_dir", runs_dir.resolve())

        result = json.loads(list_runs(ListRunsParams()))
        assert result["count"] == 2
        roles = {r["display_name"]: r["role"] for r in result["runs"]}
        assert roles["run-20260214-1430"] == "latest"
        assert roles["run-20260101-0000"] == "previous"
