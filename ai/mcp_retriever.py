"""Microsoft Learn MCP retriever — structured doc search, code samples, and full fetch.

Uses the official MCP Python SDK (Streamable HTTP transport) to connect to:
    https://learn.microsoft.com/api/mcp

Available tools:
  1. microsoft_docs_search        — curated 500-token chunks
  2. microsoft_code_sample_search — code snippets by language
  3. microsoft_docs_fetch         — full page as markdown

Enriched with ALZ design-area-aware grounding — every search is scoped to
an official Azure Landing Zone design area when applicable.

Falls back to the public Learn search API if MCP is unreachable.
"""
from __future__ import annotations

import asyncio
import json
import requests
from typing import Any

from alz.loader import (
    ALZ_DESIGN_AREAS,
    get_design_area_learn_urls,
    get_items_by_design_area,
    build_prompt_checklist_context,
    get_design_area_summary,
)

# Lazy MCP imports — avoids hard failure when mcp SDK is not installed
# (e.g. --why / --demo mode only needs mcp_retriever's REST fallback)
ClientSession = None
streamable_http_client = None

def _ensure_mcp():
    """Import MCP SDK on first real use; raise clear error if missing."""
    global ClientSession, streamable_http_client
    if ClientSession is not None:
        return
    try:
        from mcp import ClientSession as _CS
        from mcp.client.streamable_http import streamable_http_client as _SHC
        ClientSession = _CS
        streamable_http_client = _SHC
    except ImportError as exc:
        raise ImportError(
            "MCP SDK not installed. Install with: pip install mcp"
        ) from exc


# ── MCP endpoint ──────────────────────────────────────────────────
MCP_URL = "https://learn.microsoft.com/api/mcp"
LEARN_SEARCH_FALLBACK = "https://learn.microsoft.com/api/search"
_TIMEOUT = 30


# ──────────────────────────────────────────────────────────────────
# Core MCP client (official SDK, Streamable HTTP transport)
# ──────────────────────────────────────────────────────────────────

async def _mcp_call_async(tool_name: str, arguments: dict) -> dict | None:
    """Invoke an MCP tool using the official SDK's Streamable HTTP client."""
    _ensure_mcp()
    try:
        async with streamable_http_client(MCP_URL) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments)
                if result and result.content:
                    text = result.content[0].text  # type: ignore[union-attr]
                    if text:
                        stripped = text.strip()
                        if stripped.startswith(("{", "[")):
                            return json.loads(stripped)
                        return {"text": text}
    except BaseException:
        # Must catch BaseException — asyncio.CancelledError (Python 3.9+)
        # is a BaseException, not an Exception
        return None
    return None


def _mcp_call(tool_name: str, arguments: dict) -> dict | None:
    """Synchronous wrapper around the async MCP client."""
    try:
        return asyncio.run(_mcp_call_async(tool_name, arguments))
    except RuntimeError:
        # If there's already an event loop running, use a new thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, _mcp_call_async(tool_name, arguments))
            return future.result(timeout=_TIMEOUT)
    except BaseException:
        # CancelledError, KeyboardInterrupt, etc. — let callers fall back
        return None


def _fallback_search(query: str, top: int = 5) -> list[dict]:
    """Public Learn search API fallback."""
    try:
        resp = requests.get(
            LEARN_SEARCH_FALLBACK,
            params={"search": query, "locale": "en-us", "$top": top},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        return [
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "description": item.get("description", ""),
            }
            for item in data.get("results", [])[:top]
        ]
    except Exception as e:
        print(f"  ⚠ Fallback search failed: {e}")
        return []


# ──────────────────────────────────────────────────────────────────
# Public API — search, code samples, fetch
# ──────────────────────────────────────────────────────────────────

