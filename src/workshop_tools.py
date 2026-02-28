# workshop_tools.py — Enterprise tool layer for Copilot SDK workshop
#
# THE most important file in the Copilot integration.
#
# 4 tools. No extras. No AI mutation. No Azure mutation.
# Every tool executes deterministic logic and returns structured evidence.
#
# Guardrails enforced at the code level:
#   - All file writes confined to out/
#   - Format allow-list for output generation
#   - Lazy-loaded, memory-cached run data
#   - No scoring modification
# ──────────────────────────────────────────────────────────────────

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

# ══════════════════════════════════════════════════════════════════
# Path guardrails
# ══════════════════════════════════════════════════════════════════

_PROJECT_ROOT = Path(__file__).resolve().parent.parent  # src/ → project root
OUT_DIR = (_PROJECT_ROOT / "out").resolve()
DEMO_DIR = (_PROJECT_ROOT / "demo").resolve()


def ensure_out_path(path: str | Path) -> Path:
    """Validate that *path* resolves inside out/.  Raise on violation."""
    resolved = Path(path).resolve()
    if not str(resolved).startswith(str(OUT_DIR)):
        raise ValueError(
            f"Write outside out/ directory not allowed: {resolved}"
        )
    return resolved


# ══════════════════════════════════════════════════════════════════
# Run source directory (set by workshop session for run discovery)
# ══════════════════════════════════════════════════════════════════

_run_source_dir: Path | None = None  # None → use OUT_DIR (default)


def set_run_source_dir(path: Path | None) -> None:
    """Configure the directory used for run discovery in this session."""
    global _run_source_dir
    _run_source_dir = path


# Pattern for sanitising run IDs into safe filename components.
_UNSAFE_ID_CHARS = re.compile(r"[^\w\-]")


# ══════════════════════════════════════════════════════════════════
# Background scan tracking (live mode only)
# ══════════════════════════════════════════════════════════════════

_active_scan: dict[str, Any] | None = None  # {process, started, before_files, stderr_path}
_active_scan_lock = threading.Lock()


def _collect_scan_result(
    process: subprocess.Popen,
    before: set[Path],
    stderr_path: str | None = None,
) -> str:
    """Harvest results from a completed background scan process.

    stdout is inherited (printed live to the console) so the user
    sees real-time scan progress.  Only stderr is captured to a temp
    file for error diagnostics if the scan fails.
    """
    stderr_text = ""
    try:
        if stderr_path and os.path.exists(stderr_path):
            stderr_text = Path(stderr_path).read_text(encoding="utf-8", errors="replace")
    finally:
        if stderr_path:
            try:
                os.unlink(stderr_path)
            except OSError:
                pass

    if process.returncode != 0:
        stderr_tail = stderr_text.strip().splitlines()[-5:]
        return json.dumps({
            "status": "failed",
            "error": "Scan failed",
            "exit_code": process.returncode,
            "detail": "\n".join(stderr_tail),
        })

    # Discover new run files produced by the scan
    after = set(OUT_DIR.glob("run-*.json"))
    new_files = sorted(after - before)

    if not new_files:
        return json.dumps({
            "status": "failed",
            "error": "Scan completed but no new run file was created.",
        })

    run_path = new_files[-1]
    run_id = run_path.stem

    # Collect all output artefacts for this run
    output_paths = [str(run_path.relative_to(_PROJECT_ROOT))]
    for f in OUT_DIR.iterdir():
        if f.name.startswith(run_id) and f != run_path:
            output_paths.append(str(f.relative_to(_PROJECT_ROOT)))
    for f in OUT_DIR.glob(f"ALZ-Platform-Readiness-Report-{run_id}*.html"):
        rel = str(f.relative_to(_PROJECT_ROOT))
        if rel not in output_paths:
            output_paths.append(rel)

    return json.dumps({
        "status": "completed",
        "run_id": run_id,
        "output_paths": output_paths,
    }, indent=2)


# ══════════════════════════════════════════════════════════════════
# Run cache (lazy load, keep in memory for the session)
# ══════════════════════════════════════════════════════════════════

