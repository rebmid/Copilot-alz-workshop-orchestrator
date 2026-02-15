"""Storage account posture signal provider."""
from __future__ import annotations

from signals.types import SignalResult, SignalStatus
from signals.providers.resource_graph import _query_rg


def fetch_storage_posture(subscriptions: list[str]) -> SignalResult:
    """Evaluate storage accounts for public access, HTTPS, TLS, and network ACLs."""
    query = """
    Resources
    | where type =~ 'microsoft.storage/storageaccounts'
    | extend publicAccess    = tostring(properties.allowBlobPublicAccess),
             httpsOnly       = tostring(properties.supportsHttpsTrafficOnly),
             minTls          = tostring(properties.minimumTlsVersion),
             networkDefault  = tostring(properties.networkAcls.defaultAction),
             publicNetwork   = tostring(properties.publicNetworkAccess)
    | project name, resourceGroup, location, id,
              publicAccess, httpsOnly, minTls, networkDefault, publicNetwork
    """
    r = _query_rg(query, subscriptions)
    r.signal_name = "resource_graph:storage_posture"

    if r.status == SignalStatus.OK:
        items = r.items or []
        total = len(items)
        compliant = 0
        issues: list[dict] = []

        for sa in items:
            ok = True
            sa_issues = []

            if (sa.get("publicAccess") or "").lower() in ("true", "1"):
                sa_issues.append("blob public access enabled")
                ok = False
            if (sa.get("httpsOnly") or "").lower() not in ("true", "1"):
                sa_issues.append("HTTPS-only not enforced")
                ok = False
            if (sa.get("minTls") or "").lower() not in ("tls1_2", "tls1_3"):
                sa_issues.append(f"TLS < 1.2 ({sa.get('minTls', 'unknown')})")
                ok = False
            if (sa.get("networkDefault") or "").lower() != "deny":
                sa_issues.append("network ACL default is Allow (not restricted)")
                ok = False

            if ok:
                compliant += 1
            else:
                issues.append({"resource": sa.get("name"), "id": sa.get("id"),
                               "issues": sa_issues})

        ratio = round(compliant / total, 4) if total else 0.0
        r.raw = {
            "query": "storage_posture",
            "count": total,
            "coverage": {"applicable": total, "compliant": compliant, "ratio": ratio},
            "non_compliant_details": issues[:20],
        }
    return r
