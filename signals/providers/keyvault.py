"""Key Vault posture signal provider."""
from __future__ import annotations

from signals.types import SignalResult, SignalStatus
from signals.providers.resource_graph import _query_rg


def fetch_keyvault_posture(subscriptions: list[str]) -> SignalResult:
    """Evaluate Key Vaults for purge protection, RBAC mode, public network access."""
    query = """
    Resources
    | where type =~ 'microsoft.keyvault/vaults'
    | extend purgeProtect   = tostring(properties.enablePurgeProtection),
             softDelete     = tostring(properties.enableSoftDelete),
             rbacAuth       = tostring(properties.enableRbacAuthorization),
             publicNetwork  = tostring(properties.publicNetworkAccess),
             skuName        = tostring(properties.sku.name)
    | project name, resourceGroup, location, id,
              purgeProtect, softDelete, rbacAuth, publicNetwork, skuName
    """
    r = _query_rg(query, subscriptions)
    r.signal_name = "resource_graph:keyvault_posture"

    if r.status == SignalStatus.OK:
        items = r.items or []
        total = len(items)
        compliant = 0
        issues: list[dict] = []

        for kv in items:
            ok = True
            kv_issues = []

            if (kv.get("purgeProtect") or "").lower() not in ("true", "1"):
                kv_issues.append("purge protection disabled")
                ok = False
            if (kv.get("softDelete") or "").lower() not in ("true", "1"):
                kv_issues.append("soft delete disabled")
                ok = False
            if (kv.get("rbacAuth") or "").lower() not in ("true", "1"):
                kv_issues.append("RBAC auth not enabled (using vault access policies)")
                ok = False
            if (kv.get("publicNetwork") or "Enabled").lower() == "enabled":
                kv_issues.append("public network access enabled")
                ok = False

            if ok:
                compliant += 1
            else:
                issues.append({"resource": kv.get("name"), "id": kv.get("id"),
                               "issues": kv_issues})

        ratio = round(compliant / total, 4) if total else 0.0
        r.raw = {
            "query": "keyvault_posture",
            "count": total,
            "coverage": {"applicable": total, "compliant": compliant, "ratio": ratio},
            "non_compliant_details": issues[:20],
        }
    return r
