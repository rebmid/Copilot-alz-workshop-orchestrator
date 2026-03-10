"""Network topology signal providers — LB, gateways, Bastion, Front Door, App GW, DNS, peerings, tags, managed identities."""
from __future__ import annotations

from signals.types import SignalResult, SignalStatus
from signals.providers.resource_graph import _query_rg


def fetch_load_balancers(subscriptions: list[str]) -> SignalResult:
    """Load Balancers with SKU and backend pool info."""
    query = """
    Resources
    | where type =~ 'microsoft.network/loadbalancers'
    | extend skuName = tostring(sku.name),
             skuTier = tostring(sku.tier),
             backendPools = array_length(properties.backendAddressPools),
             frontendConfigs = array_length(properties.frontendIPConfigurations),
             zones = properties.frontendIPConfigurations[0].zones
    | project name, resourceGroup, location, id, skuName, skuTier,
              backendPools, frontendConfigs, zones
    """
    r = _query_rg(query, subscriptions)
    r.signal_name = "resource_graph:load_balancers"

    if r.status == SignalStatus.OK:
        items = r.items or []
        total = len(items)
        standard = sum(1 for lb in items if (lb.get("skuName") or "").lower() == "standard")
        zone_redundant = sum(1 for lb in items if lb.get("zones"))
        r.raw = {
            "count": total,
            "standard_count": standard,
            "zone_redundant_count": zone_redundant,
            "coverage": {"applicable": total, "compliant": standard, "ratio": round(standard / max(total, 1), 4)},
        }
    return r


def fetch_expressroute_gateways(subscriptions: list[str]) -> SignalResult:
    """ExpressRoute and VPN virtual network gateways."""
    query = """
    Resources
    | where type =~ 'microsoft.network/virtualnetworkgateways'
    | extend gatewayType = tostring(properties.gatewayType),
             skuName = tostring(properties.sku.name),
             skuTier = tostring(properties.sku.tier),
             activeActive = tostring(properties.activeActiveEnabled),
             vpnType = tostring(properties.vpnType),
             bgpEnabled = tostring(properties.enableBgp)
    | project name, resourceGroup, location, id, gatewayType,
              skuName, skuTier, activeActive, vpnType, bgpEnabled
    """
    r = _query_rg(query, subscriptions)
    r.signal_name = "resource_graph:vnet_gateways"

    if r.status == SignalStatus.OK:
        items = r.items or []
        er_gws = [g for g in items if (g.get("gatewayType") or "").lower() == "expressroute"]
        vpn_gws = [g for g in items if (g.get("gatewayType") or "").lower() == "vpn"]
        r.raw = {
            "count": len(items),
            "expressroute_count": len(er_gws),
            "vpn_count": len(vpn_gws),
            "er_gateways": er_gws,
            "vpn_gateways": vpn_gws,
        }
    return r


def fetch_bastion_hosts(subscriptions: list[str]) -> SignalResult:
    """Azure Bastion hosts."""
    query = """
    Resources
    | where type =~ 'microsoft.network/bastionhosts'
    | extend skuName = tostring(sku.name)
    | project name, resourceGroup, location, id, skuName
    """
    r = _query_rg(query, subscriptions)
    r.signal_name = "resource_graph:bastion_hosts"
    if r.status == SignalStatus.OK:
        r.raw = {"count": len(r.items or [])}
    return r


def fetch_front_doors(subscriptions: list[str]) -> SignalResult:
    """Azure Front Door and CDN profiles (AFD Standard/Premium)."""
    query = """
    Resources
    | where type =~ 'microsoft.cdn/profiles' or type =~ 'microsoft.network/frontdoors'
    | extend skuName = tostring(sku.name),
             wafPolicyId = tostring(properties.frontDoorId)
    | project name, resourceGroup, location, id, type, skuName
    """
    r = _query_rg(query, subscriptions)
    r.signal_name = "resource_graph:front_doors"
    if r.status == SignalStatus.OK:
        r.raw = {"count": len(r.items or [])}
    return r


def fetch_application_gateways(subscriptions: list[str]) -> SignalResult:
    """Application Gateways with WAF and SKU info."""
    query = """
    Resources
    | where type =~ 'microsoft.network/applicationgateways'
    | extend skuName = tostring(properties.sku.name),
             skuTier = tostring(properties.sku.tier),
             wafEnabled = tostring(properties.webApplicationFirewallConfiguration.enabled),
             firewallPolicyId = tostring(properties.firewallPolicy.id)
    | project name, resourceGroup, location, id,
              skuName, skuTier, wafEnabled, firewallPolicyId
    """
    r = _query_rg(query, subscriptions)
    r.signal_name = "resource_graph:app_gateways"

    if r.status == SignalStatus.OK:
        items = r.items or []
        total = len(items)
        waf_enabled = sum(1 for ag in items
                         if (ag.get("wafEnabled") or "").lower() in ("true", "1")
                         or ag.get("firewallPolicyId"))
        r.raw = {
            "count": total,
            "waf_enabled_count": waf_enabled,
            "coverage": {"applicable": total, "compliant": waf_enabled,
                         "ratio": round(waf_enabled / max(total, 1), 4)},
        }
    return r


