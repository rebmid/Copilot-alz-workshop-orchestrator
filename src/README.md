# /src

Runtime source for the Copilot SDK workshop integration layer.

| File | Purpose |
|---|---|
| `workshop_copilot.py` | Copilot SDK session entry point — 6 tools, session cache, REPL |
| `workshop_tools.py` | Handler functions, guardrails, run-data caching |
| `run_store.py` | Run source resolution, discovery, and delta comparison |

Both files are referenced from `scan.py --workshop-copilot`.

### Registered Tools

| Tool | Description |
|---|---|
| `run_scan` | Execute a deterministic ALZ assessment scan |
| `load_results` | Load a completed run into memory and return structured metadata |
| `summarize_findings` | Filter findings by design area, severity, or failure status |
| `generate_outputs` | Produce HTML report or Excel workbook from a loaded run |
| `list_runs` | List discovered runs in the active run source (newest first) |
| `compare_runs` | Compare latest vs previous run and write a delta report |
