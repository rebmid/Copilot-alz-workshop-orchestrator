# collectors/defender.py
from __future__ import annotations
from typing import Any, Dict
from collectors.azure_client import AzureClient

SEC_API = "2024-01-01"

def collect_defender_pricings(client: AzureClient, subscription_id: str) -> Dict[str, Any]:
    data = client.get(f"/subscriptions/{subscription_id}/providers/Microsoft.Security/pricings", api_version=SEC_API)
    items = data.get("value", []) or []

    enabled = 0
    total = len(items)
    plans = []

    for p in items:
        props = p.get("properties", {}) or {}
        tier = (props.get("pricingTier") or "").lower()
        name = p.get("name")
        plans.append({"name": name, "tier": props.get("pricingTier")})
        if tier in ("standard", "premium"):  # old/new naming varies
            enabled += 1

    return {
        "subscription_id": subscription_id,
        "plans_total": total,
        "plans_enabled": enabled,
        "plans": plans
    }

def collect_secure_score(client: AzureClient) -> Dict[str, Any]:
    """
    Secure score is tenant-level in many setups.
    This endpoint can vary by tenant; keep resilient.
    """
    try:
        data = client.get("/providers/Microsoft.Security/secureScores", api_version=SEC_API)
        items = data.get("value", []) or []
        if not items:
            return {"status": "NotAvailable", "reason": "No secureScores returned.", "scores": []}

        # return top few
        scores = []
        for s in items[:5]:
            props = s.get("properties", {}) or {}
            scores.append({
                "name": s.get("name"),
                "current": props.get("currentScore"),
                "max": props.get("maxScore"),
                "percentage": props.get("percentage")
            })

        return {"status": "OK", "scores": scores}
    except Exception as e:
        return {"status": "Error", "reason": str(e), "scores": []}