def fetch_dns_zones(subscriptions: list[str]) -> SignalResult:
    """Azure DNS zones (public and private)."""
    query = """
    Resources
    | where type =~ 'microsoft.network/dnszones' or type =~ 'microsoft.network/privatednszones'
    | extend zoneType = case(type =~ 'microsoft.network/privatednszones', 'Private', 'Public'),
             recordCount = tostring(properties.numberOfRecordSets)
    | project name, resourceGroup, location, id, type, zoneType, recordCount
    """
    r = _query_rg(query, subscriptions)
    r.signal_name = "resource_graph:dns_zones"

    if r.status == SignalStatus.OK:
        items = r.items or []
        private = sum(1 for z in items if z.get("zoneType") == "Private")
        public = sum(1 for z in items if z.get("zoneType") == "Public")
        r.raw = {"count": len(items), "private_zones": private, "public_zones": public}
    return r


def fetch_vnet_peerings(subscriptions: list[str]) -> SignalResult:
    """VNet peering details — state, traffic forwarding, gateway transit."""
    query = """
    Resources
    | where type =~ 'microsoft.network/virtualnetworks'
    | mv-expand peering = properties.virtualNetworkPeerings
    | extend peeringName = tostring(peering.name),
             peeringState = tostring(peering.properties.peeringState),
             allowForwarded = tostring(peering.properties.allowForwardedTraffic),
             allowGatewayTransit = tostring(peering.properties.allowGatewayTransit),
             useRemoteGateways = tostring(peering.properties.useRemoteGateways),
             allowVnetAccess = tostring(peering.properties.allowVirtualNetworkAccess)
    | project vnetName=name, resourceGroup, location, id, peeringName,
              peeringState, allowForwarded, allowGatewayTransit,
              useRemoteGateways, allowVnetAccess
    """
    r = _query_rg(query, subscriptions)
    r.signal_name = "resource_graph:vnet_peerings"

    if r.status == SignalStatus.OK:
        items = r.items or []
        total = len(items)
        connected = sum(1 for p in items if (p.get("peeringState") or "").lower() == "connected")
        vnet_access = sum(1 for p in items if (p.get("allowVnetAccess") or "").lower() in ("true", "1"))
        r.raw = {
            "count": total,
            "connected_count": connected,
            "allow_vnet_access_count": vnet_access,
        }
    return r


def fetch_managed_identities(subscriptions: list[str]) -> SignalResult:
    """Count of resources using system-assigned or user-assigned managed identities."""
    query = """
    Resources
    | where isnotempty(identity)
    | extend identityType = tostring(identity.type)
    | summarize count() by identityType
    """
    r = _query_rg(query, subscriptions)
    r.signal_name = "resource_graph:managed_identities"

    if r.status == SignalStatus.OK:
        items = r.items or []
        total_with_identity = sum(item.get("count_", 0) for item in items)
        r.raw = {
            "resources_with_identity": total_with_identity,
            "identity_types": {item.get("identityType", ""): item.get("count_", 0) for item in items},
        }
    return r


def fetch_tag_coverage(subscriptions: list[str]) -> SignalResult:
    """Check tag coverage — resources with vs without tags."""
    query = """
    Resources
    | where type !~ 'microsoft.resources/subscriptions'
        and type !~ 'microsoft.resources/subscriptions/resourcegroups'
    | extend tagCount = bag_keys(tags)
    | extend hasAnyTag = array_length(tagCount) > 0
    | summarize total=count(), tagged=countif(hasAnyTag) by type
    | order by total desc
    | take 50
    """
    r = _query_rg(query, subscriptions)
    r.signal_name = "resource_graph:tag_coverage"

    if r.status == SignalStatus.OK:
        items = r.items or []
        total = sum(item.get("total", 0) for item in items)
        tagged = sum(item.get("tagged", 0) for item in items)
        r.raw = {
            "total_resources": total,
            "tagged_resources": tagged,
            "tag_coverage_percent": round(tagged / max(total, 1) * 100, 1),
            "coverage": {"applicable": total, "compliant": tagged,
                         "ratio": round(tagged / max(total, 1), 4)},
        }
    return r


def fetch_gateway_subnets(subscriptions: list[str]) -> SignalResult:
    """Check GatewaySubnet prefix sizes."""
    query = """
    Resources
    | where type =~ 'microsoft.network/virtualnetworks'
    | mv-expand subnet = properties.subnets
    | where tostring(subnet.name) == 'GatewaySubnet'
    | extend subnetPrefix = tostring(subnet.properties.addressPrefix),
             routeTableId = tostring(subnet.properties.routeTable.id)
    | project vnetName=name, resourceGroup, location, id, subnetPrefix, routeTableId
    """
    r = _query_rg(query, subscriptions)
    r.signal_name = "resource_graph:gateway_subnets"

    if r.status == SignalStatus.OK:
        items = r.items or []
        total = len(items)
        compliant = 0
        for item in items:
            prefix = item.get("subnetPrefix", "")
            # Extract CIDR suffix
            try:
                cidr = int(prefix.split("/")[1]) if "/" in prefix else 32
            except (ValueError, IndexError):
                cidr = 32
            # /27 or larger (smaller CIDR number) is compliant
            if cidr <= 27:
                compliant += 1
        r.raw = {
            "count": total,
            "compliant_count": compliant,
            "coverage": {"applicable": total, "compliant": compliant,
                         "ratio": round(compliant / max(total, 1), 4)},
        }
    return r
