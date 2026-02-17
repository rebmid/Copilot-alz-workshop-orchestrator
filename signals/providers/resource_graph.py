"""Resource Graph signal providers — VNets, firewalls, public IPs, route tables."""
from __future__ import annotations

import time
from typing import Any

from signals.types import SignalResult, SignalStatus


def _query_rg(query: str, subscriptions: list[str], *, top: int = 1000) -> SignalResult:
    """Execute a Resource Graph query and return a SignalResult.

    Paginates automatically if the result set exceeds *top* rows.
    """
    from azure.mgmt.resourcegraph import ResourceGraphClient
    from azure.mgmt.resourcegraph.models import QueryRequest, QueryRequestOptions
    from collectors.azure_client import get_shared_credential

    start = time.perf_counter_ns()
    try:
        credential = get_shared_credential()
        client = ResourceGraphClient(credential)
        all_items: list = []
        skip_token: str | None = None

        while True:
            options = QueryRequestOptions(
                result_format="objectArray",
                top=top,
            )
            if skip_token:
                options.skip_token = skip_token

            request = QueryRequest(
                subscriptions=subscriptions,
                query=query,
                options=options,
            )
            response = client.resources(request)
            page = response.data if isinstance(response.data, list) else []  # type: ignore[assignment]
            all_items.extend(page)

            skip_token = getattr(response, "skip_token", None)
            if not skip_token or not page:
                break

        ms = (time.perf_counter_ns() - start) // 1_000_000
        return SignalResult(
            signal_name="",  # caller sets this
            status=SignalStatus.OK,
            items=all_items,
            raw={"query": query, "count": len(all_items), "pages": 1 + (len(all_items) // top if all_items else 0)},
            duration_ms=ms,
        )
    except Exception as e:
        ms = (time.perf_counter_ns() - start) // 1_000_000
        return SignalResult(
            signal_name="",
            status=SignalStatus.ERROR,
            error_msg=str(e),
            duration_ms=ms,
        )


def fetch_azure_firewalls(subscriptions: list[str]) -> SignalResult:
    query = """
    Resources
    | where type =~ 'microsoft.network/azurefirewalls'
    | project name, resourceGroup, location, id,
              sku=properties.sku.name,
              policyId=properties.firewallPolicy.id
    """
    r = _query_rg(query, subscriptions)
    r.signal_name = "resource_graph:azure_firewall"
    return r


def fetch_vnets(subscriptions: list[str]) -> SignalResult:
    query = """
    Resources
    | where type =~ 'microsoft.network/virtualnetworks'
    | project name, resourceGroup, location, id,
              addressSpace=properties.addressSpace.addressPrefixes,
              subnets=array_length(properties.subnets),
              peerings=array_length(properties.virtualNetworkPeerings),
              ddosProtectionPlan=properties.enableDdosProtection
    """
    r = _query_rg(query, subscriptions)
    r.signal_name = "resource_graph:vnets"
    return r


def fetch_public_ips(subscriptions: list[str]) -> SignalResult:
    query = """
    Resources
    | where type =~ 'microsoft.network/publicipaddresses'
    | project name, resourceGroup, location, id,
              sku=sku.name,
              allocationMethod=properties.publicIPAllocationMethod,
              associatedTo=properties.ipConfiguration.id
    """
    r = _query_rg(query, subscriptions)
    r.signal_name = "resource_graph:public_ips"
    return r


def fetch_route_tables(subscriptions: list[str]) -> SignalResult:
    query = """
    Resources
    | where type =~ 'microsoft.network/routetables'
    | project name, resourceGroup, location, id,
              routes=array_length(properties.routes),
              subnets=array_length(properties.subnets)
    """
    r = _query_rg(query, subscriptions)
    r.signal_name = "resource_graph:route_tables"
    return r


def fetch_nsg_list(subscriptions: list[str]) -> SignalResult:
    query = """
    Resources
    | where type =~ 'microsoft.network/networksecuritygroups'
    | project name, resourceGroup, location, id,
              rules=array_length(properties.securityRules)
    """
    r = _query_rg(query, subscriptions)
    r.signal_name = "resource_graph:nsgs"
    return r
