# collectors/diagnostics.py
from __future__ import annotations
from collections import defaultdict
from typing import Any, Dict, List, Tuple
from collectors.azure_client import AzureClient

RES_API = "2021-04-01"
DIAG_API = "2021-05-01-preview"

def _list_resources(client: AzureClient, subscription_id: str, top: int = 500) -> List[Dict[str, Any]]:
    data = client.get(f"/subscriptions/{subscription_id}/resources", api_version=RES_API, params={"$top": top})
    return data.get("value", []) or []

def _has_diag(client: AzureClient, resource_id: str) -> bool:
    try:
        data = client.get(f"{resource_id}/providers/microsoft.insights/diagnosticSettings", api_version=DIAG_API)
        items = data.get("value", []) or []
        return len(items) > 0
    except Exception:
        # some resources don't support diag settings; treat separately later if you want
        return False

def collect_diagnostics_coverage(client: AzureClient, subscription_id: str, max_resources: int = 300) -> Dict[str, Any]:
    resources = _list_resources(client, subscription_id, top=max_resources)
    total = len(resources)

    enabled = 0
    by_type_total = defaultdict(int)
    by_type_enabled = defaultdict(int)

    for r in resources:
        rid = r.get("id")
        rtype = (r.get("type") or "unknown").lower()
        by_type_total[rtype] += 1

        if rid and _has_diag(client, rid):
            enabled += 1
            by_type_enabled[rtype] += 1

    coverage = round((enabled / total) * 100.0, 1) if total else None

    # top missing types
    gaps = []
    for t, cnt in by_type_total.items():
        en = by_type_enabled.get(t, 0)
        miss = cnt - en
        if cnt > 0:
            gaps.append((t, miss, cnt))
    gaps.sort(key=lambda x: (x[1], x[2]), reverse=True)

    return {
        "subscription_id": subscription_id,
        "method": "sample",
        "sample_size": total,
        "diag_enabled_count": enabled,
        "diag_coverage_percent": coverage,
        "top_missing_types": [{"type": t, "missing": miss, "total": cnt} for t, miss, cnt in gaps[:10]],
        "note": f"Sample-based coverage (limit={max_resources}). Increase max_resources for more accuracy."
    }