def search_docs(query: str, top: int = 5) -> list[dict]:
    """
    Search Microsoft Learn via MCP (microsoft_docs_search).
    Returns up to *top* results with title, url, excerpt.
    Falls back to public API if MCP fails.
    """
    result = _mcp_call("microsoft_docs_search", {"query": query})
    if result and isinstance(result, list):
        return result[:top]
    if result and isinstance(result, dict):
        items = result.get("results", result.get("items", []))
        if items:
            return [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "excerpt": r.get("excerpt", r.get("content", "")),
                }
                for r in items[:top]
            ]
    # Fallback
    return _fallback_search(query, top)


def search_code_samples(
    query: str,
    language: str = "bicep",
    top: int = 5,
) -> list[dict]:
    """
    Search for code snippets via MCP (microsoft_code_sample_search).
    Returns up to *top* code samples.
    """
    result = _mcp_call("microsoft_code_sample_search", {
        "query": query,
        "language": language,
    })
    if result and isinstance(result, list):
        return result[:top]
    if result and isinstance(result, dict):
        items = result.get("results", result.get("samples", []))
        if items:
            return [
                {
                    "title": s.get("title", s.get("description", "")[:120]),
                    "language": s.get("language", language),
                    "code": s.get("codeSnippet", s.get("code", s.get("content", ""))),
                    "url": s.get("url", ""),
                }
                for s in items[:top]
            ]
    return []


def fetch_doc(url: str) -> str:
    """
    Fetch a full Learn page as markdown via MCP (microsoft_docs_fetch).
    Returns the markdown content or empty string.
    """
    result = _mcp_call("microsoft_docs_fetch", {"url": url})
    if result:
        return result.get("text", result.get("content", ""))
    return ""


# ──────────────────────────────────────────────────────────────────
# Grounding functions (used by the reasoning engine)
# ──────────────────────────────────────────────────────────────────

# ── ALZ Design-Area-Aware Microsoft Learn Queries ─────────────────
# Every search is scoped to an official ALZ design area so results
# are authoritative and aligned to the review checklist.
_ALZ_DESIGN_AREA_QUERIES: dict[str, list[str]] = {
    "Azure Billing and Microsoft Entra ID Tenants": [
        "Azure landing zone billing Microsoft Entra tenant design area",
        "Cloud Adoption Framework Azure billing subscription organization",
    ],
    "Identity and Access Management": [
        "Azure landing zone identity access management RBAC PIM Entra ID",
        "Cloud Adoption Framework identity design area conditional access break-glass",
    ],
    "Network Topology and Connectivity": [
        "Azure landing zone network topology hub spoke Virtual WAN connectivity",
        "Cloud Adoption Framework network design area Azure Firewall DNS Private Link",
    ],
    "Security": [
        "Azure landing zone security design area Defender for Cloud CSPM Sentinel",
        "Cloud Adoption Framework security baseline Microsoft Defender plans",
    ],
    "Management": [
        "Azure landing zone management design area monitoring Log Analytics diagnostics",
        "Cloud Adoption Framework management Azure Monitor Update Manager",
    ],
    "Resource Organization": [
        "Azure landing zone resource organization management groups subscriptions",
        "Cloud Adoption Framework resource organization naming tagging conventions",
    ],
    "Platform Automation and DevOps": [
        "Azure landing zone platform automation DevOps IaC Bicep subscription vending",
        "Cloud Adoption Framework platform automation GitOps Azure Verified Modules",
    ],
    "Governance": [
        "Azure landing zone governance design area Azure Policy compliance",
        "Cloud Adoption Framework governance policy initiatives cost management",
    ],
}

