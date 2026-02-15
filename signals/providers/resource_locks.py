"""Resource lock signal provider."""
from __future__ import annotations

from signals.types import SignalResult, SignalStatus
from signals.providers.resource_graph import _query_rg


def fetch_resource_locks(subscriptions: list[str]) -> SignalResult:
    """Inventory resource locks and compute lock coverage for critical resource types."""
    query = """
    ResourceContainers
    | where type =~ 'microsoft.resources/subscriptions/resourcegroups'
    | project rgName=name, rgId=id
    | join kind=leftouter (
        Resources
        | where type =~ 'microsoft.authorization/locks'
        | extend lockLevel = tostring(properties.level)
        | project lockName=name, lockLevel, lockScope=id
    ) on $left.rgId == $right.lockScope
    | summarize lockCount=countif(isnotempty(lockName)) by rgName, rgId
    | project rgName, rgId, lockCount, hasLock=(lockCount > 0)
    """
    # Simpler approach — just check subscription-level lock data via ARG
    lock_query = """
    Resources
    | where type =~ 'microsoft.authorization/locks'
    | extend lockLevel = tostring(properties.level)
    | project name, lockLevel, resourceGroup, id
    """
    r = _query_rg(lock_query, subscriptions)
    r.signal_name = "resource_graph:resource_locks"

    if r.status == SignalStatus.OK:
        locks = r.items or []
        # Check production-critical resource groups (count RGs with locks)
        rg_query = """
        ResourceContainers
        | where type =~ 'microsoft.resources/subscriptions/resourcegroups'
        | project name, id
        """
        rg_r = _query_rg(rg_query, subscriptions)
        total_rgs = len(rg_r.items) if rg_r.status == SignalStatus.OK else 0
        locked_rgs = set()
        for lk in locks:
            rg = lk.get("resourceGroup", "")
            if rg:
                locked_rgs.add(rg.lower())

        ratio = round(len(locked_rgs) / total_rgs, 4) if total_rgs else 0.0
        readonly_locks = sum(1 for l in locks if (l.get("lockLevel") or "").lower() == "readonly")
        delete_locks = sum(1 for l in locks if (l.get("lockLevel") or "").lower() in ("cannotdelete", "delete"))

        r.raw = {
            "query": "resource_locks",
            "lock_count": len(locks),
            "readonly_locks": readonly_locks,
            "delete_locks": delete_locks,
            "total_resource_groups": total_rgs,
            "locked_resource_groups": len(locked_rgs),
            "coverage": {"applicable": total_rgs, "compliant": len(locked_rgs), "ratio": ratio},
        }
    return r
