"""Detailed signal-capability audit for EVERY Network Topology & Connectivity checklist item.
For each item, determine: can our signals see it, and what specific query would check it."""
import json
from alz.loader import load_alz_checklist
from control_packs.loader import load_pack

checklist = load_alz_checklist(force_refresh=False)
items = checklist.get("items", [])
pack = load_pack("alz", "v1.0")
pack_guids = set(c.full_id for c in pack.controls.values())

net = [i for i in items if "network" in (i.get("category", "") or "").lower()
       and "connectivity" in (i.get("category", "") or "").lower()]

# Detailed signal mapping per resource type / concept
# Key: substring match in text → (signal_available, RG_query_approach)
SIGNAL_MAP = {
    # Resource presence checks (ResourceGraph: type query)
    "azure firewall": ("YES", "RG: microsoft.network/azurefirewalls — sku, policy, zones, threatIntelMode, idpsMode"),
    "application gateway": ("YES", "RG: microsoft.network/applicationgateways — sku, wafEnabled, firewallPolicy"),
    "front door": ("YES", "RG: microsoft.cdn/profiles — sku, wafPolicy"),
    "load balancer": ("YES", "RG: microsoft.network/loadbalancers — sku, zones, backendPools"),
    "bastion": ("YES", "RG: microsoft.network/bastionhosts — sku, subnet"),
    "expressroute": ("YES", "RG: microsoft.network/virtualnetworkgateways where gatewayType=ExpressRoute — sku, activeActive"),
    "vpn gateway": ("YES", "RG: microsoft.network/virtualnetworkgateways where gatewayType=Vpn — sku, activeActive, bgp"),
    "route table": ("YES", "RG: microsoft.network/routetables — routes count, subnet associations"),
    "route server": ("YES", "RG: microsoft.network/virtualHubs where sku.name=RouteServerStandard"),
    "private endpoint": ("YES", "RG: microsoft.network/privateendpoints — count, linked resources"),
    "private link": ("YES", "RG: microsoft.network/privateendpoints — same as above"),
    "private dns": ("YES", "RG: microsoft.network/privatednszones — count, vnet links, auto-registration"),
    "dns zone": ("YES", "RG: microsoft.network/dnszones — record count"),
    "dns proxy": ("PARTIAL", "RG: firewall properties.dnsSettings.enableProxy — extend firewall query"),
    "nsg": ("YES", "RG: microsoft.network/networksecuritygroups — rules count, subnet association"),
    "ddos": ("YES", "RG: VNet properties.enableDdosProtection — boolean per VNet"),
    "public ip": ("YES", "RG: microsoft.network/publicipaddresses — sku, zones, allocation"),
    "vnet peering": ("YES", "RG: VNet properties.virtualNetworkPeerings — state, allowForwarded, allowGateway"),
    "virtual network": ("YES", "RG: microsoft.network/virtualnetworks — addressSpace, subnets, peerings"),
    "subnet": ("YES", "RG: VNet subnets — addressPrefix, serviceEndpoints, NSG, routeTable"),
    "service endpoint": ("YES", "RG: VNet subnet properties.serviceEndpoints — list per subnet"),
    "flow log": ("YES", "RG: microsoft.network/networkwatchers/flowlogs — enabled, version, trafficAnalytics"),
    "traffic analytics": ("YES", "RG: flowlog properties.flowAnalyticsConfiguration.enabled"),
    "network watcher": ("YES", "RG: microsoft.network/networkwatchers — enabled per region"),
    "virtual wan": ("YES", "RG: microsoft.network/virtualwans + microsoft.network/virtualhubs"),
    "secured hub": ("YES", "RG: virtualHubs where securityPartnerProvider or azureFirewall present"),
    # Config checks (need extended RG projections)
    "ip address space": ("YES", "RG: VNet addressSpace.addressPrefixes — compare for overlaps"),
    "gateway subnet": ("YES", "RG: VNet subnets where name=GatewaySubnet — addressPrefix CIDR check"),
    "firewall subnet": ("YES", "RG: VNet subnets where name=AzureFirewallSubnet — addressPrefix CIDR check"),
    "diagnostic": ("YES", "RG: diagnosticSettings on resources — or monitor:diag_coverage_sample"),
    "availability zone": ("YES", "RG: resource zones property — LBs, Firewalls, Gateways, IPs"),
    "zone-redundant": ("YES", "RG: same as availability zone check"),
    "bgp": ("PARTIAL", "RG: gateway properties.enableBgp — boolean"),
    "waf": ("YES", "RG: appGateway properties.webApplicationFirewallConfiguration + firewallPolicy"),
    "macsec": ("NO", "ExpressRoute Direct physical link config — not in Resource Graph"),
    "bfd": ("NO", "Customer/provider edge routing config — not in Azure"),
    "ipsec": ("PARTIAL", "RG: VPN connection properties — but requires connection resource, not just gateway"),
    "web categories": ("NO", "Firewall policy rule detail — too granular for posture check"),
    "tls inspection": ("PARTIAL", "RG: firewall policy properties.transportSecurity — extend query"),
    "idps": ("YES", "RG: firewall policy properties.intrusionDetection.mode"),
    "threat intelligence": ("YES", "RG: firewall policy properties.threatIntelMode"),
    "snat": ("NO", "Runtime metric — not a config check"),
    "connection monitor": ("YES", "RG: microsoft.network/connectionMonitors — count"),
    "azure monitor": ("YES", "monitor:workspace_topology — Log Analytics workspace presence"),
    # Organizational/process (not queryable)
    "partner vendor": ("NO", "Vendor relationship — organizational"),
    "document": ("NO", "Documentation requirement — process"),
    "plan for": ("NO", "Planning requirement — process"),
    "breaking change": ("NO", "External roadmap awareness"),
}

print(f"=== Network Topology & Connectivity: Signal Capability Audit ===")
print(f"Total items: {len(net)}\n")

yes_count = 0
partial_count = 0
no_count = 0
already_count = 0

for item in net:
    guid = item.get("guid", "")
    sev = item.get("severity", "")
    text = item.get("text", "") or ""
    text_lower = text.lower()

    if guid in pack_guids:
        already_count += 1
        continue

    # Find best match
    best_match = None
    best_capability = "NO"
    best_detail = "No matching signal found"

    for pattern, (capability, detail) in SIGNAL_MAP.items():
        if pattern in text_lower:
            if capability == "YES" and best_capability != "YES":
                best_capability = capability
                best_detail = detail
                best_match = pattern
            elif capability == "PARTIAL" and best_capability == "NO":
                best_capability = capability
                best_detail = detail
                best_match = pattern

    icon = {"YES": "+", "PARTIAL": "~", "NO": "-"}[best_capability]
    if best_capability == "YES":
        yes_count += 1
    elif best_capability == "PARTIAL":
        partial_count += 1
    else:
        no_count += 1

    print(f"  [{icon}] [{sev:6s}] {guid[:8]} {best_capability:7s} {text[:95]}")
    if best_capability != "NO":
        print(f"           Signal: {best_detail}")

print(f"\n=== SUMMARY ===")
print(f"Already evaluated: {already_count}")
print(f"CAN automate (YES): {yes_count}")
print(f"Partially automatable: {partial_count}")
print(f"Truly manual (NO): {no_count}")
print(f"Potential coverage: {already_count + yes_count + partial_count}/{len(net)} "
      f"({(already_count + yes_count + partial_count)*100//len(net)}%)")