# Initiative-topic → ALZ design area mapping (enriches grounding)
_TOPIC_TO_DESIGN_AREA: dict[str, str] = {
    "security": "Security",
    "defender": "Security",
    "sentinel": "Security",
    "siem": "Security",
    "soc": "Security",
    "network": "Network Topology and Connectivity",
    "hub": "Network Topology and Connectivity",
    "spoke": "Network Topology and Connectivity",
    "firewall": "Network Topology and Connectivity",
    "dns": "Network Topology and Connectivity",
    "ddos": "Network Topology and Connectivity",
    "private endpoint": "Network Topology and Connectivity",
    "connectivity": "Network Topology and Connectivity",
    "governance": "Governance",
    "policy": "Governance",
    "compliance": "Governance",
    "cost": "Governance",
    "budget": "Governance",
    "identity": "Identity and Access Management",
    "rbac": "Identity and Access Management",
    "pim": "Identity and Access Management",
    "entra": "Identity and Access Management",
    "conditional access": "Identity and Access Management",
    "break-glass": "Identity and Access Management",
    "logging": "Management",
    "monitor": "Management",
    "diagnostic": "Management",
    "update manager": "Management",
    "log analytics": "Management",
    "management group": "Resource Organization",
    "subscription": "Resource Organization",
    "naming": "Resource Organization",
    "tagging": "Resource Organization",
    "resource org": "Resource Organization",
    "automation": "Platform Automation and DevOps",
    "iac": "Platform Automation and DevOps",
    "bicep": "Platform Automation and DevOps",
    "vending": "Platform Automation and DevOps",
    "devops": "Platform Automation and DevOps",
    "billing": "Azure Billing and Microsoft Entra ID Tenants",
    "tenant": "Azure Billing and Microsoft Entra ID Tenants",
}

# Tailored queries by initiative topic area (kept for backward compat)
_INITIATIVE_QUERIES: dict[str, str] = {
    "security": "Azure landing zone security baseline Defender for Cloud CSPM",
    "network": "Azure landing zone hub spoke connectivity Azure Firewall network topology",
    "governance": "Azure landing zone management group hierarchy policy driven governance",
    "identity": "Azure landing zone identity RBAC PIM Entra ID conditional access",
    "logging": "Azure Monitor centralized logging Microsoft Sentinel SIEM landing zone",
    "policy": "Azure Policy initiatives management group scope landing zone compliance",
    "management": "Azure landing zone management subscription monitoring diagnostics",
    "defender": "Microsoft Defender for Cloud plans subscriptions landing zone security",
    "ddos": "Azure DDoS Protection Standard landing zone network security",
    "diagnostics": "Azure diagnostic settings policy initiative Log Analytics",
}


def _pick_query(title: str) -> str:
    """Pick the best search query for an initiative title."""
    title_lower = title.lower()
    for keyword, query in _INITIATIVE_QUERIES.items():
        if keyword in title_lower:
            return query
    return f"Azure landing zone {title}"


def _infer_design_area(title: str) -> str | None:
    """Infer the ALZ design area from initiative title keywords."""
    title_lower = title.lower()
    for keyword, area in _TOPIC_TO_DESIGN_AREA.items():
        if keyword in title_lower:
            return area
    return None


# ──────────────────────────────────────────────────────────────────
# ALZ Design-Area-Aware Grounding (NEW)
# ──────────────────────────────────────────────────────────────────

def ground_by_design_area(design_area: str, top: int = 5) -> list[dict]:
    """Search Microsoft Learn for a specific ALZ design area.

    Uses the curated queries from _ALZ_DESIGN_AREA_QUERIES and
    supplements with a fetch of the canonical design area page.
    """
    queries = _ALZ_DESIGN_AREA_QUERIES.get(design_area, [])
    refs: list[dict] = []
    seen_urls: set[str] = set()

    for query in queries:
        try:
            results = search_docs(query, top=3)
            for r in results:
                url = r.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    refs.append(r)
        except Exception:
            pass

    # Always include the canonical CAF design area page
    canonical_urls = get_design_area_learn_urls()
    canonical = canonical_urls.get(design_area)
    if canonical and canonical not in seen_urls:
        refs.insert(0, {
            "title": f"ALZ Design Area — {design_area}",
            "url": canonical,
            "excerpt": f"Official Cloud Adoption Framework guidance for {design_area}.",
        })

    return refs[:top]


