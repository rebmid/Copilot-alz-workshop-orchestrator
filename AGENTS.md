# AGENTS.md — Copilot ALZ Workshop Orchestrator
#
# This file describes how AI agents interact with this repository.
# It is consumed by GitHub Copilot, Copilot Extensions, and the
# GitHub Copilot SDK session bootstrapped by scan.py --workshop-copilot.

## Repository Purpose

Enterprise-grade Azure Landing Zone assessment orchestrator.
Runs deterministic governance scans against Azure environments,
scores maturity across ALZ design areas, and produces customer-facing
reports — all surfaced through a 4-tool Copilot SDK session.

## Agent Capabilities

The Copilot SDK session exposes **exactly 4 tools**:

| Tool | Description |
|---|---|
| `run_scan` | Execute a deterministic ALZ assessment scan (subprocess-isolated) |
| `load_results` | Load a completed run into memory and return structured metadata |
| `summarize_findings` | Filter findings by design area, severity, or failure status |
| `generate_outputs` | Produce HTML report or Excel workbook from a loaded run |

## Guardrails

- **No data fabrication**: Every response must be grounded in loaded assessment data.
- **No environment mutation**: The agent cannot create, modify, or delete Azure resources.
- **File confinement**: All generated artefacts are written to `out/` — writes outside that directory are rejected at the code level.
- **Format allow-list**: Only `html` and `excel` output formats are accepted.
- **No scoring override**: Maturity scores are computed deterministically and cannot be altered by the agent.

## Session Cache

After `run_scan` or `load_results`, the session remembers the active run ID.
Subsequent `summarize_findings` and `generate_outputs` calls default to the
active run when `run_id` is omitted.

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
