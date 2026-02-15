"""Container posture signal provider — AKS + ACR."""
from __future__ import annotations

from signals.types import SignalResult, SignalStatus
from signals.providers.resource_graph import _query_rg


def fetch_aks_posture(subscriptions: list[str]) -> SignalResult:
    """Evaluate AKS clusters for RBAC, network policy, private API, managed identity."""
    query = """
    Resources
    | where type =~ 'microsoft.containerservice/managedclusters'
    | extend rbacEnabled   = tostring(properties.enableRBAC),
             networkPlugin = tostring(properties.networkProfile.networkPlugin),
             networkPolicy = tostring(properties.networkProfile.networkPolicy),
             privateCluster = tostring(properties.apiServerAccessProfile.enablePrivateCluster),
             identityType  = tostring(identity.type),
             skuTier       = tostring(sku.tier)
    | project name, resourceGroup, location, id,
              rbacEnabled, networkPlugin, networkPolicy, privateCluster, identityType, skuTier
    """
    r = _query_rg(query, subscriptions)
    r.signal_name = "resource_graph:aks_posture"

    if r.status == SignalStatus.OK:
        items = r.items or []
        total = len(items)
        compliant = 0
        issues: list[dict] = []

        for aks in items:
            ok = True
            aks_issues = []

            if (aks.get("rbacEnabled") or "").lower() not in ("true", "1"):
                aks_issues.append("RBAC not enabled")
                ok = False
            if not aks.get("networkPolicy"):
                aks_issues.append("no network policy configured")
                ok = False
            if (aks.get("privateCluster") or "").lower() not in ("true", "1"):
                aks_issues.append("public API server")
                ok = False
            if (aks.get("identityType") or "").lower() not in ("systemassigned", "userassigned"):
                aks_issues.append("no managed identity")
                ok = False

            if ok:
                compliant += 1
            else:
                issues.append({"resource": aks.get("name"), "id": aks.get("id"),
                               "issues": aks_issues})

        ratio = round(compliant / total, 4) if total else 0.0
        r.raw = {
            "query": "aks_posture",
            "count": total,
            "coverage": {"applicable": total, "compliant": compliant, "ratio": ratio},
            "non_compliant_details": issues[:20],
        }
    return r


def fetch_acr_posture(subscriptions: list[str]) -> SignalResult:
    """Evaluate Container Registries for SKU, admin user, public access."""
    query = """
    Resources
    | where type =~ 'microsoft.containerregistry/registries'
    | extend skuName       = tostring(sku.name),
             adminEnabled  = tostring(properties.adminUserEnabled),
             publicNetwork = tostring(properties.publicNetworkAccess)
    | project name, resourceGroup, location, id,
              skuName, adminEnabled, publicNetwork
    """
    r = _query_rg(query, subscriptions)
    r.signal_name = "resource_graph:acr_posture"

    if r.status == SignalStatus.OK:
        items = r.items or []
        total = len(items)
        compliant = 0
        issues: list[dict] = []

        for acr in items:
            ok = True
            acr_issues = []

            if (acr.get("skuName") or "").lower() == "basic":
                acr_issues.append("Basic SKU (no geo-replication, no private link)")
                ok = False
            if (acr.get("adminEnabled") or "").lower() in ("true", "1"):
                acr_issues.append("admin user enabled")
                ok = False
            if (acr.get("publicNetwork") or "Enabled").lower() == "enabled":
                acr_issues.append("public network access enabled")
                ok = False

            if ok:
                compliant += 1
            else:
                issues.append({"resource": acr.get("name"), "id": acr.get("id"),
                               "issues": acr_issues})

        ratio = round(compliant / total, 4) if total else 0.0
        r.raw = {
            "query": "acr_posture",
            "count": total,
            "coverage": {"applicable": total, "compliant": compliant, "ratio": ratio},
            "non_compliant_details": issues[:20],
        }
    return r
