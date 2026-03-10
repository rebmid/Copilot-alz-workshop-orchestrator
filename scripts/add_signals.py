"""Add new signal definitions to signals.json for the expanded evaluators."""
import json

SIGNALS_PATH = "control_packs/alz/v1.0/signals.json"

with open(SIGNALS_PATH, encoding="utf-8") as f:
    data = json.load(f)

new_signals = {
    "load_balancers": {
        "provider": "resource_graph",
        "query": "Resources | where type =~ 'microsoft.network/loadbalancers'",
        "signal_bus_name": "resource_graph:load_balancers",
        "description": "Load Balancers with SKU, backend pools, and zone redundancy",
        "preflight_probe": "resource_graph",
    },
    "vnet_gateways": {
        "provider": "resource_graph",
        "query": "Resources | where type =~ 'microsoft.network/virtualnetworkgateways'",
        "signal_bus_name": "resource_graph:vnet_gateways",
        "description": "ExpressRoute and VPN virtual network gateways",
        "preflight_probe": "resource_graph",
    },
    "bastion_hosts": {
        "provider": "resource_graph",
        "query": "Resources | where type =~ 'microsoft.network/bastionhosts'",
        "signal_bus_name": "resource_graph:bastion_hosts",
        "description": "Azure Bastion hosts for secure VM access",
        "preflight_probe": "resource_graph",
    },
    "front_doors": {
        "provider": "resource_graph",
        "query": "Resources | where type =~ 'microsoft.cdn/profiles' or type =~ 'microsoft.network/frontdoors'",
        "signal_bus_name": "resource_graph:front_doors",
        "description": "Azure Front Door and CDN profiles for global HTTP/S protection",
        "preflight_probe": "resource_graph",
    },
    "app_gateways": {
        "provider": "resource_graph",
        "query": "Resources | where type =~ 'microsoft.network/applicationgateways'",
        "signal_bus_name": "resource_graph:app_gateways",
        "description": "Application Gateways with WAF and SKU info",
        "preflight_probe": "resource_graph",
    },
    "dns_zones": {
        "provider": "resource_graph",
        "query": "Resources | where type =~ 'microsoft.network/dnszones' or type =~ 'microsoft.network/privatednszones'",
        "signal_bus_name": "resource_graph:dns_zones",
        "description": "Azure DNS zones (public and private)",
        "preflight_probe": "resource_graph",
    },
    "vnet_peerings": {
        "provider": "resource_graph",
        "query": "VNet peering details extracted from virtual network properties",
        "signal_bus_name": "resource_graph:vnet_peerings",
        "description": "VNet peering state, traffic forwarding, and gateway transit settings",
        "preflight_probe": "resource_graph",
    },
    "managed_identities": {
        "provider": "resource_graph",
        "query": "Resources with system-assigned or user-assigned managed identities",
        "signal_bus_name": "resource_graph:managed_identities",
        "description": "Count of resources using managed identities for authentication",
        "preflight_probe": "resource_graph",
    },
    "tag_coverage": {
        "provider": "resource_graph",
        "query": "Tag coverage analysis across all resource types",
        "signal_bus_name": "resource_graph:tag_coverage",
        "description": "Tag coverage percentage — resources with vs without tags",
        "preflight_probe": "resource_graph",
    },
    "gateway_subnets": {
        "provider": "resource_graph",
        "query": "GatewaySubnet prefix sizes from virtual network subnet properties",
        "signal_bus_name": "resource_graph:gateway_subnets",
        "description": "GatewaySubnet prefix sizes for gateway subnet compliance",
        "preflight_probe": "resource_graph",
    },
}

data["signals"].update(new_signals)

with open(SIGNALS_PATH, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print(f"Updated signals.json: {len(data['signals'])} signals")
