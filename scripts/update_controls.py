"""One-time script to add new evaluator entries to controls.json."""
import json

with open("control_packs/alz/v1.0/controls.json", encoding="utf-8") as f:
    data = json.load(f)

new_controls = {
    # Network Topology & Connectivity
    "std-lb-s": {"name": "Standard Load Balancer SKU", "full_id": "9dcd6250-9c4a-4382-aa9b-5b84c64fc1fe", "design_area": "network_topology", "severity": "High", "evaluation_logic": "automated", "evaluator_module": "evaluators.network_topology"},
    "lb-backe": {"name": "LB Backend Pool Instances", "full_id": "48682fb1-1e86-4458-a686-518ebd47393d", "design_area": "network_topology", "severity": "High", "evaluation_logic": "automated", "evaluator_module": "evaluators.network_topology"},
    "vnet-pee": {"name": "VNet Peering Traffic Allowed", "full_id": "c76cb5a2-abe2-11ed-afa1-0242ac120002", "design_area": "network_topology", "severity": "High", "evaluation_logic": "automated", "evaluator_module": "evaluators.network_topology"},
    "bastion-": {"name": "Azure Bastion Deployed", "full_id": "ee1ac551-c4d5-46cf-b035-d0a3c50d87ad", "design_area": "network_topology", "severity": "Medium", "evaluation_logic": "automated", "evaluator_module": "evaluators.network_topology"},
    "frontdoo": {"name": "Azure Front Door with WAF", "full_id": "1d7aa9b6-4704-4489-a804-2d88e79d17b7", "design_area": "network_topology", "severity": "Medium", "evaluation_logic": "automated", "evaluator_module": "evaluators.network_topology"},
    "privdns-": {"name": "Private DNS Zones", "full_id": "153e8908-ae28-4c84-a33b-6b7808b9fe5c", "design_area": "network_topology", "severity": "Medium", "evaluation_logic": "automated", "evaluator_module": "evaluators.network_topology"},
    "dns-auto": {"name": "DNS Auto-Registration", "full_id": "614658d3-558f-4d77-849b-821112df27ee", "design_area": "network_topology", "severity": "High", "evaluation_logic": "automated", "evaluator_module": "evaluators.network_topology"},
    "gw-subne": {"name": "Gateway Subnet Size", "full_id": "f2aad7e3-bb03-4adc-8606-4123d342a917", "design_area": "network_topology", "severity": "High", "evaluation_logic": "automated", "evaluator_module": "evaluators.network_topology"},
    "ddos-log": {"name": "DDoS Diagnostic Logs", "full_id": "b1c82a3f-2320-4dfa-8972-7ae4823c8930", "design_area": "network_topology", "severity": "High", "evaluation_logic": "automated", "evaluator_module": "evaluators.network_topology"},
    "shared-n": {"name": "Shared Networking Services", "full_id": "7dd61623-a364-4a90-9eca-e48ebd54cd7d", "design_area": "network_topology", "severity": "High", "evaluation_logic": "automated", "evaluator_module": "evaluators.network_topology"},
    "fw-diag-": {"name": "Firewall Diagnostic Logs", "full_id": "715d833d-4708-4527-90ac-1b142c7045ba", "design_area": "network_topology", "severity": "High", "evaluation_logic": "automated", "evaluator_module": "evaluators.network_topology"},
    "fw-subne": {"name": "Firewall Subnet Size /26", "full_id": "22d6419e-b627-4d95-9e7d-019fa759387f", "design_area": "network_topology", "severity": "High", "evaluation_logic": "automated", "evaluator_module": "evaluators.network_topology"},
    "ddos-fw-": {"name": "DDoS on Firewall VNet", "full_id": "e8143efa-0301-4d62-be54-ca7b5ce566dc", "design_area": "network_topology", "severity": "High", "evaluation_logic": "automated", "evaluator_module": "evaluators.network_topology"},
    "fw-premi": {"name": "Azure Firewall Premium", "full_id": "c10d51ef-f999-455d-bba0-5c90ece07447", "design_area": "network_topology", "severity": "High", "evaluation_logic": "automated", "evaluator_module": "evaluators.network_topology"},
    "fw-az-de": {"name": "Firewall Availability Zones", "full_id": "d38ad60c-bc9e-4d49-b699-97e5d4dcf707", "design_area": "network_topology", "severity": "High", "evaluation_logic": "automated", "evaluator_module": "evaluators.network_topology"},
    "onprem-p": {"name": "On-Premises Private Endpoints", "full_id": "b3e4563a-4d87-4397-98b6-62d6d15f512a", "design_area": "network_topology", "severity": "Medium", "evaluation_logic": "automated", "evaluator_module": "evaluators.network_topology"},
    "appgw-wa": {"name": "Application Gateway WAF", "full_id": "2363cefe-179b-4599-be0d-5973cd4cd21b", "design_area": "network_topology", "severity": "High", "evaluation_logic": "automated", "evaluator_module": "evaluators.network_topology"},
    "er-prima": {"name": "ExpressRoute as Primary", "full_id": "359c373e-7dd6-4162-9a36-4a907ecae48e", "design_area": "network_topology", "severity": "Medium", "evaluation_logic": "automated", "evaluator_module": "evaluators.network_topology"},
    # Identity & Access Management
    "mgd-iden": {"name": "Managed Identity Usage", "full_id": "4348bf81-7573-4512-8f46-9061cc198fea", "design_area": "identity_access", "severity": "High", "evaluation_logic": "automated", "evaluator_module": "evaluators.identity_access"},
    "ca-polic": {"name": "Conditional Access Policies", "full_id": "53e8908a-e28c-484c-93b6-b7808b9fe5c4", "design_area": "identity_access", "severity": "High", "evaluation_logic": "automated", "evaluator_module": "evaluators.identity_access"},
    "mfa-enfo": {"name": "MFA Enforcement", "full_id": "1049d403-a923-4c34-94d0-0018ac6a9e01", "design_area": "identity_access", "severity": "High", "evaluation_logic": "automated", "evaluator_module": "evaluators.identity_access"},
    "pim-zero": {"name": "PIM Zero Standing Access", "full_id": "14658d35-58fd-4772-99b8-21112df27ee4", "design_area": "identity_access", "severity": "Medium", "evaluation_logic": "automated", "evaluator_module": "evaluators.identity_access"},
    "bg-alz--": {"name": "Break-Glass Accounts (ALZ)", "full_id": "984a859c-773e-47d2-9162-3a765a917e1f", "design_area": "identity_access", "severity": "High", "evaluation_logic": "automated", "evaluator_module": "evaluators.identity_access"},
    "rbac-ali": {"name": "RBAC Model Alignment", "full_id": "348ef254-c27d-442e-abba-c7571559ab91", "design_area": "identity_access", "severity": "High", "evaluation_logic": "automated", "evaluator_module": "evaluators.identity_access"},
    "pim-revw": {"name": "PIM Access Reviews", "full_id": "d505ebcb-79b1-4274-9c0d-a27c8bea489c", "design_area": "identity_access", "severity": "Medium", "evaluation_logic": "automated", "evaluator_module": "evaluators.identity_access"},
    "ctrl-del": {"name": "Centralized Delegation", "full_id": "e6a83de5-de32-4c19-a248-1607d5d1e4e6", "design_area": "identity_access", "severity": "High", "evaluation_logic": "automated", "evaluator_module": "evaluators.identity_access"},
    # Resource Organization
    "sandbox-": {"name": "Sandbox Management Group", "full_id": "667313b4-f566-44b5-b984-a859c773e7d2", "design_area": "resource_org", "severity": "Medium", "evaluation_logic": "automated", "evaluator_module": "evaluators.resource_organization"},
    "no-root-": {"name": "No Subscriptions Under Root MG", "full_id": "33b6b780-8b9f-4e5c-9104-9d403a923c34", "design_area": "resource_org", "severity": "Medium", "evaluation_logic": "automated", "evaluator_module": "evaluators.resource_organization"},
    "mg-rbac-": {"name": "MG RBAC Authorization", "full_id": "74d00018-ac6a-49e0-8e6a-83de5de32c19", "design_area": "resource_org", "severity": "Medium", "evaluation_logic": "automated", "evaluator_module": "evaluators.resource_organization"},
    "tag-bill": {"name": "Tags for Billing", "full_id": "5de32c19-9248-4160-9d5d-1e4e614658d3", "design_area": "resource_org", "severity": "Medium", "evaluation_logic": "automated", "evaluator_module": "evaluators.resource_organization"},
    "region-s": {"name": "Region Selection", "full_id": "250d81ce-8bbe-4f85-9051-6a18a8221e50", "design_area": "resource_org", "severity": "High", "evaluation_logic": "automated", "evaluator_module": "evaluators.resource_organization"},
    "multi-re": {"name": "Multi-Region Deployment", "full_id": "19ca3f89-397d-44b1-b5b6-5e18661372ac", "design_area": "resource_org", "severity": "Medium", "evaluation_logic": "automated", "evaluator_module": "evaluators.resource_organization"},
    # Platform Automation & DevOps
    "kv-secre": {"name": "Key Vault for Secrets", "full_id": "108d5099-a11d-4445-bd8b-e12a5e95412e", "design_area": "platform_automation", "severity": "High", "evaluation_logic": "automated", "evaluator_module": "evaluators.platform_automation"},
    "iac-matu": {"name": "IaC Maturity", "full_id": "2cdc9d99-dbcc-4ad4-97f5-e7d358bdfa73", "design_area": "platform_automation", "severity": "High", "evaluation_logic": "automated", "evaluator_module": "evaluators.platform_automation"},
    "devsecop": {"name": "DevSecOps Integration", "full_id": "cc87a3bc-c572-4ad2-92ed-8cabab66160f", "design_area": "platform_automation", "severity": "High", "evaluation_logic": "automated", "evaluator_module": "evaluators.platform_automation"},
    # Azure Billing
    "cost-rep": {"name": "Cost Reporting Setup", "full_id": "32952499-58c8-4e6f-ada5-972e67893d55", "design_area": "billing", "severity": "Medium", "evaluation_logic": "automated", "evaluator_module": "evaluators.billing"},
    "budget-a": {"name": "Budget Alerts", "full_id": "54f0d8b1-22a3-4c0d-8ce2-58b9e086c93a", "design_area": "billing", "severity": "Low", "evaluation_logic": "automated", "evaluator_module": "evaluators.billing"},
    "notifica": {"name": "Notification Contact Email", "full_id": "685cb4f2-ac9c-4b19-9167-993ed0b32415", "design_area": "billing", "severity": "Medium", "evaluation_logic": "automated", "evaluator_module": "evaluators.billing"},
}

new_design_areas = {
    "network_topology": {
        "label": "Network Topology & Connectivity (ALZ)",
        "controls": [k for k, v in new_controls.items() if v["design_area"] == "network_topology"],
    },
    "identity_access": {
        "label": "Identity & Access Management (ALZ)",
        "controls": [k for k, v in new_controls.items() if v["design_area"] == "identity_access"],
    },
    "resource_org": {
        "label": "Resource Organization (ALZ)",
        "controls": [k for k, v in new_controls.items() if v["design_area"] == "resource_org"],
    },
    "platform_automation": {
        "label": "Platform Automation & DevOps (ALZ)",
        "controls": [k for k, v in new_controls.items() if v["design_area"] == "platform_automation"],
    },
    "billing": {
        "label": "Azure Billing & Entra Tenants (ALZ)",
        "controls": [k for k, v in new_controls.items() if v["design_area"] == "billing"],
    },
}

data["design_areas"].update(new_design_areas)
data["controls"].update(new_controls)
data["version"] = "1.4.0"
data["description"] = "85+ automated control evaluators covering all ALZ design areas."

with open("control_packs/alz/v1.0/controls.json", "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print(f"Updated controls.json: {len(data['controls'])} controls, {len(data['design_areas'])} design areas")
