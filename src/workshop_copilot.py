# workshop_copilot.py — Copilot SDK workshop session entry point
#
# Launched via:  python scan.py --workshop-copilot
#
# Registers exactly 4 tools with explicit JSON schemas.
# No wildcard tools. No freeform input. No dynamic execution.
# ──────────────────────────────────────────────────────────────────

import asyncio
import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone

from copilot import CopilotClient, Tool, ToolResult
from copilot.types import CopilotClientOptions

logger = logging.getLogger("workshop")

# ── Import the 4 handler functions from the tool layer ───────────
from src.workshop_tools import (
    run_scan      as _handle_run_scan,
    load_results  as _handle_load_results,
    summarize_findings as _handle_summarize_findings,
    generate_outputs   as _handle_generate_outputs,
    _load_cached,
)

# ══════════════════════════════════════════════════════════════════
# Session-level cache
# ──────────────────────────────────────────────────────────────────
# After run_scan or load_results, we remember the active run so that
# subsequent summarize / generate calls can omit run_id.
# ══════════════════════════════════════════════════════════════════

active_run_id:  str  | None = None
active_results: dict | None = None


# ══════════════════════════════════════════════════════════════════
# Handler adapters
# ──────────────────────────────────────────────────────────────────
# workshop_tools handlers are @define_tool-decorated (they expect a
# Pydantic params object).  The explicit Tool() constructor expects
# a raw ToolHandler(invocation) → ToolResult.  These thin adapters
# bridge the two: pull arguments from the invocation dict, build
# the Pydantic params, call the handler, and wrap the return value
# in a ToolResult.
# ══════════════════════════════════════════════════════════════════

from src.workshop_tools import (
    RunScanParams,
    LoadResultsParams,
    SummarizeFindingsParams,
    GenerateOutputsParams,
)


def _log_tool(tool_name: str, run_id: str | None, **extra) -> None:
    """Emit a structured log entry for every tool invocation."""
    logger.info(
        "tool_invocation",
        extra={
            "tool_name": tool_name,
            "run_id": run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **extra,
        },
    )


def _handler_run_scan(invocation) -> ToolResult:
    global active_run_id, active_results
    args = invocation.get("arguments", {})
    params = RunScanParams(
        scope=args.get("scope"),
        demo=args.get("demo", False),
        tag=args.get("tag"),
    )
    _log_tool("run_scan", None, demo=params.demo, scope=params.scope)
    result = _handle_run_scan(params)

    # ── Populate session cache ────────────────────────────────
    try:
        payload = json.loads(result)
        rid = payload.get("run_id")
        if rid:
            active_run_id = rid
            active_results = _load_cached(rid)
    except (json.JSONDecodeError, Exception):
        pass  # scan may have returned an error — leave cache unchanged

    return ToolResult(content=result)


def _handler_load_results(invocation) -> ToolResult:
    global active_run_id, active_results
    args = invocation.get("arguments", {})
    run_id = args.get("run_id", "latest")
    _log_tool("load_results", run_id)
    params = LoadResultsParams(run_id=run_id)
    result = _handle_load_results(params)

    # ── Populate session cache ────────────────────────────────
    try:
        payload = json.loads(result)
        rid = payload.get("run_id")
        if rid:
            active_run_id = rid
            active_results = _load_cached(rid)
    except (json.JSONDecodeError, Exception):
        pass

    return ToolResult(content=result)


def _handler_summarize_findings(invocation) -> ToolResult:
    args = invocation.get("arguments", {})
    run_id = args.get("run_id") or active_run_id or "latest"
    _log_tool("summarize_findings", run_id, design_area=args.get("design_area"))
    params = SummarizeFindingsParams(
        run_id=run_id,
        design_area=args.get("design_area"),
        severity=args.get("severity"),
        failed_only=args.get("failed_only", False),
        limit=args.get("limit", 25),
    )
    result = _handle_summarize_findings(params)
    return ToolResult(content=result)


def _handler_generate_outputs(invocation) -> ToolResult:
    args = invocation.get("arguments", {})
    run_id = args.get("run_id") or active_run_id or "latest"
    _log_tool("generate_outputs", run_id, formats=args.get("formats", ["html"]))
    params = GenerateOutputsParams(
        run_id=run_id,
        formats=args.get("formats", ["html"]),
    )
    result = _handle_generate_outputs(params)
    return ToolResult(content=result)


# ══════════════════════════════════════════════════════════════════
# Tool registration — explicit name, schema, handler.  Nothing else.
# ══════════════════════════════════════════════════════════════════