def fetch_design_area_guidance(design_area: str) -> str:
    """Fetch the full Microsoft Learn page for an ALZ design area.

    Returns the page content as markdown for deep grounding.
    """
    canonical_urls = get_design_area_learn_urls()
    url = canonical_urls.get(design_area)
    if not url:
        return ""
    return fetch_doc(url)


def ground_all_design_areas(top_per_area: int = 3) -> dict[str, list[dict]]:
    """Ground all 8 ALZ design areas with Microsoft Learn references.

    Returns {design_area: [refs]} for the full set.
    """
    grounded: dict[str, list[dict]] = {}
    for area in ALZ_DESIGN_AREAS:
        try:
            grounded[area] = ground_by_design_area(area, top=top_per_area)
        except Exception as e:
            print(f"  ⚠ Grounding failed for '{area}': {e}")
            grounded[area] = []
    return grounded


def build_alz_grounding_block() -> str:
    """Build a text block of ALZ checklist + Learn references for prompt injection.

    Combines the official checklist items with the canonical Learn URLs
    so LLMs have authoritative grounding for every recommendation.
    """
    lines = [
        "## Official Azure Landing Zone Design Areas",
        "Source: Azure/review-checklists GitHub repo + Microsoft Learn CAF",
        "",
    ]

    canonical_urls = get_design_area_learn_urls()
    try:
        summary = get_design_area_summary()
    except Exception:
        summary = []

    for i, area in enumerate(ALZ_DESIGN_AREAS, 1):
        url = canonical_urls.get(area, "")
        area_summary = next((s for s in summary if s["design_area"] == area), None)
        item_count = area_summary["total_items"] if area_summary else "?"
        lines.append(f"{i}. **{area}** ({item_count} checklist items)")
        if url:
            lines.append(f"   Learn: {url}")
        if area_summary and area_summary.get("severity_breakdown"):
            sevs = ", ".join(
                f"{k}: {v}" for k, v in area_summary["severity_breakdown"].items()
            )
            lines.append(f"   Severity: {sevs}")
        lines.append("")

    return "\n".join(lines)


def ground_initiatives(initiatives: list[dict]) -> list[dict]:
    """
    Enrich each initiative with up to 3 Microsoft Learn references.
    Uses MCP search with ALZ-design-area-aware queries.
    """
    for init in initiatives:
        title = init.get("title", "")
        # Primary: use ALZ design area query if we can infer it
        design_area = _infer_design_area(title)
        if design_area:
            try:
                refs = ground_by_design_area(design_area, top=3)
                init["learn_references"] = refs
                init["alz_design_area_grounded"] = design_area
                continue
            except Exception:
                pass

        # Fallback: topic-based query
        query = _pick_query(title)
        try:
            refs = search_docs(query, top=3)
            init["learn_references"] = refs
        except Exception as e:
            print(f"  ⚠ Learn search failed for initiative '{title[:50]}': {e}")
            init["learn_references"] = []
    return initiatives


def ground_gaps(gaps: list[dict]) -> list[dict]:
    """
    For each top gap, retrieve authoritative Microsoft Learn references.
    Scopes queries to the gap's ALZ design area when available.
    Returns enriched gap dicts with a 'references' key.
    """
    grounded = []
    for gap in gaps:
        query = gap.get("question") or gap.get("notes") or gap.get("control_id", "")
        query = query[:120]

        # Try infer ALZ design area from domain/section/query
        domain_hint = gap.get("domain", "") or gap.get("section", "")
        design_area = _infer_design_area(domain_hint) or _infer_design_area(query)

        try:
            if design_area:
                refs = ground_by_design_area(design_area, top=2)
            else:
                refs = search_docs(f"Azure Landing Zone {query}", top=2)
        except Exception as e:
            print(f"  ⚠ Learn search failed for '{query[:60]}': {e}")
            refs = []
        grounded.append({
            **gap,
            "references": refs,
            "alz_design_area": design_area or "",
        })
    return grounded


