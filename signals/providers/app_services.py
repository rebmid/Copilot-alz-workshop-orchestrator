"""App Service posture signal provider."""
from __future__ import annotations

from signals.types import SignalResult, SignalStatus
from signals.providers.resource_graph import _query_rg


def fetch_app_service_posture(subscriptions: list[str]) -> SignalResult:
    """Evaluate App Services for HTTPS, managed identity, VNet integration."""
    query = """
    Resources
    | where type =~ 'microsoft.web/sites'
    | extend httpsOnly   = tostring(properties.httpsOnly),
             vnetInteg   = iff(isnotempty(tostring(properties.virtualNetworkSubnetId)), true, false),
             managedId   = iff(isnotempty(identity), true, false)
    | project name, resourceGroup, location, id, kind,
              httpsOnly, vnetInteg, managedId
    """
    r = _query_rg(query, subscriptions)
    r.signal_name = "resource_graph:app_service_posture"

    if r.status == SignalStatus.OK:
        items = r.items or []
        total = len(items)
        compliant = 0
        issues: list[dict] = []

        for app in items:
            ok = True
            app_issues = []

            if (app.get("httpsOnly") or "").lower() not in ("true", "1"):
                app_issues.append("HTTPS-only not enforced")
                ok = False
            if not app.get("managedId"):
                app_issues.append("no managed identity")
                ok = False

            if ok:
                compliant += 1
            else:
                issues.append({"resource": app.get("name"), "id": app.get("id"),
                               "issues": app_issues})

        ratio = round(compliant / total, 4) if total else 0.0
        r.raw = {
            "query": "app_service_posture",
            "count": total,
            "coverage": {"applicable": total, "compliant": compliant, "ratio": ratio},
            "non_compliant_details": issues[:20],
        }
    return r
