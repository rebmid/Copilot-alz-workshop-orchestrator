def build_advisor_payload(scoring, results, execution_context, delta=None,
                         mg_hierarchy=None):
    """
    Build a compact, token-safe payload for AI clustering / advisory.
    Only the fields the model needs — never the full raw result set.
    """

    fails = [
        {
            "control_id": r["control_id"],
            "description": r.get("description"),
            "severity": r.get("severity"),
            "domain": r.get("domain"),
            "section": r.get("section"),
        }
        for r in results
        if r["status"] == "Fail"
    ]

    manual = [
        {
            "control_id": r["control_id"],
            "description": r.get("description"),
            "severity": r.get("severity"),
            "domain": r.get("domain"),
        }
        for r in results
        if r["status"] == "Manual"
        and r.get("severity") in ("High", "Critical")
    ][:25]

    return {
        "execution_context": execution_context,
        "overall_maturity": scoring["overall_maturity_percent"],
        "section_scores": scoring.get("section_scores", []),
        "top_failing_sections": scoring.get("top_failing_sections", [])[:5],
        "most_impactful_gaps": scoring.get("most_impactful_gaps", [])[:15],
        "failed_controls": fails,
        "sampled_manual_controls": manual,
        "delta": delta,
        "management_group_hierarchy": mg_hierarchy,
    }
