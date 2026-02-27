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

# ── Import handler functions from the tool layer ─────────────────
from src.workshop_tools import (
    run_scan      as _handle_run_scan,
    load_results  as _handle_load_results,
    summarize_findings as _handle_summarize_findings,
    generate_outputs   as _handle_generate_outputs,
    list_runs     as _handle_list_runs,
    compare_runs  as _handle_compare_runs,
    _load_cached,
    set_run_source_dir as _set_run_source_dir,
)

# ══════════════════════════════════════════════════════════════════
# Session-level cache
# ──────────────────────────────────────────────────────────────────
# After run_scan or load_results, we remember the active run so that
# subsequent summarize / generate calls can omit run_id.
# ══════════════════════════════════════════════════════════════════

active_run_id:  str  | None = None
active_results: dict | None = None
_session_demo: bool = False  # Set True when --demo; forces run_scan to use demo fixture


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
    ListRunsParams,
    CompareRunsParams,
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
    print(f"  [tool] run_scan invoked — type={type(invocation).__name__}", flush=True)
    try:
        # Dump raw invocation for debug visibility
        try:
            print(f"  [tool] invocation keys: {list(invocation.keys())}", flush=True)
        except Exception:
            print(f"  [tool] invocation repr: {repr(invocation)[:200]}", flush=True)
        args = invocation.get("arguments", {})
        # The session-level flag is authoritative — ignore what the model passes
        params = RunScanParams(
            scope=args.get("scope"),
            demo=_session_demo,
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

        print(f"  [tool] run_scan completed", flush=True)
        return ToolResult(textResultForLlm=result)
    except Exception as exc:
        print(f"  [tool] run_scan ERROR: {exc}", flush=True)
        return ToolResult(textResultForLlm=json.dumps({"error": str(exc)}))


def _handler_load_results(invocation) -> ToolResult:
    global active_run_id, active_results
    print("  [tool] load_results invoked …", flush=True)
    try:
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

        print(f"  [tool] load_results completed", flush=True)
        return ToolResult(textResultForLlm=result)
    except Exception as exc:
        print(f"  [tool] load_results ERROR: {exc}", flush=True)
        return ToolResult(textResultForLlm=json.dumps({"error": str(exc)}))


def _handler_summarize_findings(invocation) -> ToolResult:
    print("  [tool] summarize_findings invoked …", flush=True)
    try:
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
        print(f"  [tool] summarize_findings completed", flush=True)
        return ToolResult(textResultForLlm=result)
    except Exception as exc:
        print(f"  [tool] summarize_findings ERROR: {exc}", flush=True)
        return ToolResult(textResultForLlm=json.dumps({"error": str(exc)}))


def _handler_generate_outputs(invocation) -> ToolResult:
    print("  [tool] generate_outputs invoked …", flush=True)
    try:
        args = invocation.get("arguments", {})
        run_id = args.get("run_id") or active_run_id or "latest"
        _log_tool("generate_outputs", run_id, formats=args.get("formats", ["html"]))
        params = GenerateOutputsParams(
            run_id=run_id,
            formats=args.get("formats", ["html"]),
        )
        result = _handle_generate_outputs(params)
        print(f"  [tool] generate_outputs completed", flush=True)
        return ToolResult(textResultForLlm=result)
    except Exception as exc:
        print(f"  [tool] generate_outputs ERROR: {exc}", flush=True)
        return ToolResult(textResultForLlm=json.dumps({"error": str(exc)}))


def _handler_list_runs(invocation) -> ToolResult:
    print("  [tool] list_runs invoked …", flush=True)
    try:
        _log_tool("list_runs", None)
        result = _handle_list_runs(ListRunsParams())
        print(f"  [tool] list_runs completed", flush=True)
        return ToolResult(textResultForLlm=result)
    except Exception as exc:
        print(f"  [tool] list_runs ERROR: {exc}", flush=True)
        return ToolResult(textResultForLlm=json.dumps({"error": str(exc)}))


def _handler_compare_runs(invocation) -> ToolResult:
    print("  [tool] compare_runs invoked …", flush=True)
    try:
        _log_tool("compare_runs", None)
        result = _handle_compare_runs(CompareRunsParams())
        print(f"  [tool] compare_runs completed", flush=True)
        return ToolResult(textResultForLlm=result)
    except Exception as exc:
        print(f"  [tool] compare_runs ERROR: {exc}", flush=True)
        return ToolResult(textResultForLlm=json.dumps({"error": str(exc)}))


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
    # ── 5. list_runs ──────────────────────────────────────────
    Tool(
        name="list_runs",
        description=(
            "List discovered assessment runs in the active run source "
            "(newest first). Shows display name, timestamp, and role "
            "(latest/previous). Use before compare_runs to confirm ≥2 runs exist."
        ),
        handler=_handler_list_runs,
        parameters={
            "type": "object",
            "properties": {},
            "required": [],
        },
    ),
    # ── 6. compare_runs ───────────────────────────────────────
    Tool(
        name="compare_runs",
        description=(
            "Compare the latest run against the previous run (delta analysis). "
            "Reports score change and controls that changed status. "
            "Delta output is written to out/deltas/. "
            "Requires ≥2 runs in the active run source."
        ),
        handler=_handler_compare_runs,
        parameters={
            "type": "object",
            "properties": {},
            "required": [],
        },
    ),
]