def ground_target_architecture(target_arch: dict) -> dict:
    """
    Enrich target architecture execution units and design areas
    with Microsoft Learn references and code samples.
    Uses ALZ design area mapping for scoped, authoritative results.
    """
    if not target_arch:
        return target_arch

    # Ground each phase's execution units
    for phase in target_arch.get("implementation_plan", {}).get("phases", []):
        for eu in phase.get("execution_units", []):
            capability = eu.get("capability", "")
            design_area = _infer_design_area(capability)

            # Primary: ALZ design-area-scoped grounding
            if design_area:
                try:
                    refs = ground_by_design_area(design_area, top=2)
                    eu["learn_references"] = refs
                    eu["alz_design_area"] = design_area
                except Exception:
                    eu["learn_references"] = []
            else:
                # Fallback: generic query
                query = f"Azure landing zone {capability}"
                try:
                    refs = search_docs(query, top=2)
                    eu["learn_references"] = refs
                except Exception:
                    eu["learn_references"] = []

            # Add code samples for infra-related capabilities
            cap_lower = capability.lower()
            if any(kw in cap_lower for kw in (
                "network", "firewall", "hub", "spoke", "vnet",
                "policy", "defender", "diagnostic", "log analytics",
                "management group", "subscription vend", "bicep",
            )):
                try:
                    samples = search_code_samples(
                        f"Azure {capability} Bicep template",
                        language="bicep",
                        top=2,
                    )
                    eu["code_samples"] = samples
                except Exception:
                    eu["code_samples"] = []

    # Also ground the target_state design areas if present
    target_state = target_arch.get("target_state", {})
    if target_state and not target_state.get("_learn_grounded"):
        canonical_urls = get_design_area_learn_urls()
        target_state["alz_design_area_references"] = {
            area: url for area, url in canonical_urls.items()
        }
        target_state["_learn_grounded"] = True

    return target_arch


def build_grounding_context(
    initiatives: list[dict],
    gaps: list[dict],
    target_arch: dict | None,
) -> dict[str, Any]:
    """
    Assemble a grounding context dict for LLM enrichment.
    The reasoning engine passes this to the grounding prompt so the AI
    can produce contextually relevant Learn references tied to findings.
    """
    context: dict[str, Any] = {
        "initiatives": [],
        "gaps": [],
        "target_execution_units": [],
    }

    for init in initiatives:
        refs = init.get("learn_references", [])
        if refs:
            context["initiatives"].append({
                "title": init.get("title", ""),
                "checklist_id": init.get("checklist_id", init.get("initiative_id", "")),
                "references": [
                    {"title": r.get("title", ""), "url": r.get("url", "")}
                    for r in refs[:3]
                ],
            })

    for gap in gaps:
        refs = gap.get("references", [])
        if refs:
            context["gaps"].append({
                "control_id": gap.get("control_id", ""),
                "question": gap.get("question", ""),
                "references": [
                    {"title": r.get("title", ""), "url": r.get("url", "")}
                    for r in refs[:2]
                ],
            })

    if target_arch:
        for phase in target_arch.get("implementation_plan", {}).get("phases", []):
            for eu in phase.get("execution_units", []):
                refs = eu.get("learn_references", [])
                if refs:
                    context["target_execution_units"].append({
                        "capability": eu.get("capability", ""),
                        "phase": phase.get("phase", ""),
                        "references": [
                            {"title": r.get("title", ""), "url": r.get("url", "")}
                            for r in refs[:2]
                        ],
                    })

    return context


# ──────────────────────────────────────────────────────────────────
# ALZ Implementation Pattern Retrieval (architectural decision support)
# ──────────────────────────────────────────────────────────────────

