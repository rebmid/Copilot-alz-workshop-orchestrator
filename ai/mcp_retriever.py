"""Microsoft Learn MCP retriever — structured doc search, code samples, and full fetch.

Uses the official MCP Python SDK (Streamable HTTP transport) to connect to:
    https://learn.microsoft.com/api/mcp

Available tools:
  1. microsoft_docs_search        — curated 500-token chunks
  2. microsoft_code_sample_search — code snippets by language
  3. microsoft_docs_fetch         — full page as markdown

Falls back to the public Learn search API if MCP is unreachable.
"""
from __future__ import annotations

import asyncio
import json
import requests
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


# ── MCP endpoint ──────────────────────────────────────────────────
MCP_URL = "https://learn.microsoft.com/api/mcp"
LEARN_SEARCH_FALLBACK = "https://learn.microsoft.com/api/search"
_TIMEOUT = 30


# ──────────────────────────────────────────────────────────────────
# Core MCP client (official SDK, Streamable HTTP transport)
# ──────────────────────────────────────────────────────────────────

async def _mcp_call_async(tool_name: str, arguments: dict) -> dict | None:
    """Invoke an MCP tool using the official SDK's Streamable HTTP client."""
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
    except Exception:
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

# Tailored queries by initiative topic area
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


def ground_initiatives(initiatives: list[dict]) -> list[dict]:
    """
    Enrich each initiative with up to 3 Microsoft Learn references.
    Uses MCP search with tailored queries.
    """
    for init in initiatives:
        title = init.get("title", "")
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
    Returns enriched gap dicts with a 'references' key.
    """
    grounded = []
    for gap in gaps:
        query = gap.get("question") or gap.get("notes") or gap.get("control_id", "")
        query = query[:120]
        try:
            refs = search_docs(f"Azure Landing Zone {query}", top=2)
        except Exception as e:
            print(f"  ⚠ Learn search failed for '{query[:60]}': {e}")
            refs = []
        grounded.append({**gap, "references": refs})
    return grounded


def ground_target_architecture(target_arch: dict) -> dict:
    """
    Enrich target architecture execution units and design areas
    with Microsoft Learn references and code samples.
    """
    if not target_arch:
        return target_arch

    # Ground each phase's execution units
    for phase in target_arch.get("implementation_plan", {}).get("phases", []):
        for eu in phase.get("execution_units", []):
            capability = eu.get("capability", "")
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
                "initiative_id": init.get("initiative_id", ""),
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
# Backward-compat aliases
# ──────────────────────────────────────────────────────────────────
search_learn = search_docs
enrich_with_mcp = ground_initiatives