_run_cache: dict[str, dict] = {}  # keyed by run_id or "latest"


def _resolve_run_path(run_id: str) -> Path:
    """Map a run_id to its JSON file.

    Special value ``"latest"`` → newest run in the active run source dir
    (``_run_source_dir`` when set, otherwise ``OUT_DIR``).
    Otherwise looks in out/ first, then falls back to demo/.
    """
    if run_id == "latest":
        from src.run_store import latest_run
        source = _run_source_dir if _run_source_dir is not None else OUT_DIR
        ref = latest_run(source)
        if ref is None:
            source_label = str(source)
            raise RuntimeError(
                f"No run files found in {source_label}. "
                "Run a scan first or use --run-source to point at a directory "
                "with existing runs."
            )
        return ref.path
    candidate = OUT_DIR / f"{run_id}.json"
    if candidate.exists():
        return ensure_out_path(candidate)
    # Fallback: check demo/ for pre-built fixtures
    demo_candidate = DEMO_DIR / f"{run_id}.json"
    if demo_candidate.exists():
        return demo_candidate
    raise FileNotFoundError(f"Run file not found: {candidate}")


def _load_cached(run_id: str) -> dict:
    """Return a cached run dict, loading from disk on first access."""
    if run_id not in _run_cache:
        path = _resolve_run_path(run_id)
        _run_cache[run_id] = json.loads(path.read_text(encoding="utf-8"))
        # Also cache by the canonical run_id from metadata
        canonical = _run_cache[run_id].get("meta", {}).get("run_id")
        if canonical and canonical != run_id:
            _run_cache[canonical] = _run_cache[run_id]
    return _run_cache[run_id]


# ══════════════════════════════════════════════════════════════════
# Tool 1 — run_scan
# ══════════════════════════════════════════════════════════════════

class RunScanParams(BaseModel):
    scope: str | None = Field(
        default=None,
        description=(
            "Management-group ID to scope the scan "
            "(passed as --mg-scope). "
            "None → default Resource Graph subscription discovery."
        ),
    )
    subscription: str | None = Field(
        default=None,
        description=(
            "Single subscription ID to scope the scan to. "
            "Faster than scanning all visible subscriptions."
        ),
    )
    demo: bool = Field(
        default=False,
        description="True → run in demo mode (no Azure connection).",
    )
    tag: str | None = Field(
        default=None,
        description="Optional label for this run snapshot.",
    )


