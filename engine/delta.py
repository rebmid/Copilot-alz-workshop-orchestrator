def compute_delta(prev, curr):

    prev_map = {r["control_id"]: r for r in prev.get("results", [])}
    changes = []

    for r in curr.get("results", []):
        old = prev_map.get(r["control_id"])
        if old and old["status"] != r["status"]:
            changes.append({
                "control_id": r["control_id"],
                "previous": old["status"],
                "current": r["status"]
            })

    return {
        "has_previous": True,
        "changed_controls": changes,
        "count": len(changes)
    }


def compute_trend(prev, curr):
    """Compute maturity trend between two run snapshots.

    Returns a trend dict with overall maturity delta and per-domain
    deltas.  Backwards-compatible: if either run lacks scoring data
    the deltas are set to 0.

    Output:
        {
            "has_previous": true,
            "previous_run_id": "...",
            "maturity_delta": <float>,
            "domain_deltas": { "<section>": <float>, ... }
        }
    """
    prev_scoring = prev.get("scoring", {})
    curr_scoring = curr.get("scoring", {})

    prev_overall = prev_scoring.get("overall_maturity_percent") or 0.0
    curr_overall = curr_scoring.get("overall_maturity_percent") or 0.0

    # Build per-domain (section) delta map
    prev_sections = {
        s["section"]: (s.get("maturity_percent") or 0.0)
        for s in prev_scoring.get("section_scores", [])
        if "section" in s
    }
    curr_sections = {
        s["section"]: (s.get("maturity_percent") or 0.0)
        for s in curr_scoring.get("section_scores", [])
        if "section" in s
    }

    all_domains = sorted(set(prev_sections) | set(curr_sections))
    domain_deltas = {
        d: round((curr_sections.get(d) or 0.0) - (prev_sections.get(d) or 0.0), 1)
        for d in all_domains
    }

    return {
        "has_previous": True,
        "previous_run_id": prev.get("meta", {}).get("run_id", ""),
        "maturity_delta": round(curr_overall - prev_overall, 1),
        "domain_deltas": domain_deltas,
    }
