# Documentation

## Workshop Deliverables Checklist

| # | Deliverable | Status |
|---|---|---|
| 1 | Assessment scan completed | `run_scan` tool |
| 2 | Run data loaded and validated | `load_results` tool |
| 3 | Findings summarised by design area | `summarize_findings` tool |
| 4 | HTML readiness report generated | `generate_outputs(formats=["html"])` |
| 5 | Excel CSA workbook generated | `generate_outputs(formats=["excel"])` |
| 6 | All artefacts confined to `out/` | Enforced by `ensure_out_path()` |

## Architecture

See [ARCHITECTURE.md](../ARCHITECTURE.md) for the system-level diagram.

## Getting Started

```bash
# Install dependencies
pip install -r requirements.txt

# Run workshop in demo mode
python scan.py --workshop-copilot --demo

# Run workshop against live Azure environment
python scan.py --workshop-copilot
```

## Test Suite

```bash
python -m pytest tests/test_workshop.py -v
```
