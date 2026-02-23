"""Cost Simulation — category-based cost drivers per initiative.

Two modes:
  - "tool_backed"   : compute from MCP pricing tool SKU data (when available)
  - "category_only" : output cost driver categories only (Low/Medium/High)

CRITICAL: No dollar amounts unless mode == "tool_backed".

Layer: Derived models (deterministic joins only).
"""
from __future__ import annotations

from engine.guardrails import empty_evidence_refs


# ── Known resource → billing meter mappings ───────────────────────
# These are factual Azure billing meter names, not estimates.

RESOURCE_BILLING_MAP: dict[str, dict] = {
    "Azure Firewall": {
        "billing_meters": ["Firewall Deployment (hours)", "Data Processed (GB)"],
        "category_hint": "High",  # Firewall is a consistent monthly cost
    },
    "Azure Firewall Premium": {
        "billing_meters": ["Firewall Premium Deployment (hours)", "Data Processed (GB)", "TLS Inspection (GB)"],
        "category_hint": "High",
    },
    "DDoS Protection Plan": {
        "billing_meters": ["DDoS Protection Plan", "Overage per resource"],
        "category_hint": "High",
    },
    "Log Analytics Workspace": {
        "billing_meters": ["Data Ingestion (GB/day)", "Data Retention (GB/month beyond free)"],
        "category_hint": "Medium",
    },
    "Azure Monitor": {
        "billing_meters": ["Log Data Ingestion", "Metrics", "Alerts"],
        "category_hint": "Medium",
    },
    "Microsoft Defender for Cloud": {
        "billing_meters": ["Defender for Servers (per server/month)", "Defender for SQL (per instance)", "Defender for Storage (per account)"],
        "category_hint": "Medium",
    },
    "Azure Bastion": {
        "billing_meters": ["Bastion hours", "Outbound data transfer (GB)"],
        "category_hint": "Medium",
    },
    "VPN Gateway": {
        "billing_meters": ["Gateway hours", "S2S tunnels", "Data transfer (GB)"],
        "category_hint": "Medium",
    },
    "ExpressRoute": {
        "billing_meters": ["Circuit (per month)", "Standard/Premium add-on", "Data metered/unlimited"],
        "category_hint": "High",
    },
    "Azure Key Vault": {
        "billing_meters": ["Operations (per 10,000)", "Certificate renewals", "HSM-backed keys"],
        "category_hint": "Low",
    },
    "Azure Policy (remediation)": {
        "billing_meters": ["No direct cost — included in platform"],
        "category_hint": "Low",
    },
    "Management Group": {
        "billing_meters": ["No direct cost — included in platform"],
        "category_hint": "Low",
    },
    "Private Endpoints": {
        "billing_meters": ["Private Endpoint (per hour)", "Data processed (GB)"],
        "category_hint": "Low",
    },
    "Azure Backup": {
        "billing_meters": ["Protected Instances", "Backup Storage (GB/month)"],
        "category_hint": "Medium",
    },
    "Network Security Group": {
        "billing_meters": ["No direct cost — included in platform"],
        "category_hint": "Low",
    },
    "Route Table / UDR": {
        "billing_meters": ["No direct cost — included in platform"],
        "category_hint": "Low",
    },
}

# ── Initiative → resource mapping heuristics ──────────────────────
# Maps common initiative patterns to resources they typically introduce.

INITIATIVE_RESOURCE_PATTERNS: dict[str, list[str]] = {
    "network": ["Azure Firewall", "VPN Gateway", "Azure Bastion", "Private Endpoints"],
    "hub": ["Azure Firewall", "VPN Gateway", "Azure Bastion"],
    "firewall": ["Azure Firewall"],
    "logging": ["Log Analytics Workspace", "Azure Monitor"],
    "monitoring": ["Log Analytics Workspace", "Azure Monitor"],
    "diagnostic": ["Log Analytics Workspace"],
    "security": ["Microsoft Defender for Cloud", "Azure Key Vault"],
    "defender": ["Microsoft Defender for Cloud"],
    "ddos": ["DDoS Protection Plan"],
    "backup": ["Azure Backup"],
    "governance": ["Management Group", "Azure Policy (remediation)"],
    "policy": ["Azure Policy (remediation)"],
    "identity": ["Azure Key Vault"],
    "encryption": ["Azure Key Vault"],
    "private": ["Private Endpoints"],
    "expressroute": ["ExpressRoute"],
    "vpn": ["VPN Gateway"],
    "bastion": ["Azure Bastion"],
    "nsg": ["Network Security Group"],
    "route": ["Route Table / UDR"],
    "lock": [],  # no cost
}


def _infer_resources(initiative: dict) -> list[str]:
    """Infer which Azure resources an initiative would introduce."""
    title = (initiative.get("title") or "").lower()
    controls = initiative.get("controls", [])
    caf = (initiative.get("caf_discipline") or "").lower()
    selected_pattern = (initiative.get("selected_pattern") or "").lower()

    search_text = f"{title} {caf} {selected_pattern} {' '.join(controls)}"

    resources = set()
    for keyword, resource_list in INITIATIVE_RESOURCE_PATTERNS.items():
        if keyword in search_text:
            resources.update(resource_list)

    return sorted(resources)


def build_cost_simulation(
    initiatives: list[dict],
    results: list[dict],
    mcp_pricing_available: bool = False,
) -> dict:
    """
    Build cost simulation with per-initiative cost drivers.

    If MCP pricing tool is unavailable, outputs category labels only.

    Parameters
    ----------
    initiatives : list[dict]
        Initiative list from the roadmap.
    results : list[dict]
        Assessment control results.
    mcp_pricing_available : bool
        Whether the MCP pricing tool returned data.

    Returns
    -------
    dict conforming to cost_simulation schema.
    """
    mode = "tool_backed" if mcp_pricing_available else "category_only"

    drivers = []
    for init in initiatives:
        init_id = init.get("initiative_id", "")
        resources = _infer_resources(init)

        if not resources:
            continue

        billing_meters = []
        categories = []
        for resource in resources:
            mapping = RESOURCE_BILLING_MAP.get(resource, {})
            billing_meters.extend(mapping.get("billing_meters", []))
            cat = mapping.get("category_hint", "Unknown")
            categories.append(cat)

        # Aggregate category: highest wins
        if "High" in categories:
            combined_category = "High"
        elif "Medium" in categories:
            combined_category = "Medium"
        else:
            combined_category = "Low"

        # Evidence: controls affected by this initiative
        init_controls = init.get("controls", [])

        driver = {
            "initiative_id": init_id,
            "resources_introduced": resources,
            "billing_meters": list(set(billing_meters)),
            "estimated_monthly_category": combined_category,
            "evidence_refs": {
                "controls": init_controls[:10],
                "risks": [],
                "blockers": [],
                "signals": [],
                "mcp_queries": [],
            },
            "assumptions": [
                "Cost categories are directional only (Low/Medium/High)",
                "Actual costs depend on SKU selection, data volumes, and region",
            ],
        }

        if mode != "tool_backed":
            driver["assumptions"].append(
                "No pricing tool available — cost numbers are not provided"
            )

        drivers.append(driver)

    return {
        "mode": mode,
        "drivers": drivers,
    }
