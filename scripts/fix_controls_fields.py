"""One-shot script to fix all missing fields in controls.json for new evaluators."""
import json, sys

CONTROLS_PATH = "control_packs/alz/v1.0/controls.json"

# Complete definitions for all 38 new controls
# Each has: sub_area, waf_pillar, control_type, required_signals, caf_guidance, caf_url
FIXES = {
    # ── Network Topology ─────────────────────────────────────────
    "std-lb-s": {
        "sub_area": "Load Balancing",
        "waf_pillar": "Reliability",
        "control_type": "ALZ",
        "required_signals": ["load_balancers"],
        "caf_guidance": "Define an Azure network topology",
        "caf_url": "https://learn.microsoft.com/azure/cloud-adoption-framework/ready/azure-best-practices/define-an-azure-network-topology",
    },
    "lb-backe": {
        "sub_area": "Load Balancing",
        "waf_pillar": "Reliability",
        "control_type": "ALZ",
        "required_signals": ["load_balancers"],
        "caf_guidance": "Define an Azure network topology",
        "caf_url": "https://learn.microsoft.com/azure/cloud-adoption-framework/ready/azure-best-practices/define-an-azure-network-topology",
    },
    "vnet-pee": {
        "sub_area": "Connectivity",
        "waf_pillar": "Reliability",
        "control_type": "ALZ",
        "required_signals": ["vnet_peerings"],
        "caf_guidance": "Define an Azure network topology",
        "caf_url": "https://learn.microsoft.com/azure/cloud-adoption-framework/ready/azure-best-practices/define-an-azure-network-topology",
    },
    "bastion-": {
        "sub_area": "Secure Access",
        "waf_pillar": "Security",
        "control_type": "ALZ",
        "required_signals": ["bastion_hosts"],
        "caf_guidance": "Plan for inbound and outbound internet connectivity",
        "caf_url": "https://learn.microsoft.com/azure/cloud-adoption-framework/ready/azure-best-practices/plan-for-inbound-and-outbound-internet-connectivity",
    },
    "frontdoo": {
        "sub_area": "Internet Connectivity",
        "waf_pillar": "Security",
        "control_type": "ALZ",
        "required_signals": ["front_doors"],
        "caf_guidance": "Plan for inbound and outbound internet connectivity",
        "caf_url": "https://learn.microsoft.com/azure/cloud-adoption-framework/ready/azure-best-practices/plan-for-inbound-and-outbound-internet-connectivity",
    },
    "privdns-": {
        "sub_area": "DNS",
        "waf_pillar": "Operational Excellence",
        "control_type": "ALZ",
        "required_signals": ["dns_zones"],
        "caf_guidance": "Private Link and DNS integration at scale",
        "caf_url": "https://learn.microsoft.com/azure/cloud-adoption-framework/ready/azure-best-practices/private-link-and-dns-integration-at-scale",
    },
    "dns-auto": {
        "sub_area": "DNS",
        "waf_pillar": "Operational Excellence",
        "control_type": "ALZ",
        "required_signals": ["dns_zones"],
        "caf_guidance": "Private Link and DNS integration at scale",
        "caf_url": "https://learn.microsoft.com/azure/cloud-adoption-framework/ready/azure-best-practices/private-link-and-dns-integration-at-scale",
    },
    "gw-subne": {
        "sub_area": "Connectivity",
        "waf_pillar": "Reliability",
        "control_type": "ALZ",
        "required_signals": ["gateway_subnets"],
        "caf_guidance": "Define an Azure network topology",
        "caf_url": "https://learn.microsoft.com/azure/cloud-adoption-framework/ready/azure-best-practices/define-an-azure-network-topology",
    },
    "ddos-log": {
        "sub_area": "Security",
        "waf_pillar": "Security",
        "control_type": "ALZ",
        "required_signals": ["vnets", "diagnostic_settings_sample"],
        "caf_guidance": "Plan for traffic inspection",
        "caf_url": "https://learn.microsoft.com/azure/cloud-adoption-framework/ready/azure-best-practices/plan-for-traffic-inspection",
    },
    "shared-n": {
        "sub_area": "Topology",
        "waf_pillar": "Reliability",
        "control_type": "ALZ",
        "required_signals": ["vnet_gateways", "azure_firewalls"],
        "caf_guidance": "Define an Azure network topology",
        "caf_url": "https://learn.microsoft.com/azure/cloud-adoption-framework/ready/azure-best-practices/define-an-azure-network-topology",
    },
    "fw-diag-": {
        "sub_area": "Security",
        "waf_pillar": "Security",
        "control_type": "ALZ",
        "required_signals": ["azure_firewalls", "diagnostic_settings_sample"],
        "caf_guidance": "Plan for traffic inspection",
        "caf_url": "https://learn.microsoft.com/azure/cloud-adoption-framework/ready/azure-best-practices/plan-for-traffic-inspection",
    },
    "fw-subne": {
        "sub_area": "Firewall",
        "waf_pillar": "Reliability",
        "control_type": "ALZ",
        "required_signals": ["vnets"],
        "caf_guidance": "Plan for traffic inspection",
        "caf_url": "https://learn.microsoft.com/azure/cloud-adoption-framework/ready/azure-best-practices/plan-for-traffic-inspection",
    },
    "ddos-fw-": {
        "sub_area": "Security",
        "waf_pillar": "Security",
        "control_type": "ALZ",
        "required_signals": ["vnets", "azure_firewalls"],
        "caf_guidance": "Plan for traffic inspection",
        "caf_url": "https://learn.microsoft.com/azure/cloud-adoption-framework/ready/azure-best-practices/plan-for-traffic-inspection",
    },
    "fw-premi": {
        "sub_area": "Firewall",
        "waf_pillar": "Security",
        "control_type": "ALZ",
        "required_signals": ["azure_firewalls"],
        "caf_guidance": "Plan for traffic inspection",
        "caf_url": "https://learn.microsoft.com/azure/cloud-adoption-framework/ready/azure-best-practices/plan-for-traffic-inspection",
    },
    "fw-az-de": {
        "sub_area": "Firewall",
        "waf_pillar": "Reliability",
        "control_type": "ALZ",
        "required_signals": ["azure_firewalls"],
        "caf_guidance": "Plan for traffic inspection",
        "caf_url": "https://learn.microsoft.com/azure/cloud-adoption-framework/ready/azure-best-practices/plan-for-traffic-inspection",
    },
    "onprem-p": {
        "sub_area": "Private Connectivity",
        "waf_pillar": "Security",
        "control_type": "ALZ",
        "required_signals": ["private_endpoints", "vnet_gateways"],
        "caf_guidance": "Private Link and DNS integration at scale",
        "caf_url": "https://learn.microsoft.com/azure/cloud-adoption-framework/ready/azure-best-practices/private-link-and-dns-integration-at-scale",
    },
    "appgw-wa": {
        "sub_area": "Internet Connectivity",
        "waf_pillar": "Security",
        "control_type": "ALZ",
        "required_signals": ["app_gateways"],
        "caf_guidance": "Plan for inbound and outbound internet connectivity",
        "caf_url": "https://learn.microsoft.com/azure/cloud-adoption-framework/ready/azure-best-practices/plan-for-inbound-and-outbound-internet-connectivity",
    },
    "er-prima": {
        "sub_area": "Connectivity",
        "waf_pillar": "Reliability",
        "control_type": "ALZ",
        "required_signals": ["vnet_gateways"],
        "caf_guidance": "Define an Azure network topology",
        "caf_url": "https://learn.microsoft.com/azure/cloud-adoption-framework/ready/azure-best-practices/define-an-azure-network-topology",
    },
    # ── Identity & Access Management ─────────────────────────────
    "mgd-iden": {
        "sub_area": "Authentication",
        "waf_pillar": "Security",
        "control_type": "ALZ",
        "required_signals": ["managed_identities"],
        "caf_guidance": "Identity and access management",
        "caf_url": "https://learn.microsoft.com/azure/cloud-adoption-framework/ready/landing-zone/design-area/identity-access",
    },
    "ca-polic": {
        "sub_area": "Access Control",
        "waf_pillar": "Security",
        "control_type": "ALZ",
        "required_signals": ["admin_ca_coverage"],
        "caf_guidance": "Identity and access management",
        "caf_url": "https://learn.microsoft.com/azure/cloud-adoption-framework/ready/landing-zone/design-area/identity-access",
    },
    "mfa-enfo": {
        "sub_area": "Authentication",
        "waf_pillar": "Security",
        "control_type": "ALZ",
        "required_signals": ["admin_ca_coverage"],
        "caf_guidance": "Identity and access management",
        "caf_url": "https://learn.microsoft.com/azure/cloud-adoption-framework/ready/landing-zone/design-area/identity-access",
    },
    "pim-zero": {
        "sub_area": "Privileged Access",
        "waf_pillar": "Security",
        "control_type": "ALZ",
        "required_signals": ["pim_maturity"],
        "caf_guidance": "Identity and access management",
        "caf_url": "https://learn.microsoft.com/azure/cloud-adoption-framework/ready/landing-zone/design-area/identity-access",
    },
    "bg-alz--": {
        "sub_area": "Emergency Access",
        "waf_pillar": "Security",
        "control_type": "ALZ",
        "required_signals": ["breakglass_validation"],
        "caf_guidance": "Identity and access management",
        "caf_url": "https://learn.microsoft.com/azure/cloud-adoption-framework/ready/landing-zone/design-area/identity-access",
    },
    "rbac-ali": {
        "sub_area": "RBAC",
        "waf_pillar": "Security",
        "control_type": "ALZ",
        "required_signals": ["rbac_hygiene"],
        "caf_guidance": "Identity and access management",
        "caf_url": "https://learn.microsoft.com/azure/cloud-adoption-framework/ready/landing-zone/design-area/identity-access",
    },
    "pim-revw": {
        "sub_area": "Privileged Access",
        "waf_pillar": "Security",
        "control_type": "ALZ",
        "required_signals": ["pim_usage"],
        "caf_guidance": "Identity and access management",
        "caf_url": "https://learn.microsoft.com/azure/cloud-adoption-framework/ready/landing-zone/design-area/identity-access",
    },
    "ctrl-del": {
        "sub_area": "RBAC",
        "waf_pillar": "Operational Excellence",
        "control_type": "ALZ",
        "required_signals": ["rbac_hygiene", "mg_hierarchy"],
        "caf_guidance": "Identity and access management",
        "caf_url": "https://learn.microsoft.com/azure/cloud-adoption-framework/ready/landing-zone/design-area/identity-access",
    },
    # ── Resource Organization ────────────────────────────────────
    "sandbox-": {
        "sub_area": "Management Groups",
        "waf_pillar": "Operational Excellence",
        "control_type": "ALZ",
        "required_signals": ["mg_hierarchy"],
        "caf_guidance": "Resource organization",
        "caf_url": "https://learn.microsoft.com/azure/cloud-adoption-framework/ready/landing-zone/design-area/resource-org",
    },
    "no-root-": {
        "sub_area": "Management Groups",
        "waf_pillar": "Operational Excellence",
        "control_type": "ALZ",
        "required_signals": ["mg_hierarchy"],
        "caf_guidance": "Resource organization",
        "caf_url": "https://learn.microsoft.com/azure/cloud-adoption-framework/ready/landing-zone/design-area/resource-org",
    },
    "mg-rbac-": {
        "sub_area": "Management Groups",
        "waf_pillar": "Security",
        "control_type": "ALZ",
        "required_signals": ["mg_hierarchy", "rbac_hygiene"],
        "caf_guidance": "Resource organization",
        "caf_url": "https://learn.microsoft.com/azure/cloud-adoption-framework/ready/landing-zone/design-area/resource-org",
    },
    "tag-bill": {
        "sub_area": "Tagging",
        "waf_pillar": "Cost Optimization",
        "control_type": "ALZ",
        "required_signals": ["tag_coverage"],
        "caf_guidance": "Resource organization",
        "caf_url": "https://learn.microsoft.com/azure/cloud-adoption-framework/ready/landing-zone/design-area/resource-org",
    },
    "region-s": {
        "sub_area": "Regions",
        "waf_pillar": "Reliability",
        "control_type": "ALZ",
        "required_signals": ["vnets"],
        "caf_guidance": "Resource organization",
        "caf_url": "https://learn.microsoft.com/azure/cloud-adoption-framework/ready/landing-zone/design-area/resource-org",
    },
    "multi-re": {
        "sub_area": "Regions",
        "waf_pillar": "Reliability",
        "control_type": "ALZ",
        "required_signals": ["vnets"],
        "caf_guidance": "Resource organization",
        "caf_url": "https://learn.microsoft.com/azure/cloud-adoption-framework/ready/landing-zone/design-area/resource-org",
    },
    # ── Platform Automation & DevOps ─────────────────────────────
    "kv-secre": {
        "sub_area": "Secrets Management",
        "waf_pillar": "Security",
        "control_type": "ALZ",
        "required_signals": ["keyvault_posture"],
        "caf_guidance": "Platform automation and DevOps",
        "caf_url": "https://learn.microsoft.com/azure/cloud-adoption-framework/ready/landing-zone/design-area/platform-automation-devops",
    },
    "iac-matu": {
        "sub_area": "Infrastructure as Code",
        "waf_pillar": "Operational Excellence",
        "control_type": "ALZ",
        "required_signals": ["activity_log_analysis"],
        "caf_guidance": "Platform automation and DevOps",
        "caf_url": "https://learn.microsoft.com/azure/cloud-adoption-framework/ready/landing-zone/design-area/platform-automation-devops",
    },
    "devsecop": {
        "sub_area": "DevSecOps",
        "waf_pillar": "Security",
        "control_type": "ALZ",
        "required_signals": ["defender_pricings", "keyvault_posture"],
        "caf_guidance": "Platform automation and DevOps",
        "caf_url": "https://learn.microsoft.com/azure/cloud-adoption-framework/ready/landing-zone/design-area/platform-automation-devops",
    },
    # ── Azure Billing & Entra ID Tenants ─────────────────────────
    "cost-rep": {
        "sub_area": "Cost Management",
        "waf_pillar": "Cost Optimization",
        "control_type": "ALZ",
        "required_signals": ["cost_management_posture"],
        "caf_guidance": "Azure billing and Microsoft Entra tenant",
        "caf_url": "https://learn.microsoft.com/azure/cloud-adoption-framework/ready/landing-zone/design-area/azure-billing-microsoft-entra-tenant",
    },
    "budget-a": {
        "sub_area": "Cost Management",
        "waf_pillar": "Cost Optimization",
        "control_type": "ALZ",
        "required_signals": ["cost_management_posture"],
        "caf_guidance": "Azure billing and Microsoft Entra tenant",
        "caf_url": "https://learn.microsoft.com/azure/cloud-adoption-framework/ready/landing-zone/design-area/azure-billing-microsoft-entra-tenant",
    },
    "notifica": {
        "sub_area": "Notifications",
        "waf_pillar": "Operational Excellence",
        "control_type": "ALZ",
        "required_signals": ["action_group_coverage"],
        "caf_guidance": "Azure billing and Microsoft Entra tenant",
        "caf_url": "https://learn.microsoft.com/azure/cloud-adoption-framework/ready/landing-zone/design-area/azure-billing-microsoft-entra-tenant",
    },
}

with open(CONTROLS_PATH, encoding="utf-8") as f:
    data = json.load(f)

fixed = 0
for key, patches in FIXES.items():
    ctrl = data["controls"].get(key)
    if ctrl is None:
        print(f"WARNING: {key} not found in controls.json", file=sys.stderr)
        continue
    ctrl.update(patches)
    fixed += 1

with open(CONTROLS_PATH, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print(f"Fixed {fixed}/{len(FIXES)} controls in {CONTROLS_PATH}")
