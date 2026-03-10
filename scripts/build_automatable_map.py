"""Build the complete automatable control map from the official ALZ checklist.

Reads every checklist item, determines if a signal can evaluate it,
and outputs a JSON map of GUID -> evaluation spec.

This replaces the manual approach of hand-writing evaluator classes."""
import json
import re
from alz.loader import load_alz_checklist

checklist = load_alz_checklist(force_refresh=False)
items = checklist.get("items", [])

# Complete mapping: resource type keywords -> signal_bus_name + evaluation approach
# Each entry: (signal_bus_name, check_type, check_detail)
SIGNAL_CHECKS = [
    # Resource Graph resource-type checks
    ("azure firewall", "resource_graph:azure_firewall", "presence_or_config",
     "Checks Azure Firewall presence and configuration"),
    ("application gateway", "resource_graph:app_gateways", "presence_or_config",
     "Checks Application Gateway with WAF status"),
    ("front door", "resource_graph:front_doors", "presence_or_config",
     "Checks Azure Front Door / CDN profile presence"),
    ("load balancer", "resource_graph:load_balancers", "presence_or_config",
     "Checks Load Balancer SKU and configuration"),
    ("bastion", "resource_graph:bastion_hosts", "presence_or_config",
     "Checks Azure Bastion host deployment"),
    ("expressroute", "resource_graph:vnet_gateways", "presence_or_config",
     "Checks ExpressRoute gateway presence and SKU"),
    ("vpn gateway", "resource_graph:vnet_gateways", "presence_or_config",
     "Checks VPN gateway presence and configuration"),
    ("route table", "resource_graph:route_tables", "presence_or_config",
     "Checks route table configuration"),
    ("private endpoint", "resource_graph:private_endpoints", "coverage",
     "Checks private endpoint coverage for PaaS"),
    ("private link", "resource_graph:private_endpoints", "coverage",
     "Checks Private Link usage"),
    ("private dns", "resource_graph:dns_zones", "presence_or_config",
     "Checks Private DNS zone configuration"),
    ("dns zone", "resource_graph:dns_zones", "presence_or_config",
     "Checks DNS zone presence"),
    ("nsg", "resource_graph:nsgs", "presence_or_config",
     "Checks NSG configuration and rules"),
    ("network security group", "resource_graph:nsgs", "presence_or_config",
     "Checks NSG configuration"),
    ("ddos", "resource_graph:vnets", "config_check",
     "Checks DDoS protection on VNets"),
    ("public ip", "resource_graph:public_ips", "presence_or_config",
     "Checks Public IP SKU and configuration"),
    ("vnet peering", "resource_graph:vnet_peerings", "config_check",
     "Checks VNet peering configuration"),
    ("virtual network", "resource_graph:vnets", "presence_or_config",
     "Checks VNet address space and configuration"),
    ("vnet", "resource_graph:vnets", "presence_or_config",
     "Checks VNet configuration"),
    ("subnet", "resource_graph:vnets", "config_check",
     "Checks subnet configuration"),
    ("service endpoint", "resource_graph:vnets", "config_check",
     "Checks service endpoint configuration on subnets"),
    ("flow log", "network:watcher_posture", "config_check",
     "Checks NSG flow log configuration"),
    ("traffic analytics", "network:watcher_posture", "config_check",
     "Checks Traffic Analytics enablement"),
    ("network watcher", "network:watcher_posture", "presence_or_config",
     "Checks Network Watcher deployment"),
    ("virtual wan", "resource_graph:vnets", "presence_or_config",
     "Checks Virtual WAN presence"),
    ("gateway subnet", "resource_graph:gateway_subnets", "config_check",
     "Checks GatewaySubnet prefix size"),
    ("availability zone", "resource_graph:load_balancers", "config_check",
     "Checks zone-redundant deployment"),
    ("zone-redundant", "resource_graph:load_balancers", "config_check",
     "Checks zone redundancy"),
    # Management group / governance
    ("management group", "arm:mg_hierarchy", "config_check",
     "Checks management group hierarchy"),
    ("policy", "policy:assignments", "presence_or_config",
     "Checks policy assignment and compliance"),
    ("compliance", "policy:compliance_summary", "coverage",
     "Checks policy compliance state"),
    # Security
    ("defender", "defender:pricings", "coverage",
     "Checks Defender for Cloud plan enablement"),
    ("secure score", "defender:secure_score", "threshold",
     "Checks Microsoft Secure Score"),
    ("diagnostic", "monitor:diag_coverage_sample", "coverage",
     "Checks diagnostic settings coverage"),
    ("log analytics", "monitor:workspace_topology", "presence_or_config",
     "Checks Log Analytics workspace configuration"),
    ("sentinel", "monitor:workspace_topology", "config_check",
     "Checks Microsoft Sentinel enablement"),
    ("azure monitor", "monitor:workspace_topology", "presence_or_config",
     "Checks Azure Monitor configuration"),
    # Identity
    ("conditional access", "identity:admin_ca_coverage", "presence_or_config",
     "Checks Conditional Access policies"),
    ("multi-factor", "identity:admin_ca_coverage", "config_check",
     "Checks MFA enforcement"),
    ("mfa", "identity:admin_ca_coverage", "config_check",
     "Checks MFA enforcement"),
    ("pim", "identity:pim_maturity", "config_check",
     "Checks PIM maturity"),
    ("privileged identity", "identity:pim_maturity", "config_check",
     "Checks PIM configuration"),
    ("break-glass", "identity:breakglass_validation", "presence_or_config",
     "Checks break-glass account presence"),
    ("emergency access", "identity:breakglass_validation", "presence_or_config",
     "Checks emergency access accounts"),
    ("rbac", "identity:rbac_hygiene", "config_check",
     "Checks RBAC configuration"),
    ("managed identit", "resource_graph:managed_identities", "presence_or_config",
     "Checks managed identity adoption"),
    ("service principal", "identity:sp_owner_risk", "config_check",
     "Checks service principal risk"),
    # Cost / Billing
    ("budget", "cost:management_posture", "presence_or_config",
     "Checks budget configuration"),
    ("cost management", "cost:management_posture", "presence_or_config",
     "Checks cost management setup"),
    ("cost report", "cost:management_posture", "presence_or_config",
     "Checks cost reporting"),
    # Resource posture
    ("storage account", "resource_graph:storage_posture", "coverage",
     "Checks storage account security posture"),
    ("key vault", "resource_graph:keyvault_posture", "coverage",
     "Checks Key Vault security posture"),
    ("aks", "resource_graph:aks_posture", "coverage",
     "Checks AKS cluster security posture"),
    ("container registr", "resource_graph:acr_posture", "coverage",
     "Checks Container Registry security posture"),
    ("backup", "resource_graph:backup_coverage", "coverage",
     "Checks backup coverage"),
    ("resource lock", "resource_graph:resource_locks", "presence_or_config",
     "Checks resource lock deployment"),
    ("tag", "resource_graph:tag_coverage", "coverage",
     "Checks tag coverage"),
    # Monitoring
    ("action group", "monitor:action_group_coverage", "presence_or_config",
     "Checks action group configuration"),
    ("alert", "monitor:alert_action_mapping", "presence_or_config",
     "Checks alert rule configuration"),
    ("update manager", "manage:update_manager", "presence_or_config",
     "Checks Update Manager configuration"),
    # Lighthouse
    ("lighthouse", "resource_graph:vnets", "presence_or_config",
     "Checks Azure Lighthouse configuration"),
    # Entra ID
    ("entra", "identity:entra_log_availability", "config_check",
     "Checks Entra ID log availability"),
    # IP addressing
    ("ip address", "resource_graph:vnets", "config_check",
     "Checks IP address configuration"),
]