def run_scan(params: RunScanParams) -> str:
    """Invoke scan.py as a subprocess and return run metadata.

    We shell out rather than importing main() to guarantee process
    isolation — scan.py was not designed for re-entrant calls inside
    the same interpreter.

    In demo mode, we copy the demo fixture into out/ instead of running
    scan.py (which ignores --demo for the main scan path).
    """
    from datetime import datetime as _dt, timezone as _tz
    import shutil as _shutil

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── Demo mode: copy fixture, skip subprocess ──────────────
    if params.demo:
        demo_src = _PROJECT_ROOT / "demo" / "demo_run.json"
        if not demo_src.exists():
            return json.dumps({"error": "demo/demo_run.json not found."})

        run_id = _dt.now(_tz.utc).strftime("run-%Y%m%d-%H%M")
        dest = OUT_DIR / f"{run_id}.json"
        _shutil.copy2(str(demo_src), str(dest))

        return json.dumps({
            "run_id": run_id,
            "demo": True,
            "output_paths": [str(dest.relative_to(_PROJECT_ROOT))],
        }, indent=2)

    # ── Live mode: non-blocking background scan ──────────────
    global _active_scan

    with _active_scan_lock:
        # ── If a scan is already running, report status ───────
        if _active_scan is not None:
            proc = _active_scan["process"]
            elapsed = (datetime.now(timezone.utc) - _active_scan["started"]).total_seconds()
            elapsed_str = f"{int(elapsed // 60)}m {int(elapsed % 60)}s"

            if proc.poll() is None:
                # Still running
                return json.dumps({
                    "status": "in_progress",
                    "message": (
                        f"Scan is still running ({elapsed_str} elapsed). "
                        "Call run_scan again to check, or use list_runs / "
                        "load_results once it completes."
                    ),
                    "elapsed_seconds": round(elapsed),
                }, indent=2)

            # ── Scan finished — harvest results ──────────────
            result_json = _collect_scan_result(
                proc,
                _active_scan["before_files"],
                stderr_path=_active_scan.get("stderr_path"),
            )
            _active_scan = None
            return result_json

    # ── No active scan — start one ────────────────────────────
    cmd = [sys.executable, str(_PROJECT_ROOT / "scan.py")]
    if params.scope:
        cmd.extend(["--mg-scope", params.scope])
    if params.subscription:
        cmd.extend(["--subscription", params.subscription])
    if params.tag:
        cmd.extend(["--tag", params.tag])

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    before = set(OUT_DIR.glob("run-*.json"))

    # stdout inherits from parent → scan progress prints live in
    # the workshop terminal so the CSA can see what's happening.
    # stderr goes to a temp file for error harvesting if scan fails.
    # (Using pipes would deadlock on long scans that produce >64 KB.)
    stderr_fd = tempfile.NamedTemporaryFile(
        mode="w", suffix="_scan_stderr.log", dir=str(OUT_DIR),
        delete=False, encoding="utf-8",
    )

    process = subprocess.Popen(
        cmd,
        stdout=None,   # inherit → prints live to console
        stderr=stderr_fd,
        cwd=str(_PROJECT_ROOT),
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )

    stderr_fd.close()  # subprocess owns the fd now

    with _active_scan_lock:
        _active_scan = {
            "process": process,
            "started": datetime.now(timezone.utc),
            "before_files": before,
            "cmd": cmd,
            "stderr_path": stderr_fd.name,
        }

    return json.dumps({
        "status": "started",
        "message": (
            "Scan started in the background. A live scan typically takes "
            "5–10 minutes depending on tenant size. "
            "Call run_scan again to check progress, or use list_runs / "
            "load_results once it completes."
        ),
    }, indent=2)


# ══════════════════════════════════════════════════════════════════
# Tool 2 — load_results
# ══════════════════════════════════════════════════════════════════

class LoadResultsParams(BaseModel):
    run_id: str = Field(
        default="latest",
        description=(
            "The run ID to load (e.g. 'run-20260224-1430'). "
            "'latest' → newest run in out/."
        ),
    )


def load_results(params: LoadResultsParams) -> str:
    """Load a run and return its metadata summary."""
    try:
        run = _load_cached(params.run_id)
    except (RuntimeError, FileNotFoundError) as exc:
        return json.dumps({"error": str(exc)})

    meta = run.get("meta", {})
    scoring = run.get("scoring", {})
    ctx = run.get("execution_context", {})
    results = run.get("results", [])

    return json.dumps({
        "run_id": meta.get("run_id"),
        "timestamp": meta.get("timestamp"),
        "total_controls": meta.get("total_controls", len(results)),
        "subscription_ids": meta.get("subscription_ids", []),
        "tag": meta.get("tag"),
        "overall_maturity_percent": scoring.get("overall_maturity_percent"),
        "section_count": len(scoring.get("section_scores", [])),
        "has_ai": bool(run.get("ai")),
        "has_delta": bool(run.get("delta")),
        "tenant_id": ctx.get("tenant_id"),
        "tenant_name": ctx.get("tenant_display_name"),
        "cached": True,
    }, indent=2, default=str)


# ══════════════════════════════════════════════════════════════════
# Tool 3 — summarize_findings
# ══════════════════════════════════════════════════════════════════

class SummarizeFindingsParams(BaseModel):
    run_id: str = Field(
        default="latest",
        description="Run ID to summarise. 'latest' → newest run.",
    )
    design_area: str | None = Field(
        default=None,
        description=(
            "Filter by ALZ design area / section "
            "(e.g. 'Security', 'Networking', 'Identity'). None → all."
        ),
    )
    severity: str | None = Field(
        default=None,
        description="Filter by severity: Critical, High, Medium, Low. None → all.",
    )
    failed_only: bool = Field(
        default=False,
        description="If True, return only controls with status 'Fail'.",
    )
    limit: int = Field(
        default=25,
        description="Max items to return in top_items (default 25).",
    )


