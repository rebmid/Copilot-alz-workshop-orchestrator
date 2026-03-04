#!/usr/bin/env python3
import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


STATUS_ORDER = {
    "Fail": 0,
    "Partial": 1,
    "Manual": 2,
    "Not Applicable": 2,
    "Pass": 3,
}

SEVERITY_WEIGHT = {
    "high": 3,
    "medium": 2,
    "low": 1,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate deterministic ALZ delta summary markdown from two run JSON files."
    )
    parser.add_argument("--previous", required=True, help="Path to previous run JSON")
    parser.add_argument("--current", required=True, help="Path to current run JSON")
    parser.add_argument("--output", required=True, help="Path to markdown output")
    parser.add_argument("--top", type=int, default=5, help="Top N regressions/improvements")
    return parser.parse_args()


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _status_rank(status: str | None) -> int:
    if not status:
        return -1
    return STATUS_ORDER.get(status, -1)


def _severity_value(item: dict) -> int:
    severity = str(item.get("severity", "")).strip().lower()
    return SEVERITY_WEIGHT.get(severity, 0)


def _run_label(payload: dict, fallback: str) -> str:
    meta = payload.get("meta", {})
    return str(meta.get("run_id") or meta.get("timestamp") or fallback)


def _section_maturity_map(payload: dict) -> dict[str, float]:
    section_scores = payload.get("scoring", {}).get("section_scores", [])
    mapped: dict[str, float] = {}
    for section in section_scores:
        name = section.get("section")
        maturity = section.get("maturity_percent")
        if name is None or maturity is None:
            continue
        try:
            mapped[str(name)] = float(maturity)
        except (TypeError, ValueError):
            continue
    return mapped


def _format_delta(value: float | None) -> str:
    if value is None:
        return "n/a"
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.1f}pp"


def _line_for_change(change: dict) -> str:
    severity = change.get("severity") or "Unknown"
    section = change.get("section") or "Unknown"
    title = change.get("title") or change["control_id"]
    return (
        f"- `{change['control_id']}` ({section}, {severity}) — "
        f"{change['previous']} → {change['current']} — {title}"
    )


def build_summary(previous: dict, current: dict, top_n: int) -> str:
    prev_results = {item["control_id"]: item for item in previous.get("results", []) if "control_id" in item}
    curr_results = {item["control_id"]: item for item in current.get("results", []) if "control_id" in item}

    common_ids = sorted(set(prev_results) & set(curr_results))
    added_ids = sorted(set(curr_results) - set(prev_results))
    removed_ids = sorted(set(prev_results) - set(curr_results))

    changed: list[dict] = []
    regressions: list[dict] = []
    improvements: list[dict] = []
    transition_counts: Counter[str] = Counter()

    for control_id in common_ids:
        prev_item = prev_results[control_id]
        curr_item = curr_results[control_id]

        prev_status = prev_item.get("status")
        curr_status = curr_item.get("status")

        if prev_status == curr_status:
            continue

        prev_rank = _status_rank(prev_status)
        curr_rank = _status_rank(curr_status)
        magnitude = abs(curr_rank - prev_rank)
        severity_value = max(_severity_value(prev_item), _severity_value(curr_item))

        row = {
            "control_id": control_id,
            "previous": prev_status,
            "current": curr_status,
            "section": curr_item.get("section") or prev_item.get("section"),
            "severity": curr_item.get("severity") or prev_item.get("severity"),
            "title": curr_item.get("question") or curr_item.get("text") or prev_item.get("question") or prev_item.get("text"),
            "magnitude": magnitude,
            "severity_value": severity_value,
        }

        changed.append(row)
        transition_counts[f"{prev_status} → {curr_status}"] += 1

        if curr_rank < prev_rank:
            regressions.append(row)
        elif curr_rank > prev_rank:
            improvements.append(row)

    regressions.sort(key=lambda item: (-item["magnitude"], -item["severity_value"], item["control_id"]))
    improvements.sort(key=lambda item: (-item["magnitude"], -item["severity_value"], item["control_id"]))

    prev_maturity = previous.get("scoring", {}).get("overall_maturity_percent")
    curr_maturity = current.get("scoring", {}).get("overall_maturity_percent")
    maturity_delta = None
    if isinstance(prev_maturity, (int, float)) and isinstance(curr_maturity, (int, float)):
        maturity_delta = float(curr_maturity) - float(prev_maturity)

    prev_sections = _section_maturity_map(previous)
    curr_sections = _section_maturity_map(current)
    section_deltas = []
    for section in sorted(set(prev_sections) | set(curr_sections)):
        delta = curr_sections.get(section, 0.0) - prev_sections.get(section, 0.0)
        if abs(delta) > 0:
            section_deltas.append((section, delta))
    section_deltas.sort(key=lambda item: abs(item[1]), reverse=True)

    lines: list[str] = []
    lines.append("# Continuous ALZ Posture Delta Summary")
    lines.append("")
    lines.append(f"- Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"- Previous run: {_run_label(previous, 'previous')}")
    lines.append(f"- Current run: {_run_label(current, 'current')}")
    lines.append("")
    lines.append("## What changed")
    lines.append(f"- Controls compared: {len(common_ids)}")
    lines.append(f"- Status changes: {len(changed)}")
    lines.append(f"- Regressions: {len(regressions)}")
    lines.append(f"- Improvements: {len(improvements)}")
    lines.append(f"- Added controls in current run: {len(added_ids)}")
    lines.append(f"- Removed controls from previous run: {len(removed_ids)}")
    lines.append(f"- Overall maturity delta: {_format_delta(maturity_delta)}")

    if transition_counts:
        lines.append("- Status transition counts:")
        for transition, count in transition_counts.most_common():
            lines.append(f"  - {transition}: {count}")

    if section_deltas:
        lines.append("- Largest design area maturity shifts:")
        for section, delta in section_deltas[:top_n]:
            lines.append(f"  - {section}: {_format_delta(delta)}")

    lines.append("")
    lines.append("## Top regressions")
    if regressions:
        for row in regressions[:top_n]:
            lines.append(_line_for_change(row))
    else:
        lines.append("- No regressions detected.")

    lines.append("")
    lines.append("## Notable improvements")
    if improvements:
        for row in improvements[:top_n]:
            lines.append(_line_for_change(row))
    else:
        lines.append("- No improvements detected.")

    lines.append("")
    lines.append("_Summary generated from deterministic run JSON only; no scoring overrides or inferred results._")
    lines.append("")

    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    previous_path = Path(args.previous)
    current_path = Path(args.current)
    output_path = Path(args.output)

    previous = _load_json(previous_path)
    current = _load_json(current_path)
    markdown = build_summary(previous, current, max(1, args.top))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")
    print(f"Delta summary written: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
