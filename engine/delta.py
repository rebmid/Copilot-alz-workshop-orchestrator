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
