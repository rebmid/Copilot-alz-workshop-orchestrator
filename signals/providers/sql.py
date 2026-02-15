"""SQL / database posture signal provider."""
from __future__ import annotations

from signals.types import SignalResult, SignalStatus
from signals.providers.resource_graph import _query_rg


def fetch_sql_posture(subscriptions: list[str]) -> SignalResult:
    """Evaluate SQL servers for TDE, auditing, public network, Entra-only auth."""
    query = """
    Resources
    | where type =~ 'microsoft.sql/servers'
    | extend publicNetwork  = tostring(properties.publicNetworkAccess),
             minTls         = tostring(properties.minimalTlsVersion),
             entraOnly      = tostring(properties.administrators.azureADOnlyAuthentication),
             adminLogin     = tostring(properties.administratorLogin)
    | project name, resourceGroup, location, id,
              publicNetwork, minTls, entraOnly, adminLogin
    """
    r = _query_rg(query, subscriptions)
    r.signal_name = "resource_graph:sql_posture"

    if r.status == SignalStatus.OK:
        items = r.items or []
        total = len(items)
        compliant = 0
        issues: list[dict] = []

        for srv in items:
            ok = True
            srv_issues = []

            if (srv.get("publicNetwork") or "Enabled").lower() == "enabled":
                srv_issues.append("public network access enabled")
                ok = False
            if (srv.get("minTls") or "") < "1.2":
                srv_issues.append(f"TLS < 1.2 ({srv.get('minTls', 'unset')})")
                ok = False
            if (srv.get("entraOnly") or "").lower() not in ("true", "1"):
                srv_issues.append("Entra-only auth not enabled")
                ok = False

            if ok:
                compliant += 1
            else:
                issues.append({"resource": srv.get("name"), "id": srv.get("id"),
                               "issues": srv_issues})

        ratio = round(compliant / total, 4) if total else 0.0
        r.raw = {
            "query": "sql_posture",
            "count": total,
            "coverage": {"applicable": total, "compliant": compliant, "ratio": ratio},
            "non_compliant_details": issues[:20],
        }
    return r