def summarize_findings(params: SummarizeFindingsParams) -> str:
    """Filter the results array and return a deterministic summary."""
    try:
        run = _load_cached(params.run_id)
    except (RuntimeError, FileNotFoundError) as exc:
        return json.dumps({"error": str(exc)})

    controls: list[dict] = list(run.get("results", []))
    total_before_filter = len(controls)

    # ── Apply filters ─────────────────────────────────────────
    if params.design_area:
        da = params.design_area.lower()
        controls = [
            c for c in controls
            if c.get("section", "").lower() == da
            or c.get("category", "").lower() == da
        ]

    if params.severity:
        sev = params.severity.lower()
        controls = [
            c for c in controls
            if c.get("severity", "").lower() == sev
        ]

    if params.failed_only:
        controls = [
            c for c in controls
            if c.get("status", "").lower() == "fail"
        ]

    # ── Build deterministic summary ───────────────────────────
    status_counts: dict[str, int] = {}
    severity_counts: dict[str, int] = {}
    for c in controls:
        st = c.get("status", "Unknown")
        sv = c.get("severity", "Unknown")
        status_counts[st] = status_counts.get(st, 0) + 1
        severity_counts[sv] = severity_counts.get(sv, 0) + 1

    # Project top_items with relevant fields only
    top_items = []
    for c in controls[: params.limit]:
        top_items.append({
            "control_id": c.get("control_id"),
            "section": c.get("section"),
            "severity": c.get("severity"),
            "status": c.get("status"),
            "text": c.get("text"),
            "notes": c.get("notes"),
        })

    filters_applied = {}
    if params.design_area:
        filters_applied["design_area"] = params.design_area
    if params.severity:
        filters_applied["severity"] = params.severity
    if params.failed_only:
        filters_applied["failed_only"] = True

    summary_text = (
        f"{len(controls)} of {total_before_filter} controls match filters"
    )
    if status_counts.get("Fail"):
        summary_text += f" — {status_counts['Fail']} failing"

    return json.dumps({
        "summary": summary_text,
        "total_controls": total_before_filter,
        "matched": len(controls),
        "filters": filters_applied,
        "status_breakdown": status_counts,
        "severity_breakdown": severity_counts,
        "top_items": top_items,
    }, indent=2, default=str)


# ══════════════════════════════════════════════════════════════════
# Tool 4 — generate_outputs
# ══════════════════════════════════════════════════════════════════

ALLOWED_FORMATS = {"html", "excel"}


class GenerateOutputsParams(BaseModel):
    run_id: str = Field(
        default="latest",
        description="Run ID whose data to render. 'latest' → newest run.",
    )
    formats: list[str] = Field(
        default=["html"],
        description=(
            f"Output formats to generate. "
            f"Allowed: {sorted(ALLOWED_FORMATS)}."
        ),
    )