# Curated queries per ALZ module area — returns authoritative patterns
_ALZ_IMPLEMENTATION_QUERIES: dict[str, list[str]] = {
    "Identity and Access Management": [
        "Azure landing zone identity implementation Bicep module PIM RBAC",
        "ALZ Bicep identity subscription vending Entra ID conditional access",
    ],
    "Network Topology and Connectivity": [
        "Azure landing zone hub spoke implementation Bicep ALZ module",
        "ALZ Bicep network connectivity Virtual WAN Azure Firewall DNS",
    ],
    "Security": [
        "Azure landing zone security implementation Defender for Cloud Sentinel Bicep",
        "ALZ Bicep security baseline CSPM Defender plans policy assignment",
    ],
    "Management": [
        "Azure landing zone management implementation Log Analytics diagnostics Bicep",
        "ALZ Bicep management monitoring Azure Monitor Update Manager",
    ],
    "Governance": [
        "Azure landing zone governance implementation policy Bicep compliance",
        "ALZ Bicep governance policy initiative management group assignment",
    ],
    "Resource Organization": [
        "Azure landing zone management group hierarchy Bicep implementation",
        "ALZ Bicep resource organization subscription placement naming",
    ],
    "Platform Automation and DevOps": [
        "Azure landing zone platform automation Bicep subscription vending IaC",
        "ALZ Bicep DevOps pipeline GitHub Actions Azure Verified Modules",
    ],
    "Azure Billing and Microsoft Entra ID Tenants": [
        "Azure landing zone billing tenant organization Bicep",
        "ALZ Bicep billing EA MCA subscription creation",
    ],
}

# Known ALZ Bicep module patterns for structured fallback
_ALZ_MODULE_PATTERNS: dict[str, list[dict]] = {
    "Identity and Access Management": [
        {
            "pattern_name": "Centralized PIM + Conditional Access",
            "alz_module": "ALZ-Bicep/modules/identity",
            "description": "Deploy PIM roles, break-glass accounts, and conditional access policies via ALZ identity module.",
            "prerequisites": ["Management group hierarchy", "Entra ID P2 licensing"],
            "learn_url": "https://learn.microsoft.com/azure/cloud-adoption-framework/ready/landing-zone/design-area/identity-access",
        },
    ],
    "Network Topology and Connectivity": [
        {
            "pattern_name": "Hub-Spoke with Azure Firewall",
            "alz_module": "ALZ-Bicep/modules/hubNetworking",
            "description": "Deploy hub VNet with Azure Firewall, Bastion, and VPN/ExpressRoute gateway. Spoke VNets peer to hub.",
            "prerequisites": ["Connectivity subscription", "IP address plan"],
            "learn_url": "https://learn.microsoft.com/azure/cloud-adoption-framework/ready/azure-best-practices/hub-spoke-network-topology",
        },
        {
            "pattern_name": "Virtual WAN",
            "alz_module": "ALZ-Bicep/modules/vwanConnectivity",
            "description": "Deploy Azure Virtual WAN with secured hubs, SD-WAN integration, and multi-region connectivity.",
            "prerequisites": ["Connectivity subscription", "Branch office requirements"],
            "learn_url": "https://learn.microsoft.com/azure/cloud-adoption-framework/ready/azure-best-practices/virtual-wan-network-topology",
        },
    ],
    "Security": [
        {
            "pattern_name": "Defender for Cloud + Sentinel Baseline",
            "alz_module": "ALZ-Bicep/modules/policy/assignments/alzDefaults",
            "description": "Enable all Defender plans via policy, deploy Sentinel workspace with data connectors.",
            "prerequisites": ["Log Analytics workspace", "Security subscription"],
            "learn_url": "https://learn.microsoft.com/azure/cloud-adoption-framework/ready/landing-zone/design-area/security",
        },
    ],
    "Management": [
        {
            "pattern_name": "Centralized Logging + Diagnostics",
            "alz_module": "ALZ-Bicep/modules/logging",
            "description": "Deploy central Log Analytics workspace, automation account, and diagnostic policy assignments.",
            "prerequisites": ["Management subscription"],
            "learn_url": "https://learn.microsoft.com/azure/cloud-adoption-framework/ready/landing-zone/design-area/management",
        },
    ],
    "Governance": [
        {
            "pattern_name": "Policy-Driven Governance",
            "alz_module": "ALZ-Bicep/modules/policy/assignments/alzDefaults",
            "description": "Assign ALZ default policy initiatives at management group scope for compliance baseline.",
            "prerequisites": ["Management group hierarchy"],
            "learn_url": "https://learn.microsoft.com/azure/cloud-adoption-framework/ready/landing-zone/design-area/governance",
        },
    ],
    "Resource Organization": [
        {
            "pattern_name": "ALZ Management Group Hierarchy",
            "alz_module": "ALZ-Bicep/modules/managementGroups",
            "description": "Deploy the canonical ALZ management group structure with platform/landing zone/sandbox hierarchy.",
            "prerequisites": ["Tenant root access"],
            "learn_url": "https://learn.microsoft.com/azure/cloud-adoption-framework/ready/landing-zone/design-area/resource-organization",
        },
    ],
    "Platform Automation and DevOps": [
        {
            "pattern_name": "Subscription Vending + IaC Pipeline",
            "alz_module": "ALZ-Bicep/modules/subscriptionPlacement",
            "description": "Automated subscription vending via Bicep with GitHub Actions / Azure DevOps pipeline.",
            "prerequisites": ["Management group hierarchy", "Service principal with subscription contributor"],
            "learn_url": "https://learn.microsoft.com/azure/cloud-adoption-framework/ready/landing-zone/design-area/platform-automation-devops",
        },
    ],
}


