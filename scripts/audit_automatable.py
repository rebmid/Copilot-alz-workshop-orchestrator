"""Audit: systematically identify ALL automatable controls from the official ALZ checklist
by matching checklist item text against available Resource Graph resource types and signals."""
import json
import re
from alz.loader import load_alz_checklist
from control_packs.loader import load_pack
from signals.registry import SIGNAL_PROVIDERS

checklist = load_alz_checklist(force_refresh=False)
items = checklist.get("items", [])
pack = load_pack("alz", "v1.0")
pack_guids = set(c.full_id for c in pack.controls.values())

# Resource types and keywords we CAN query via Resource Graph or existing signals
AUTOMATABLE_PATTERNS = {
    # Resource types queryable via Resource Graph
    "load balancer": "resource_graph:load_balancers",
    "azure firewall": "resource_graph:azure_firewall",
    "virtual network": "resource_graph:vnets",
    "vnet": "resource_graph:vnets",
    "public ip": "resource_graph:public_ips",
    "nsg": "resource_graph:nsgs",
    "route table": "resource_graph:route_tables",
    "bastion": "resource_graph:bastion_hosts",
    "front door": "resource_graph:front_doors",
    "application gateway": "resource_graph:app_gateways",
    "dns": "resource_graph:dns_zones",
    "private dns": "resource_graph:dns_zones",
    "vnet peering": "resource_graph:vnet_peerings",
    "gateway subnet": "resource_graph:gateway_subnets",
    "expressroute": "resource_graph:vnet_gateways",
    "vpn gateway": "resource_graph:vnet_gateways",
    "managed identit": "resource_graph:managed_identities",
    "tag": "resource_graph:tag_coverage",
    "storage account": "resource_graph:storage_posture",
    "key vault": "resource_graph:keyvault_posture",
    "private endpoint": "resource_graph:private_endpoints",
    "aks": "resource_graph:aks_posture",
    "container registr": "resource_graph:acr_posture",
    "backup": "resource_graph:backup_coverage",
    "resource lock": "resource_graph:resource_locks",
    # Existing non-RG signals
    "management group": "arm:mg_hierarchy",
    "policy": "policy:assignments",
    "compliance": "policy:compliance_summary",
    "defender": "defender:pricings",
    "secure score": "defender:secure_score",
    "diagnostic": "monitor:diag_coverage_sample",
    "log analytics": "monitor:workspace_topology",
    "conditional access": "identity:admin_ca_coverage",
    "pim": "identity:pim_maturity",
    "break.glass|emergency access": "identity:breakglass_validation",
    "rbac": "identity:rbac_hygiene",
    "budget": "cost:management_posture",
    "network watcher": "network:watcher_posture",
    "flow log": "network:watcher_posture",
    "ddos": "resource_graph:vnets",
    "availability zone": "resource_graph:load_balancers",
    "sentinel": "monitor:workspace_topology",
    # New queryable RG types
    "sql server": "NEW:resource_graph",
    "app service": "NEW:resource_graph",
    "virtual machine": "NEW:resource_graph",
    "vm": "NEW:resource_graph",
    "service endpoint": "NEW:resource_graph",
    "azure monitor": "monitor:workspace_topology",
    "action group": "monitor:action_group_coverage",
    "alert": "monitor:alert_action_mapping",
    "cost management": "cost:management_posture",
    "ip address": "resource_graph:vnets",
    "subnet": "resource_graph:vnets",
    "waf": "resource_graph:app_gateways",
    "lighthouse": "NEW:resource_graph",
}

# Check each checklist item
already_covered = []
can_automate = []
truly_manual = []

for item in items:
    guid = item.get("guid", "")
    text = (item.get("text", "") or "").lower()
    sev = item.get("severity", "")
    category = item.get("category", "")
    
    if guid in pack_guids:
        already_covered.append(item)
        continue
    
    # Check if any pattern matches
    matched_signal = None
    for pattern, signal in AUTOMATABLE_PATTERNS.items():
        for p in pattern.split("|"):
            if p.lower() in text:
                matched_signal = signal
                break
        if matched_signal:
            break
    
    if matched_signal:
        can_automate.append((item, matched_signal))
    else:
        truly_manual.append(item)

print(f"=== ALZ Checklist Automation Audit ===")
print(f"Total checklist items: {len(items)}")
print(f"Already evaluated:     {len(already_covered)} ({len(already_covered)*100//len(items)}%)")
print(f"CAN automate (signal): {len(can_automate)}")
print(f"Truly manual:          {len(truly_manual)}")
print()

# Group can-automate by category
by_category: dict[str, list] = {}
for item, signal in can_automate:
    cat = item.get("category", "Unknown")
    by_category.setdefault(cat, []).append((item, signal))

for cat in sorted(by_category.keys()):
    entries = by_category[cat]
    print(f"\n--- {cat} ({len(entries)} automatable) ---")
    for item, signal in entries:
        sev = item.get("severity", "")
        text = item.get("text", "")[:90]
        guid = item.get("guid", "")[:8]
        print(f"  [{sev:6s}] {guid} {signal:35s} {text}")
