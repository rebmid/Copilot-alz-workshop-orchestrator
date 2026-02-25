# workshop_copilot.py — Copilot SDK workshop session entry point
#
# Launched via:  python scan.py --workshop-copilot
#
# Exposes deterministic ALZ assessment data to a Copilot-hosted LLM
# through a small set of tool handlers (read-only, no env changes).
# ──────────────────────────────────────────────────────────────────

import asyncio
import json
import sys

from pydantic import BaseModel, Field
from copilot import CopilotClient, define_tool

# ── operational tool layer (run_scan, load_results, etc.) ────────
from workshop_tools import ALL_TOOLS as OPERATIONAL_TOOLS

# ── lazy-loaded run cache ────────────────────────────────────────
_run_cache: dict | None = None


def _get_run(*, demo: bool = True) -> dict:
    """Return the cached run dict, loading on first call."""
    global _run_cache
    if _run_cache is None:
        from agent.run_loader import load_run
        _run_cache = load_run(demo=demo)
    return _run_cache


# ──────────────────────────────────────────────────────────────────
# Tool 1 — load_assessment
# ──────────────────────────────────────────────────────────────────

class LoadAssessmentParams(BaseModel):
    demo: bool = Field(
        default=True,
        description="True → load bundled demo fixture; False → load latest out/ run",
    )

@define_tool(description="Load an ALZ assessment run and return its top-level summary (meta, scoring, execution context).")
def load_assessment(params: LoadAssessmentParams) -> str:
    run = _get_run(demo=params.demo)
    summary = {
        "meta": run.get("meta"),
        "execution_context": run.get("execution_context"),
        "scoring": {
            k: run["scoring"][k]
            for k in ("overall_maturity_percent", "automation_coverage",
                      "top_failing_sections", "section_scores")
            if k in run.get("scoring", {})
        },
        "total_controls": len(run.get("results", [])),
        "has_ai": bool(run.get("ai")),
        "has_delta": bool(run.get("delta")),
    }
    return json.dumps(summary, indent=2, default=str)


# ──────────────────────────────────────────────────────────────────
# Tool 2 — get_executive_summary
# ──────────────────────────────────────────────────────────────────

class ExecSummaryParams(BaseModel):
    pass  # no params needed

@define_tool(description="Return the executive summary including top business risks, maturity narrative, and engagement framing from the loaded assessment.")
def get_executive_summary(params: ExecSummaryParams) -> str:
    run = _get_run()
    es = run.get("executive_summary", {})
    return json.dumps(es, indent=2, default=str)


# ──────────────────────────────────────────────────────────────────
# Tool 3 — list_controls
# ──────────────────────────────────────────────────────────────────

class ListControlsParams(BaseModel):
    domain: str | None = Field(
        default=None,
        description="Filter by ALZ domain/section (e.g. 'Security', 'Networking'). None → all.",
    )
    status: str | None = Field(
        default=None,
        description="Filter by status: Pass, Fail, Partial, Manual. None → all.",
    )
    severity: str | None = Field(
        default=None,
        description="Filter by severity: Critical, High, Medium, Low. None → all.",
    )
    limit: int = Field(
        default=50,
        description="Max controls to return (default 50).",
    )

@define_tool(description="List ALZ checklist controls from the loaded assessment, optionally filtered by domain, status, or severity.")
def list_controls(params: ListControlsParams) -> str:
    run = _get_run()
    controls = run.get("results", [])

    if params.domain:
        controls = [c for c in controls if c.get("section", "").lower() == params.domain.lower()]
    if params.status:
        controls = [c for c in controls if c.get("status", "").lower() == params.status.lower()]
    if params.severity:
        controls = [c for c in controls if c.get("severity", "").lower() == params.severity.lower()]

    # trim to limit and project useful fields
    trimmed = []
    for c in controls[: params.limit]:
        trimmed.append({
            "control_id": c.get("control_id"),
            "section": c.get("section"),
            "severity": c.get("severity"),
            "status": c.get("status"),
            "text": c.get("text"),
            "notes": c.get("notes"),
        })

    return json.dumps({"count": len(controls), "controls": trimmed}, indent=2, default=str)


