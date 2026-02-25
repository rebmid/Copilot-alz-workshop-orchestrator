# /src

Runtime source for the Copilot SDK workshop integration layer.

| File | Purpose |
|---|---|
| `workshop_copilot.py` | Copilot SDK session entry point — 4 explicit tools, session cache, REPL |
| `workshop_tools.py` | Handler functions, guardrails, run-data caching |

Both files are referenced from `scan.py --workshop-copilot`.
