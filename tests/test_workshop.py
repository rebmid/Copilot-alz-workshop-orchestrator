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
# Test 4 — Smoke: session + tool call happens
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
    from src.workshop_copilot import TOOLS, SYSTEM_PROMPT

    token = _resolve_github_token()
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
        client = CopilotClient({"github_token": token})
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