def generate_outputs(params: GenerateOutputsParams) -> str:
    """Generate reports for the specified run.

    Guardrails:
      - Only allowed formats accepted
      - All paths validated inside out/
      - No scoring or data mutation
    """
    # ── Validate formats ──────────────────────────────────────
    requested = {f.lower().strip() for f in params.formats}
    invalid = requested - ALLOWED_FORMATS
    if invalid:
        return json.dumps({
            "error": f"Invalid format(s): {sorted(invalid)}. "
                     f"Allowed: {sorted(ALLOWED_FORMATS)}",
        })

    if not requested:
        return json.dumps({"error": "No formats specified."})

    # ── Load run ──────────────────────────────────────────────
    try:
        run = _load_cached(params.run_id)
    except (RuntimeError, FileNotFoundError) as exc:
        return json.dumps({"error": str(exc)})

    run_id = run.get("meta", {}).get("run_id", params.run_id)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    generated: list[dict[str, str]] = []
    errors: list[str] = []

    # ── HTML report ───────────────────────────────────────────
    if "html" in requested:
        try:
            from reporting.render import generate_report

            # Compute snapshot number
            existing = sorted(OUT_DIR.glob(f"ALZ-Platform-Readiness-Report-{run_id}*.html"))
            snap = len(existing) + 1
            report_name = f"ALZ-Platform-Readiness-Report-{run_id}-S{snap:03d}.html"
            report_path = ensure_out_path(OUT_DIR / report_name)

            generate_report(run, out_path=str(report_path))
            generated.append({
                "format": "html",
                "path": str(report_path.relative_to(_PROJECT_ROOT)),
            })
        except Exception as exc:
            errors.append(f"html: {exc}")

    # ── Excel workbook ────────────────────────────────────────
    if "excel" in requested:
        try:
            from reporting.csa_workbook import build_csa_workbook

            # build_csa_workbook takes file paths, not dicts.
            # Write the run to a temp path if it was loaded from cache.
            run_json_path = _resolve_run_path(
                params.run_id if params.run_id != "latest"
                else run.get("meta", {}).get("run_id", "latest")
            )

            workbook_name = f"{run_id}_CSA_Workbook.xlsm"
            workbook_path = ensure_out_path(OUT_DIR / workbook_name)
            ta_path = str(OUT_DIR / "target_architecture.json")

            # Build deterministic why-payloads for top risks (no LLM)
            from agent.why_reasoning import build_why_payload
            why_payloads: list[dict] = []
            top_risks = run.get("executive_summary", {}).get(
                "top_business_risks", []
            )
            for risk in top_risks:
                domain = (
                    risk.get("domain")
                    or risk.get("affected_domain")
                    or risk.get("title", "")
                )
                if not domain:
                    continue
                try:
                    wp = build_why_payload(run, domain, verbose=False)
                    why_payloads.append(wp)
                except Exception:
                    pass  # non-critical — workbook still useful without

            build_csa_workbook(
                run_path=str(run_json_path),
                target_path=ta_path,
                output_path=str(workbook_path),
                why_payloads=why_payloads or None,
            )
            generated.append({
                "format": "excel",
                "path": str(workbook_path.relative_to(_PROJECT_ROOT)),
            })
        except Exception as exc:
            errors.append(f"excel: {exc}")

    result: dict[str, Any] = {
        "run_id": run_id,
        "generated": generated,
    }
    if errors:
        result["errors"] = errors

    return json.dumps(result, indent=2, default=str)


# ══════════════════════════════════════════════════════════════════
# Tool 5 — list_runs
# ══════════════════════════════════════════════════════════════════

class ListRunsParams(BaseModel):
    pass  # no parameters — always operates on the active run source


def list_runs(params: ListRunsParams) -> str:
    """List discovered runs in the active run source (newest first).

    Also reports whether a background scan is currently in progress.
    """
    from src.run_store import discover_runs, sort_runs

    source = _run_source_dir if _run_source_dir is not None else OUT_DIR
    try:
        runs = sort_runs(discover_runs(source))
    except Exception as exc:
        return json.dumps({"error": str(exc)})

    # ── Check for an active background scan ────────────────────
    scan_status: dict[str, Any] | None = None
    with _active_scan_lock:
        if _active_scan is not None:
            proc = _active_scan["process"]
            elapsed = (datetime.now(timezone.utc) - _active_scan["started"]).total_seconds()
            if proc.poll() is None:
                scan_status = {
                    "active": True,
                    "elapsed_seconds": round(elapsed),
                    "message": f"Scan in progress ({int(elapsed // 60)}m {int(elapsed % 60)}s elapsed)",
                }
            else:
                scan_status = {
                    "active": False,
                    "message": "Background scan finished. Call run_scan to collect results.",
                }

    if not runs and scan_status is None:
        return json.dumps({
            "run_source": str(source),
            "count": 0,
            "runs": [],
            "message": "No runs found in the selected source.",
        })

    entries = []
    for i, ref in enumerate(runs):
        entries.append({
            "index": i,
            "display_name": ref.display_name,
            "path": str(ref.path),
            "timestamp": ref.timestamp.isoformat() if ref.timestamp else None,
            "role": "latest" if i == 0 else ("previous" if i == 1 else None),
        })

    result: dict[str, Any] = {
        "run_source": str(source),
        "count": len(entries),
        "runs": entries,
    }
    if scan_status is not None:
        result["scan_in_progress"] = scan_status

    return json.dumps(result, indent=2, default=str)


