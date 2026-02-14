import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from azure.mgmt.resourcegraph import ResourceGraphClient
from azure.mgmt.resourcegraph.models import QueryRequest
from collectors.auth import get_credential, get_arm_token

DIAG_API = "2021-05-01-preview"

def _arm_get(url: str):
    token = get_arm_token()
    r = requests.get(url, headers={"Authorization": f"Bearer {token}"})
    r.raise_for_status()
    return r.json()

def _has_diag_settings(resource_id: str) -> bool:
    url = f"https://management.azure.com{resource_id}/providers/microsoft.insights/diagnosticSettings?api-version={DIAG_API}"
    try:
        data = _arm_get(url)
        return len(data.get("value", []) or []) > 0
    except Exception:
        # Some resources don't support diag settings (or insufficient perms)
        return False

def collect_diagnostics_coverage(subscription_ids: list[str], max_resources: int = 200, workers: int = 16):
    """
    Scalable approximation:
      - pull up to max_resources resources via Resource Graph
      - check diag settings for each resource concurrently
      - report coverage percent

    This is "good enough" to be meaningful in large tenants
    without taking 30 minutes.
    """
    credential = get_credential()
    rg = ResourceGraphClient(credential)

    query = f"""
Resources
| project id, type, name, resourceGroup, subscriptionId
| limit {max_resources}
"""

    req = QueryRequest(subscriptions=subscription_ids, query=query)
    resp = rg.resources(req)
    rows: list[dict] = [r for r in (resp.data or []) if isinstance(r, dict)]

    resource_ids = [r["id"] for r in rows if "id" in r]

    checked = 0
    enabled = 0

    # concurrent checks
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(_has_diag_settings, rid): rid for rid in resource_ids}
        for fut in as_completed(futures):
            checked += 1
            if fut.result():
                enabled += 1

    coverage = round((enabled / checked) * 100, 1) if checked else None

    return {
        "sample_size": checked,
        "diag_enabled_count": enabled,
        "diag_coverage_percent": coverage,
        "note": f"Sample-based coverage (limit={max_resources}). Increase max_resources for more accuracy."
    }
