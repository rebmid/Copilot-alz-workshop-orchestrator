"""Private endpoint coverage signal provider."""
from __future__ import annotations

from signals.types import SignalResult, SignalStatus
from signals.providers.resource_graph import _query_rg


def fetch_private_endpoint_coverage(subscriptions: list[str]) -> SignalResult:
    """Inventory private endpoints and PaaS services that should use them."""
    query = """
    Resources
    | where type =~ 'microsoft.network/privateendpoints'
    | extend targetId = tostring(properties.privateLinkServiceConnections[0].properties.privateLinkServiceId),
             status   = tostring(properties.privateLinkServiceConnections[0].properties.privateLinkServiceConnectionState.status)
    | project name, resourceGroup, location, id, targetId, status
    """
    r = _query_rg(query, subscriptions)
    r.signal_name = "resource_graph:private_endpoints"

    if r.status == SignalStatus.OK:
        pe_items = r.items or []
        pe_targets = {(pe.get("targetId") or "").lower() for pe in pe_items}

        # Count PaaS resources that should ideally have PEs
        paas_query = """
        Resources
        | where type in~ (
            'microsoft.storage/storageaccounts',
            'microsoft.keyvault/vaults',
            'microsoft.sql/servers',
            'microsoft.documentdb/databaseaccounts',
            'microsoft.web/sites',
            'microsoft.containerregistry/registries',
            'microsoft.cognitiveservices/accounts',
            'microsoft.search/searchservices',
            'microsoft.eventhub/namespaces',
            'microsoft.servicebus/namespaces'
        )
        | project name, type, id
        """
        paas_r = _query_rg(paas_query, subscriptions)
        paas_items = paas_r.items if paas_r.status == SignalStatus.OK else []
        total_paas = len(paas_items)

        # See which PaaS resources have a PE
        covered = sum(1 for p in paas_items if p.get("id", "").lower() in pe_targets)
        ratio = round(covered / total_paas, 4) if total_paas else 0.0

        r.raw = {
            "query": "private_endpoint_coverage",
            "private_endpoint_count": len(pe_items),
            "paas_resource_count": total_paas,
            "coverage": {"applicable": total_paas, "compliant": covered, "ratio": ratio},
        }
    return r
