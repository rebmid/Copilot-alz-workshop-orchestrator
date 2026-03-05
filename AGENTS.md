# AGENTS.md — Copilot ALZ Workshop Orchestrator
#
# If guidance in this file conflicts with README.md, ARCHITECTURE.md,
# or inline code comments, follow this file.
#
# This file defines:
# - Allowed tools
# - Prohibited actions
# - Execution constraints
# - Output expectations
#
# This file describes how AI agents interact with this repository.
# It is consumed by GitHub Copilot, Copilot Extensions, and the
# GitHub Copilot SDK session bootstrapped by scan.py --workshop-copilot.

## Repository Purpose

Enterprise-grade Azure Landing Zone assessment orchestrator.
Runs deterministic governance scans against Azure environments,
scores maturity across ALZ design areas, and produces customer-facing
reports — all surfaced through a 6-tool Copilot SDK session.

## Agent Capabilities

The Copilot SDK session exposes **exactly 6 tools**, which are sometimes referred to as commands since they 
are invoked by a CLI. The Copilot agent may only invoke the following tools:

| Tool | Description |
|---|---|
| `run_scan` | Execute a deterministic ALZ assessment scan (subprocess-isolated) |
| `load_results` | Load a completed run into memory and return structured metadata |
| `summarize_findings` | Filter findings by design area, severity, or failure status |
| `generate_outputs` | Produce HTML report or Excel workbook from a loaded run |
| `list_runs` | List available assessment runs in the run store (newest first) |
| `compare_runs` | Compare latest run against previous run and produce a delta summary |

# The agent must never fabricate tool output or bypass these tools
## Guardrails

- **No data fabrication**: Every response must be grounded in loaded assessment data.
- **No environment mutation**: The agent cannot create, modify, or delete Azure resources.
- **File confinement**: All generated artefacts are written to `out/` — writes outside that directory are rejected at the code level.
- **Format allow-list**: Only `html` and `excel` output formats are accepted.
- **No scoring override**: Maturity scores are computed deterministically and cannot be altered by the agent.
- **No Inferring missing telemetry: The agent cannot create or modify values, every response must be grounded in loaded assessment data.
## Session Cache

After `run_scan` or `load_results`, the session remembers the active run ID.
Subsequent `summarize_findings`, `generate_outputs`, `list_runs`, and `compare_runs`
calls default to the active run when `run_id` is omitted.

## Entry Point

```
python scan.py --workshop-copilot          # live mode
python scan.py --workshop-copilot --demo   # demo mode (no Azure connection)
```

## Key Files

| Path | Role |
|---|---|
| `src/workshop_copilot.py` | SDK session bootstrap, tool registration, caching |
| `src/workshop_tools.py` | Handler functions, path guardrails, run cache |
| `scan.py` | Main CLI — `--workshop-copilot` flag enters workshop mode |
| `demo/demo_run.json` | 243-control demo fixture for offline testing |
| `tests/test_workshop.py` | Minimal test suite (4 tests) |
