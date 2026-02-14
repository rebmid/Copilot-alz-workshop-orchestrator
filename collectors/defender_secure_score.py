import requests
from collectors.auth import get_arm_token

SECURITY_API = "2020-01-01"

def _arm_get(url: str):
    token = get_arm_token()
    r = requests.get(url, headers={"Authorization": f"Bearer {token}"})
    r.raise_for_status()
    return r.json()

def collect_secure_score(subscription_id: str):
    """
    Returns:
      - secure score summary
      - top controls (by unhealthy)
    """
    base = f"https://management.azure.com/subscriptions/{subscription_id}/providers/Microsoft.Security"

    # Secure scores
    scores = _arm_get(f"{base}/secureScores?api-version={SECURITY_API}")
    score_items = scores.get("value", []) or []

    # Most tenants have 1 primary score; choose the first for summary
    score_summary = None
    if score_items:
        p = (score_items[0].get("properties") or {})
        score_summary = {
            "name": score_items[0].get("name"),
            "current_score": p.get("currentScore"),
            "max_score": p.get("maxScore"),
            "percentage": p.get("percentage")
        }

    # Controls breakdown
    controls = _arm_get(f"{base}/secureScoreControls?api-version={SECURITY_API}")
    ctrl_items = controls.get("value", []) or []

    # Rank controls by unhealthy resource count if present
    ranked = []
    for c in ctrl_items:
        p = c.get("properties", {}) or {}
        ranked.append({
            "name": c.get("name"),
            "display_name": p.get("displayName"),
            "score": p.get("score"),
            "max_score": p.get("maxScore"),
            "healthy": p.get("healthyResourceCount"),
            "unhealthy": p.get("unhealthyResourceCount")
        })

    ranked.sort(key=lambda x: (x.get("unhealthy") or 0), reverse=True)

    return {
        "subscription_id": subscription_id,
        "secure_score": score_summary,
        "top_controls": ranked[:15],
        "control_count": len(ranked)
    }
