"""Run loader — loads assessment runs from disk.

Provides two entry points:
  - load_latest_run()  → most recent real run from out/
  - load_demo_run()    → sanitised demo fixture from demo/
"""
from __future__ import annotations

import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_OUT  = _ROOT / "out"
_DEMO = _ROOT / "demo" / "demo_run.json"


def load_latest_run() -> dict:
    """Return the most recent run-*.json from out/."""
    runs = sorted(_OUT.glob("run-*.json"), reverse=True)
    if not runs:
        raise RuntimeError("No run files found in out/. Run a full scan first (python scan.py).")
    print(f"  Using: {runs[0]}")
    return json.loads(runs[0].read_text(encoding="utf-8"))


def load_demo_run() -> dict:
    """Return the bundled demo fixture (no Azure connection required)."""
    if not _DEMO.exists():
        raise RuntimeError("demo/demo_run.json not found. Run a full scan first, then generate the fixture.")
    return json.loads(_DEMO.read_text(encoding="utf-8"))


def load_run(*, demo: bool = False) -> dict:
    """Convenience wrapper — dispatches to demo or latest."""
    return load_demo_run() if demo else load_latest_run()