# Known existing evaluator GUIDs (already have hand-written evaluators)
from control_packs.loader import load_pack
pack = load_pack("alz", "v1.0")
existing_guids = set(c.full_id for c in pack.controls.values())

# Process every checklist item
automatable = {}
manual_items = []

for item in items:
    guid = item.get("guid", "")
    if not guid:
        continue
    if guid in existing_guids:
        continue  # already covered
    
    text = (item.get("text", "") or "").lower()
    category = item.get("category", "")
    severity = item.get("severity", "Medium")
    
    # Find matching signal
    matched = None
    for keyword, signal, check_type, description in SIGNAL_CHECKS:
        if keyword in text:
            matched = {
                "signal": signal,
                "check_type": check_type,
                "matched_keyword": keyword,
                "description": description,
            }
            break
    
    if matched:
        automatable[guid] = {
            "guid": guid,
            "text": item.get("text", ""),
            "category": category,
            "severity": severity,
            "signal": matched["signal"],
            "check_type": matched["check_type"],
            "matched_keyword": matched["matched_keyword"],
        }
    else:
        manual_items.append({
            "guid": guid,
            "text": item.get("text", "")[:100],
            "category": category,
            "severity": severity,
        })

# Save the map
output = {
    "generated_from": "Azure/review-checklists ALZ checklist",
    "existing_evaluators": len(existing_guids),
    "new_automatable": len(automatable),
    "truly_manual": len(manual_items),
    "total_checklist": len(items),
    "potential_coverage_percent": round((len(existing_guids) + len(automatable)) / len(items) * 100, 1),
    "controls": automatable,
}

with open("control_packs/alz/v1.0/automatable_map.json", "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print(f"=== Checklist Automation Map ===")
print(f"Total checklist items:    {len(items)}")
print(f"Existing evaluators:      {len(existing_guids)}")
print(f"NEW automatable:          {len(automatable)}")
print(f"Truly manual:             {len(manual_items)}")
print(f"Potential coverage:       {len(existing_guids) + len(automatable)}/{len(items)} "
      f"({output['potential_coverage_percent']}%)")
print()

# Per category breakdown
from collections import Counter
by_cat = Counter()
for ctrl in automatable.values():
    by_cat[ctrl["category"]] += 1
print("NEW automatable by section:")
for cat, count in by_cat.most_common():
    print(f"  {count:3d}  {cat}")