# ──────────────────────────────────────────────────────────────────
# Tool 4 — get_scoring_summary
# ──────────────────────────────────────────────────────────────────

class ScoringSummaryParams(BaseModel):
    pass

@define_tool(description="Return the full scoring breakdown: overall maturity %, section scores, top failing sections, and automation coverage.")
def get_scoring_summary(params: ScoringSummaryParams) -> str:
    run = _get_run()
    return json.dumps(run.get("scoring", {}), indent=2, default=str)


# ──────────────────────────────────────────────────────────────────
# Tool 5 — why_domain_risk
# ──────────────────────────────────────────────────────────────────

class WhyDomainRiskParams(BaseModel):
    domain: str = Field(
        description="The ALZ domain to explain (e.g. 'Security', 'Networking', 'Identity').",
    )

@define_tool(description="Run why-risk causal reasoning for a specific domain: root cause, failing controls, dependency impact, and roadmap actions.")
def why_domain_risk(params: WhyDomainRiskParams) -> str:
    from agent.why_reasoning import build_why_payload
    run = _get_run()
    try:
        payload = build_why_payload(run, params.domain, verbose=False)
        return json.dumps(payload, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ──────────────────────────────────────────────────────────────────
# Tool 6 — get_roadmap
# ──────────────────────────────────────────────────────────────────

class RoadmapParams(BaseModel):
    phase: str | None = Field(
        default=None,
        description="Filter by phase: '30', '60', or '90'. None → all phases.",
    )

@define_tool(description="Return the 30-60-90 transformation roadmap initiatives from the loaded assessment.")
def get_roadmap(params: RoadmapParams) -> str:
    run = _get_run()
    roadmap = run.get("transformation_roadmap") or run.get("transformation_plan") or {}
    initiatives = roadmap.get("initiatives", [])
    if params.phase:
        initiatives = [i for i in initiatives if str(i.get("phase", "")) == params.phase]
    return json.dumps({"total": len(initiatives), "initiatives": initiatives}, indent=2, default=str)


# ══════════════════════════════════════════════════════════════════
# Session bootstrap
# ══════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """\
You are a **CSA workshop facilitator** for Azure Landing Zone governance assessments.

You have access to tools that query a deterministic ALZ assessment run.
Always call the relevant tool before answering — never guess or invent data.
Present findings in concise, actionable language suitable for a customer-facing workshop.

Rules
─────
1. Use tools to retrieve data before responding.
2. Never fabricate control IDs, scores, or risk statements.
3. Only discuss items present in the loaded assessment run.
4. Do not suggest or perform environment changes.
5. When asked about risks, always cite the affected controls and their status.
6. When presenting a roadmap, include phase, initiative name, and linked checklist IDs.
7. All file outputs must stay under out/. Never write outside that directory.
8. Only generate outputs in allowed formats (html, excel).
"""


# Analytical tools (read cached run data)
_ANALYTICAL_TOOLS = [
    load_assessment,
    get_executive_summary,
    list_controls,
    get_scoring_summary,
    why_domain_risk,
    get_roadmap,
]

# Full tool surface: analytical + operational
ALL_TOOLS = _ANALYTICAL_TOOLS + list(OPERATIONAL_TOOLS)


async def _run(*, demo: bool = True):
    print("╔══════════════════════════════════════════════════╗")
    print("║   ALZ Workshop — Copilot SDK Session            ║")
    print("╠══════════════════════════════════════════════════╣")
    print("║  Type questions about the assessment.           ║")
    print("║  Type 'exit' or 'quit' to end the session.      ║")
    print("╚══════════════════════════════════════════════════╝")
    print()

    # Pre-load the run so tools respond instantly
    print("  Loading assessment data …", end=" ", flush=True)
    _get_run(demo=demo)
    print("done.\n")

    client = CopilotClient()

    session = await client.create_session({
        "model": "gpt-4o",
        "system_message": {"content": SYSTEM_PROMPT},
        "tools": ALL_TOOLS,
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
        "prompt": "Briefly introduce yourself and list the tools you have available for this workshop session.",
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