# ══════════════════════════════════════════════════════════════════
# System prompt — scoped to the registered tools
# ══════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """\
Role: You are a CSA workshop facilitator for Azure Landing Zone assessments.
Behavior: Use tools to answer every question. Do not invent or fabricate results.
Scope: Only discuss items present in the loaded run results.
Safety: Do not suggest or perform environment changes. All outputs go to out/ only.
{demo_note}
Tools:
  run_scan            — execute a deterministic ALZ scan
  load_results        — load a completed run into memory
  summarize_findings  — filter findings by design area, severity, or failure
  generate_outputs    — produce HTML or Excel artefacts from a loaded run
  list_runs           — list discovered runs in the run source (newest first)
  compare_runs        — compare latest vs previous run and write a delta report

Constraints:
- Call the relevant tool before answering — never guess.
- Never fabricate control IDs, scores, or risk statements.
- Only generate outputs in allowed formats: html, excel.
- Present findings in concise, actionable language suitable for a customer-facing workshop.
"""


# ══════════════════════════════════════════════════════════════════
# Session bootstrap
# ══════════════════════════════════════════════════════════════════

async def _run(*, demo: bool = True, run_source_dir=None):
    print("╔══════════════════════════════════════════════════╗")
    print("║   ALZ Workshop — Copilot SDK Session            ║")
    print("╠══════════════════════════════════════════════════╣")
    print("║  6 tools registered (run_scan, load_results,    ║")
    print("║  summarize_findings, generate_outputs,          ║")
    print("║  list_runs, compare_runs)                       ║")
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

    _debug = os.environ.get("WORKSHOP_DEBUG", "").lower() in ("1", "true", "yes")

    # Propagate demo flag so tool handlers use the demo fixture
    global _session_demo
    _session_demo = demo

    # Configure run source dir for tool handlers
    if run_source_dir is not None:
        _set_run_source_dir(run_source_dir)
        print(f"  [session] run source: {run_source_dir}", flush=True)

    # Build system prompt with demo-mode note if applicable
    demo_note = (
        "\nMode: DEMO — using sample data, no Azure connection. "
        "Always pass demo=true when calling run_scan."
        if demo
        else "\nMode: LIVE — running against the authenticated Azure subscription. "
             "Always pass demo=false when calling run_scan."
    )
    system_prompt = SYSTEM_PROMPT.format(demo_note=demo_note)

    client = CopilotClient(CopilotClientOptions(github_token=token))

    session = await client.create_session({
        "model": "gpt-4o",
        "system_message": {"content": system_prompt},
        "tools": TOOLS,
    })

    # ── Optional debug observer — logs every event without affecting flow ──
    if _debug:
        def _debug_observer(event):
            etype = event.type if isinstance(event.type, str) else event.type.value
            data_preview = ""
            try:
                d = getattr(event, "data", None)
                if d is not None:
                    c = getattr(d, "content", None)
                    m = getattr(d, "message", None)
                    if c:
                        data_preview = f" content={str(c)[:120]!r}"
                    elif m:
                        data_preview = f" message={str(m)[:120]!r}"
            except Exception:
                pass
            print(f"  [debug] event: {etype}{data_preview}", flush=True)
        session.on(_debug_observer)

    # ── Helper: send prompt and print response ──
    async def _send_and_print(prompt: str, timeout: float = 660.0):
        """Use the SDK's send_and_wait which correctly handles the
        session.idle / assistant.message lifecycle."""
        try:
            response = await session.send_and_wait(
                {"prompt": prompt}, timeout=timeout,
            )
            if response:
                content = getattr(response.data, "content", None)
                if content:
                    print(f"\n{content}\n", flush=True)
                else:
                    if _debug:
                        print("  [debug] response received but no content", flush=True)
            else:
                if _debug:
                    print("  [debug] send_and_wait returned None (no assistant message)", flush=True)
        except asyncio.TimeoutError:
            print("\n[timeout] The request took too long. Try again.\n", flush=True)
        except Exception as exc:
            print(f"\n[error] {exc}\n", flush=True)

    # Initial greeting
    await _send_and_print(
        "Briefly introduce yourself and list the tools you have available."
    )

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

        await _send_and_print(user)

    print("\nSession ended.")
    await session.destroy()
    await client.stop()


def run_workshop(*, demo: bool = True, run_source: str = "out"):
    """Sync entry point called from scan.py --workshop-copilot."""
    from src.run_store import resolve_run_source

    # Resolve run source to an absolute path
    try:
        run_source_dir = resolve_run_source(run_source)
    except FileNotFoundError as exc:
        print(f"[error] {exc}")
        sys.exit(1)

    try:
        asyncio.run(_run(demo=demo, run_source_dir=run_source_dir))
    except KeyboardInterrupt:
        print("\nSession interrupted.")
        sys.exit(0)
