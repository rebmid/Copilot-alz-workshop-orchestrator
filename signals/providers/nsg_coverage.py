"""NSG coverage signal provider — subnet-level NSG attachment + empty NSG anti-pattern."""
from __future__ import annotations

from signals.types import SignalResult, SignalStatus
from signals.providers.resource_graph import _query_rg


def fetch_nsg_coverage(subscriptions: list[str]) -> SignalResult:
    """Check which subnets have NSGs attached and flag empty NSGs."""
    # Subnets and their NSG status
    query = """
    Resources
    | where type =~ 'microsoft.network/virtualnetworks'
    | mv-expand subnet = properties.subnets
    | extend subnetName = tostring(subnet.name),
             nsgId      = tostring(subnet.properties.networkSecurityGroup.id),
             vnetName   = name
    | where subnetName !in~ ('GatewaySubnet', 'AzureFirewallSubnet', 'AzureBastionSubnet',
                              'AzureFirewallManagementSubnet', 'RouteServerSubnet')
    | project vnetName, subnetName, nsgId, vnetId=id
    """
    r = _query_rg(query, subscriptions)
    r.signal_name = "resource_graph:nsg_coverage"

    if r.status == SignalStatus.OK:
        subnets = r.items or []
        total = len(subnets)
        covered = sum(1 for s in subnets if s.get("nsgId"))
        uncovered = [
            {"vnet": s.get("vnetName"), "subnet": s.get("subnetName")}
            for s in subnets if not s.get("nsgId")
        ]

        # Empty NSG check
        nsg_query = """
        Resources
        | where type =~ 'microsoft.network/networksecuritygroups'
        | extend ruleCount = array_length(properties.securityRules)
        | where ruleCount == 0
        | project name, resourceGroup, id
        """
        nsg_r = _query_rg(nsg_query, subscriptions)
        empty_nsgs = nsg_r.items if nsg_r.status == SignalStatus.OK else []

        ratio = round(covered / total, 4) if total else 0.0
        r.raw = {
            "query": "nsg_coverage",
            "count": total,
            "coverage": {"applicable": total, "compliant": covered, "ratio": ratio},
            "uncovered_subnets": uncovered[:20],
            "empty_nsgs": empty_nsgs[:20],
            "empty_nsg_count": len(empty_nsgs),
        }
    return r
