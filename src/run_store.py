# run_store.py — Deterministic run discovery and selection
#
# Provides run source resolution, discovery (flat JSON and structured
# run.json layouts), sorting (newest first), and loading.
#
# Used by workshop mode to support --run-source (demo/out/path) and
# deterministic "latest vs previous" delta comparisons.
# ──────────────────────────────────────────────────────────────────

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ══════════════════════════════════════════════════════════════════
# Timestamp parsing
# ══════════════════════════════════════════════════════════════════

# ISO-like timestamp patterns found in run filenames / directory names.
# Ordered most-specific → least-specific.
_TS_PATTERNS = [
    # 20260214-1430  or  20260214_1430
    re.compile(r"(\d{4})(\d{2})(\d{2})[_-](\d{2})(\d{2})"),
    # 2026-02-14T14:30
    re.compile(r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})"),
    # 2026-02-14
    re.compile(r"(\d{4})-(\d{2})-(\d{2})"),
]

# Delta output files look like  <id>__<id>.json — skip them.
_DELTA_NAME_RE = re.compile(r".+__.+\.json$")


def _parse_timestamp(name: str) -> Optional[datetime]:
    """Try to extract a UTC datetime from a filename or directory name."""
    for pat in _TS_PATTERNS:
        m = pat.search(name)
        if not m:
            continue
        groups = m.groups()
        try:
            if len(groups) == 5:
                y, mo, d, h, mi = (int(g) for g in groups)
                return datetime(y, mo, d, h, mi, tzinfo=timezone.utc)
            if len(groups) == 3:
                y, mo, d = (int(g) for g in groups)
                return datetime(y, mo, d, tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


# ══════════════════════════════════════════════════════════════════
# RunRef
# ══════════════════════════════════════════════════════════════════

@dataclass
class RunRef:
    """Reference to a single discovered run file."""
    path: Path
    display_name: str
    timestamp: Optional[datetime] = None


def _sort_key(run: RunRef):
    """Comparable sort key: (timestamp, mtime, display_name) — all ascending."""
    ts = run.timestamp or datetime.min.replace(tzinfo=timezone.utc)
    try:
        mtime = datetime.fromtimestamp(run.path.stat().st_mtime, tz=timezone.utc)
    except OSError:
        mtime = datetime.min.replace(tzinfo=timezone.utc)
    return (ts, mtime, run.display_name)


# ══════════════════════════════════════════════════════════════════
# Source resolution
# ══════════════════════════════════════════════════════════════════

def resolve_run_source(
    run_source: str,
    project_root: Optional[Path] = None,
) -> Path:
    """Resolve a run-source specifier to an absolute directory path.

    Args:
        run_source: ``"out"`` (default), ``"demo"``, or a filesystem path.
        project_root: Overridable project root for testing. Defaults to the
            parent of the ``src/`` package directory.

    Returns:
        Resolved, absolute ``Path`` to the run source directory.

    Raises:
        FileNotFoundError: When the directory cannot be located.
    """
    if project_root is None:
        project_root = Path(__file__).resolve().parent.parent

    if run_source == "out":
        return (project_root / "out").resolve()

    if run_source == "demo":
        for name in ("demo", "Demo"):
            candidate = project_root / name
            if candidate.is_dir():
                return candidate.resolve()
        raise FileNotFoundError(
            "Demo run directory not found. "
            "Expected 'demo/' or 'Demo/' under the project root. "
            "Use --run-source <path> to specify an alternative directory."
        )

    # Arbitrary path — absolute or relative to project root.
    p = Path(run_source)
    if not p.is_absolute():
        p = (project_root / p).resolve()
    else:
        p = p.resolve()
    if not p.is_dir():
        raise FileNotFoundError(f"Run source directory not found: {p}")
    return p


# ══════════════════════════════════════════════════════════════════
# Run discovery
# ══════════════════════════════════════════════════════════════════

def discover_runs(base_dir: Path) -> list[RunRef]:
    """Discover run files under *base_dir*.

    Supports two layouts:

    * **Flat JSON** — ``BASE/*.json`` and ``BASE/*/*.json``
    * **Structured** — ``BASE/**/run.json``

    Delta output files (matching ``<id>__<id>.json``) are excluded.
    Files under a ``deltas/`` subdirectory are also excluded.
    """
    runs: list[RunRef] = []
    seen: set[Path] = set()

    def _is_delta(path: Path) -> bool:
        return "deltas" in path.parts or bool(_DELTA_NAME_RE.match(path.name))

    def _add(path: Path, display: str, ts: Optional[datetime]) -> None:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            runs.append(RunRef(path=resolved, display_name=display, timestamp=ts))

    # ── Structured layout: **/run.json ────────────────────────────
    for path in base_dir.rglob("run.json"):
        if _is_delta(path):
            continue
        ts = _parse_timestamp(path.parent.name) or _parse_timestamp(path.name)
        display = path.parent.name if path.parent != base_dir else path.stem
        _add(path, display, ts)

    # ── Flat layout: BASE/*.json ──────────────────────────────────
    for path in base_dir.glob("*.json"):
        if _is_delta(path):
            continue
        name = path.stem
        ts = _parse_timestamp(name)
        _add(path, name, ts)

    # ── Flat layout one level deep: BASE/*/*.json ─────────────────
    for path in base_dir.glob("*/*.json"):
        if _is_delta(path):
            continue
        if path.name == "run.json":
            continue  # already handled above
        name = path.stem
        ts = _parse_timestamp(name) or _parse_timestamp(path.parent.name)
        _add(path, name, ts)

    return runs


def sort_runs(runs: list[RunRef]) -> list[RunRef]:
    """Return *runs* sorted newest-first."""
    return sorted(runs, key=_sort_key, reverse=True)


# ══════════════════════════════════════════════════════════════════
# Convenience selectors
# ══════════════════════════════════════════════════════════════════

def latest_run(base_dir: Path) -> Optional[RunRef]:
    """Return the newest run in *base_dir*, or ``None`` if none found."""
    sorted_runs = sort_runs(discover_runs(base_dir))
    return sorted_runs[0] if sorted_runs else None


def previous_run(base_dir: Path) -> Optional[RunRef]:
    """Return the second-newest run in *base_dir*, or ``None`` if < 2 exist."""
    sorted_runs = sort_runs(discover_runs(base_dir))
    return sorted_runs[1] if len(sorted_runs) >= 2 else None


def load_run(run_ref: RunRef) -> dict:
    """Load and parse the JSON file referenced by *run_ref*."""
    return json.loads(run_ref.path.read_text(encoding="utf-8"))