# ══════════════════════════════════════════════════════════════════
# Tool 6 — compare_runs
# ══════════════════════════════════════════════════════════════════

class CompareRunsParams(BaseModel):
    pass  # always compares latest vs previous in the active run source


def compare_runs(params: CompareRunsParams) -> str:
    """Compare the latest run against the previous run (delta analysis).

    Guardrails:
      - Reads from the active run source (demo or out/)
      - Delta output written only to out/deltas/ (never into demo)
    """
    from src.run_store import discover_runs, sort_runs, load_run as _load_run_ref

    source = _run_source_dir if _run_source_dir is not None else OUT_DIR
    try:
        runs = sort_runs(discover_runs(source))
    except Exception as exc:
        return json.dumps({"error": str(exc)})

    if len(runs) < 2:
        return json.dumps({
            "error": (
                f"Not enough runs to compare. "
                f"Found {len(runs)} run(s) in {source}. "
                "At least 2 runs are needed for a delta comparison."
            ),
            "run_source": str(source),
            "count": len(runs),
        })

    latest_ref = runs[0]
    previous_ref = runs[1]

    try:
        latest_data = _load_run_ref(latest_ref)
        previous_data = _load_run_ref(previous_ref)
    except Exception as exc:
        return json.dumps({"error": f"Failed to load run data: {exc}"})

    # ── Compute deterministic delta ───────────────────────────────
    def _score(run: dict) -> float | None:
        return run.get("scoring", {}).get("overall_maturity_percent")

    def _status_map(run: dict) -> dict[str, str]:
        return {
            c.get("control_id", ""): c.get("status", "")
            for c in run.get("results", [])
            if c.get("control_id")
        }

    latest_score = _score(latest_data)
    previous_score = _score(previous_data)
    score_delta = (
        round(latest_score - previous_score, 2)
        if latest_score is not None and previous_score is not None
        else None
    )

    latest_statuses = _status_map(latest_data)
    previous_statuses = _status_map(previous_data)

    all_ids = set(latest_statuses) | set(previous_statuses)
    changed: list[dict] = []
    for cid in sorted(all_ids):
        prev_st = previous_statuses.get(cid, "absent")
        curr_st = latest_statuses.get(cid, "absent")
        if prev_st != curr_st:
            changed.append({
                "control_id": cid,
                "previous_status": prev_st,
                "latest_status": curr_st,
            })

    regressions = [c for c in changed if c["latest_status"] == "Fail"]
    improvements = [c for c in changed if c["previous_status"] == "Fail"
                    and c["latest_status"] != "Fail"]

    latest_id = (
        latest_data.get("meta", {}).get("run_id")
        or latest_ref.display_name
    )
    previous_id = (
        previous_data.get("meta", {}).get("run_id")
        or previous_ref.display_name
    )

    delta_payload: dict[str, Any] = {
        "latest_run": latest_id,
        "previous_run": previous_id,
        "score_delta": score_delta,
        "latest_score": latest_score,
        "previous_score": previous_score,
        "total_changes": len(changed),
        "regressions": len(regressions),
        "improvements": len(improvements),
        "changed_controls": changed,
    }

    # ── Write delta to out/deltas/ (guardrail: never outside out/) ─
    deltas_dir = OUT_DIR / "deltas"
    deltas_dir.mkdir(parents=True, exist_ok=True)
    safe_latest = _UNSAFE_ID_CHARS.sub("_", str(latest_id))
    safe_previous = _UNSAFE_ID_CHARS.sub("_", str(previous_id))
    delta_filename = f"{safe_latest}__{safe_previous}.json"
    delta_path = ensure_out_path(deltas_dir / delta_filename)
    delta_path.write_text(
        json.dumps(delta_payload, indent=2, default=str),
        encoding="utf-8",
    )

    delta_payload["delta_path"] = delta_path.relative_to(_PROJECT_ROOT).as_posix()
    return json.dumps(delta_payload, indent=2, default=str)