def get_alz_implementation_options(
    initiative: dict,
    context: dict | None = None,
) -> list[dict]:
    """Retrieve ALZ implementation patterns for an initiative.

    Combines:
      1. Curated local patterns from _ALZ_MODULE_PATTERNS (always available)
      2. MCP Learn search for additional patterns & code samples

    Parameters
    ----------
    initiative : dict
        An initiative from the roadmap pass (has title, alz_design_area, controls).
    context : dict | None
        Optional assessment context (execution_context, platform_scale_limits)
        for filtering patterns by feasibility.

    Returns
    -------
    list[dict]
        Each dict has: pattern_name, alz_module, description, prerequisites, learn_url
    """
    title = initiative.get("title", "")
    design_area = initiative.get("alz_design_area") or _infer_design_area(title)

    options: list[dict] = []
    seen: set[str] = set()

    # 1. Local curated patterns (deterministic, always available)
    if design_area and design_area in _ALZ_MODULE_PATTERNS:
        for pattern in _ALZ_MODULE_PATTERNS[design_area]:
            options.append(pattern)
            seen.add(pattern["pattern_name"])

    # 2. MCP search for additional patterns
    queries = []
    if design_area and design_area in _ALZ_IMPLEMENTATION_QUERIES:
        queries = _ALZ_IMPLEMENTATION_QUERIES[design_area]
    else:
        queries = [f"Azure landing zone {title} Bicep ALZ module implementation"]

    for query in queries[:2]:
        try:
            results = search_docs(query, top=3)
            for r in results:
                name = r.get("title", "")[:80]
                if name and name not in seen:
                    seen.add(name)
                    options.append({
                        "pattern_name": name,
                        "alz_module": "",
                        "description": r.get("excerpt", r.get("description", ""))[:200],
                        "prerequisites": [],
                        "learn_url": r.get("url", ""),
                    })
        except Exception:
            pass

    # 3. Code samples for Bicep implementation
    try:
        bicep_query = f"Azure {design_area or title} Bicep ALZ module"
        samples = search_code_samples(bicep_query, language="bicep", top=2)
        for s in samples:
            name = f"Bicep: {s.get('title', '')[:60]}"
            if name not in seen:
                seen.add(name)
                options.append({
                    "pattern_name": name,
                    "alz_module": "",
                    "description": s.get("code", "")[:200],
                    "prerequisites": [],
                    "learn_url": s.get("url", ""),
                })
    except Exception:
        pass

    return options[:8]  # cap at 8 options to stay token-safe
