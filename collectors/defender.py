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

def collect_secure_score(client: AzureClient, subscription_id: str) -> Dict[str, Any]:
    """
    Secure score scoped to a subscription.

    Uses the subscription-scoped endpoint which is the most reliable path.
    Falls back to the unscoped endpoint if subscription-scoped returns nothing.
    """
    try:
        # Primary: subscription-scoped endpoint (most reliable)
        data = client.get(
            f"/subscriptions/{subscription_id}/providers/Microsoft.Security/secureScores",
            api_version=SEC_API,
        )
        items = data.get("value", []) or []

        # Fallback: unscoped endpoint
        if not items:
            try:
                data = client.get(
                    "/providers/Microsoft.Security/secureScores",
                    api_version=SEC_API,
                )
                items = data.get("value", []) or []
            except Exception:
                pass

        if not items:
            return {"status": "NotAvailable", "reason": "No secureScores returned.", "scores": []}

        scores = []
        for s in items[:5]:
            props = s.get("properties", {}) or {}
            score_def = props.get("scoreDetails", {}) or {}
            current_score = props.get("score", {}) or {}
            scores.append({
                "name": s.get("name"),
                "current": current_score.get("current", props.get("currentScore")),
                "max": current_score.get("max", props.get("maxScore")),
                "percentage": current_score.get("percentage", props.get("percentage")),
                "weight": score_def.get("weight"),
            })

        return {"status": "OK", "subscription_id": subscription_id, "scores": scores}
    except Exception as e:
        return {"status": "Error", "reason": str(e), "scores": []}