TOOLS = [
    # ── 1. run_scan ───────────────────────────────────────────
    Tool(
        name="run_scan",
        description="Run deterministic ALZ assessment scan",
        handler=_handler_run_scan,
        parameters={
            "type": "object",
            "properties": {
                "scope": {
                    "type": "string",
                    "description": "Management-group ID to scope the scan (--mg-scope). Omit for default Resource Graph discovery.",
                },
                "demo": {
                    "type": "boolean",
                    "description": "True → demo mode (no Azure connection).",
                },
                "tag": {
                    "type": "string",
                    "description": "Optional label for this run snapshot.",
                },
            },
            "required": [],
        },
    ),
    # ── 2. load_results ───────────────────────────────────────
    Tool(
        name="load_results",
        description="Load assessment run into memory and return structured metadata",
        handler=_handler_load_results,
        parameters={
            "type": "object",
            "properties": {
                "run_id": {
                    "type": "string",
                    "description": "Run ID to load (e.g. 'run-20260224-1430'). 'latest' → newest run in out/.",
                },
            },
            "required": [],
        },
    ),
    # ── 3. summarize_findings ─────────────────────────────────
    Tool(
        name="summarize_findings",
        description="Deterministic filtering of assessment findings by design area, severity, or failure status",
        handler=_handler_summarize_findings,
        parameters={
            "type": "object",
            "properties": {
                "run_id": {
                    "type": "string",
                    "description": "Run ID to summarise. 'latest' → newest run.",
                },
                "design_area": {
                    "type": "string",
                    "description": "Filter by ALZ design area (e.g. 'Security', 'Networking').",
                },
                "severity": {
                    "type": "string",
                    "description": "Filter by severity: Critical, High, Medium, Low.",
                },
                "failed_only": {
                    "type": "boolean",
                    "description": "If true, return only controls with status 'Fail'.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max items in top_items (default 25).",
                },
            },
            "required": [],
        },
    ),
    # ── 4. generate_outputs ───────────────────────────────────
    Tool(
        name="generate_outputs",
        description="Generate output artefacts (HTML report, Excel workbook) from a loaded assessment run. All outputs written to out/.",
        handler=_handler_generate_outputs,
        parameters={
            "type": "object",
            "properties": {
                "run_id": {
                    "type": "string",
                    "description": "Run ID whose data to render. 'latest' → newest run.",
                },
                "formats": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Output formats to generate. Allowed: ['html', 'excel'].",
                },
            },
            "required": [],
        },
    ),
]


# ══════════════════════════════════════════════════════════════════
# System prompt — scoped to exactly these 4 tools
# ══════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """\
Role: You are a CSA workshop facilitator for Azure Landing Zone assessments.
Behavior: Use tools to answer every question. Do not invent or fabricate results.
Scope: Only discuss items present in the loaded run results.
Safety: Do not suggest or perform environment changes. All outputs go to out/ only.

Tools (exactly 4):
  run_scan            — execute a deterministic ALZ scan
  load_results        — load a completed run into memory
  summarize_findings  — filter findings by design area, severity, or failure
  generate_outputs    — produce HTML or Excel artefacts from a loaded run

Constraints:
- Call the relevant tool before answering — never guess.
- Never fabricate control IDs, scores, or risk statements.
- Only generate outputs in allowed formats: html, excel.
- Present findings in concise, actionable language suitable for a customer-facing workshop.
"""


# ══════════════════════════════════════════════════════════════════
# Session bootstrap
# ══════════════════════════════════════════════════════════════════

async def _run(*, demo: bool = True):
    print("╔══════════════════════════════════════════════════╗")
    print("║   ALZ Workshop — Copilot SDK Session            ║")
    print("╠══════════════════════════════════════════════════╣")
    print("║  4 tools registered (run_scan, load_results,    ║")
    print("║  summarize_findings, generate_outputs)          ║")
    print("║  Type 'exit' or 'quit' to end the session.      ║")
    print("╚══════════════════════════════════════════════════╝")
    print()

    # Resolve GitHub token: env var → gh CLI fallback
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        # Try gh CLI — resolve full path on Windows to avoid PATH issues
        gh_cmd = "gh"
        if sys.platform == "win32":
            import shutil
            gh_path = shutil.which("gh")
            if gh_path:
                gh_cmd = gh_path
        try:
            proc = subprocess.run(
                [gh_cmd, "auth", "token"],
                capture_output=True, text=True, timeout=10,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                token = proc.stdout.strip()
        except FileNotFoundError:
            pass
        except Exception:
            pass
    if not token:
        print("[error] No GitHub token found.")
        print("        Fix: set GITHUB_TOKEN env var, or ensure 'gh auth login' is done")
        print("        and gh CLI is on your PATH.")
        return

    client = CopilotClient(CopilotClientOptions(github_token=token))

    session = await client.create_session({
        "model": "gpt-4o",
        "system_message": {"content": SYSTEM_PROMPT},
        "tools": TOOLS,
    })

    done = asyncio.Event()

    def on_event(event):
        etype = event.type if isinstance(event.type, str) else event.type.value
        if etype == "assistant.message":
            print(f"\n{event.data.content}\n")
            done.set()
        elif etype == "session.idle":
            done.set()
        elif etype == "session.error":
            print(f"\n[error] {getattr(event.data, 'message', event.data)}\n")
            done.set()

    session.on(on_event)

    # Initial greeting
    await session.send({
        "prompt": "Briefly introduce yourself and list the 4 tools you have available.",
    })
    await done.wait()
    done.clear()

    # Interactive loop
    while True:
        try:
            user = input("Workshop> ")
        except (EOFError, KeyboardInterrupt):
            break

        if user.strip().lower() in {"exit", "quit", ""}:
            if user.strip().lower() in {"exit", "quit"}:
                break
            continue

        done.clear()
        await session.send({"prompt": user})
        await done.wait()

    print("\nSession ended.")
    await session.destroy()
    await client.stop()


def run_workshop(*, demo: bool = True):
    """Sync entry point called from scan.py --workshop-copilot."""
    try:
        asyncio.run(_run(demo=demo))
    except KeyboardInterrupt:
        print("\nSession interrupted.")
        sys.exit(0)
