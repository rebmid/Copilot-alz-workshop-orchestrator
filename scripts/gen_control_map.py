"""Generate the full control map for ALL automatable checklist items.
Outputs a Python dict mapping GUID -> evaluation config that the data-driven evaluator will consume."""
import json
from alz.loader import load_alz_checklist
from control_packs.loader import load_pack

checklist = load_alz_checklist(force_refresh=False)
items = checklist.get("items", [])
pack = load_pack("alz", "v1.0")
pack_guids = set(c.full_id for c in pack.controls.values())

# Signal mapping: keyword in text -> (signal_bus_name, check_type)
# check_type: "presence" = resource exists, "config" = check property,
#             "count" = check count threshold, "coverage" = check ratio
KEYWORD_TO_SIGNAL = {
    "azure firewall": "resource_graph:azure_firewall",
    "application gateway": "resource_graph:app_gateways",
    "front door": "resource_graph:front_doors",
    "load balancer": "resource_graph:load_balancers",
    "bastion": "resource_graph:bastion_hosts",
    "expressroute": "resource_graph:vnet_gateways",
    "vpn gateway": "resource_graph:vnet_gateways",
    "route table": "resource_graph:route_tables",
    "route server": "resource_graph:vnet_gateways",
    "private endpoint": "resource_graph:private_endpoints",
    "private link": "resource_graph:private_endpoints",
    "private dns": "resource_graph:dns_zones",
    "dns zone": "resource_graph:dns_zones",
    "nsg": "resource_graph:nsgs",
    "ddos": "resource_graph:vnets",
    "public ip": "resource_graph:public_ips",
    "vnet peering": "resource_graph:vnet_peerings",
    "virtual network": "resource_graph:vnets",
    "vnet": "resource_graph:vnets",
    "subnet": "resource_graph:vnets",
    "service endpoint": "resource_graph:vnets",
    "flow log": "network:watcher_posture",
    "traffic analytics": "network:watcher_posture",
    "network watcher": "network:watcher_posture",
    "virtual wan": "resource_graph:vnets",
    "gateway subnet": "resource_graph:gateway_subnets",
    "firewall subnet": "resource_graph:vnets",
    "management group": "arm:mg_hierarchy",
    "policy": "policy:assignments",
    "compliance": "policy:compliance_summary",
    "defender": "defender:pricings",
    "secure score": "defender:secure_score",
    "diagnostic": "monitor:diag_coverage_sample",
    "log analytics": "monitor:workspace_topology",
    "azure monitor": "monitor:workspace_topology",
    "conditional access": "identity:admin_ca_coverage",
    "pim": "identity:pim_maturity",
    "rbac": "identity:rbac_hygiene",
    "managed identit": "resource_graph:managed_identities",
    "budget": "cost:management_posture",
    "cost management": "cost:management_posture",
    "tag": "resource_graph:tag_coverage",
    "alert": "monitor:alert_action_mapping",
    "action group": "monitor:action_group_coverage",
    "sentinel": "monitor:workspace_topology",
    "lighthouse": "resource_graph:vnets",  # placeholder
    "availability zone": "resource_graph:load_balancers",
    "zone-redundant": "resource_graph:load_balancers",
    "storage account": "resource_graph:vnets",  # placeholder for storage RG
    "key vault": "resource_graph:vnets",  # placeholder
    "backup": "resource_graph:vnets",  # placeholder
    "resource lock": "resource_graph:vnets",  # placeholder
    "ip address": "resource_graph:vnets",
    "waf": "resource_graph:app_gateways",
    "idps": "resource_graph:azure_firewall",
    "threat intelligence": "resource_graph:azure_firewall",
    "connection monitor": "network:watcher_posture",
    "update manager": "resource_graph:vnets",
    "vm extension": "resource_graph:vnets",
    "site recovery": "resource_graph:vnets",
}

# Process all items
automatable = []
for item in items:
    guid = item.get("guid", "")
    if not guid or guid in pack_guids:
        continue

    text = (item.get("text", "") or "").lower()
    category = item.get("category", "")
    severity = item.get("severity", "Medium")

    # Find matching signal
    matched_signal = None
    for keyword, signal in KEYWORD_TO_SIGNAL.items():
        if keyword in text:
            matched_signal = signal
            break

    if matched_signal:
        # Generate short key (first 8 chars of GUID)
        short_key = guid[:8]
        automatable.append({
            "short_key": short_key,
            "guid": guid,
            "signal": matched_signal,
            "category": category,
            "severity": severity,
            "text": item.get("text", "")[:120],
        })

print(f"Total automatable (not yet in pack): {len(automatable)}")

# Group by category
by_cat: dict[str, int] = {}
by_signal: dict[str, int] = {}
for a in automatable:
    by_cat[a["category"]] = by_cat.get(a["category"], 0) + 1
    by_signal[a["signal"]] = by_signal.get(a["signal"], 0) + 1

print("\nBy category:")
for cat, n in sorted(by_cat.items(), key=lambda x: -x[1]):
    print(f"  {n:3d}  {cat}")

print("\nBy signal:")
for sig, n in sorted(by_signal.items(), key=lambda x: -x[1]):
    print(f"  {n:3d}  {sig}")

# Output as JSON for the evaluator registration
output = {a["short_key"]: a for a in automatable}
with open("scripts/automatable_controls.json", "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)
print(f"\nWrote {len(output)} controls to scripts/automatable_controls.json")
