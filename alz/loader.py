"""Azure Landing Zone checklist loader — structured access to the official ALZ review checklist.

Fetches from the Azure/review-checklists GitHub repo, caches in-memory,
and exposes design-area-aware lookups for prompts, grounding, and validation.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import requests

ALZ_CHECKLIST_URL = (
    "https://raw.githubusercontent.com/Azure/review-checklists/"
    "main/checklists/alz_checklist.en.json"
)

# 8 official ALZ design areas — canonical list used everywhere
ALZ_DESIGN_AREAS: list[str] = [
    "Azure Billing and Microsoft Entra ID Tenants",
    "Identity and Access Management",
    "Network Topology and Connectivity",
    "Security",
    "Management",
    "Resource Organization",
    "Platform Automation and DevOps",
    "Governance",
]

# ── In-memory cache ──────────────────────────────────────────────
_cache: dict[str, Any] = {"raw": None, "ts": 0.0}
_CACHE_TTL = 3600  # 1 hour

# Local cache path (next to this file)
_LOCAL_CACHE = Path(__file__).parent / "_alz_checklist_cache.json"


def load_alz_checklist(*, force_refresh: bool = False) -> dict:
    """Load the full ALZ checklist JSON.  Uses in-memory and disk cache."""
    now = time.time()

    # 1. In-memory cache
    if not force_refresh and _cache["raw"] and (now - _cache["ts"]) < _CACHE_TTL:
        return _cache["raw"]

    # 2. Disk cache (survives process restarts)
    if not force_refresh and _LOCAL_CACHE.exists():
        age = now - _LOCAL_CACHE.stat().st_mtime
        if age < _CACHE_TTL:
            try:
                data = json.loads(_LOCAL_CACHE.read_text(encoding="utf-8"))
                _cache["raw"], _cache["ts"] = data, now
                return data
            except Exception:
                pass

    # 3. Fetch from GitHub
    try:
        resp = requests.get(ALZ_CHECKLIST_URL, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        # If fetch fails but we have stale cache, use it
        if _cache["raw"]:
            print(f"  ⚠ ALZ checklist fetch failed ({exc}); using stale cache")
            return _cache["raw"]
        if _LOCAL_CACHE.exists():
            return json.loads(_LOCAL_CACHE.read_text(encoding="utf-8"))
        raise

    # Persist
    _cache["raw"], _cache["ts"] = data, now
    try:
        _LOCAL_CACHE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass  # non-critical
    return data


# ── Structured accessors ─────────────────────────────────────────

def get_checklist_items() -> list[dict]:
    """Return the flat list of checklist items from the official JSON."""
    data = load_alz_checklist()
    return data.get("items", data.get("checklist", []))


def get_items_by_design_area() -> dict[str, list[dict]]:
    """Group checklist items by their ALZ design area (category field)."""
    items = get_checklist_items()
    by_area: dict[str, list[dict]] = {area: [] for area in ALZ_DESIGN_AREAS}
    for item in items:
        area = item.get("category", "")
        if area in by_area:
            by_area[area].append(item)
        else:
            by_area.setdefault(area, []).append(item)
    return by_area


def get_item_by_id(item_id: str) -> dict | None:
    """Look up a single checklist item by its GUID."""
    for item in get_checklist_items():
        if item.get("id") == item_id or item.get("guid") == item_id:
            return item
    return None


def get_items_by_severity(severity: str = "High") -> list[dict]:
    """Return checklist items filtered by severity (High, Medium, Low)."""
    return [
        item for item in get_checklist_items()
        if item.get("severity", "").lower() == severity.lower()
    ]


def get_design_area_summary() -> list[dict]:
    """Return a compact summary per design area (count, severities, sample IDs).

    Useful for injecting into LLM prompts as grounding context.
    """
    by_area = get_items_by_design_area()
    summaries = []
    for area in ALZ_DESIGN_AREAS:
        items = by_area.get(area, [])
        sev_counts: dict[str, int] = {}
        for item in items:
            s = item.get("severity", "Unknown")
            sev_counts[s] = sev_counts.get(s, 0) + 1
        summaries.append({
            "design_area": area,
            "total_items": len(items),
            "severity_breakdown": sev_counts,
            "sample_ids": [item.get("id", "")[:12] for item in items[:5]],
        })
    return summaries


def build_prompt_checklist_context(design_area: str | None = None, max_items: int = 30) -> str:
    """Build a compact text block of ALZ checklist items for LLM prompt injection.

    If *design_area* is specified, only items from that area are included.
    Returns a formatted text string ready for prompt inclusion.
    """
    if design_area:
        items = get_items_by_design_area().get(design_area, [])
    else:
        items = get_checklist_items()

    lines = [
        "## Official ALZ Checklist Reference",
        f"Source: Azure/review-checklists (design area: {design_area or 'all'})",
        "",
    ]
    for item in items[:max_items]:
        item_id = item.get("id", item.get("guid", "?"))[:12]
        sev = item.get("severity", "")
        text = item.get("text", item.get("description", ""))[:200]
        cat = item.get("category", "")
        sub = item.get("subcategory", "")
        lines.append(f"- [{item_id}] ({sev}) [{cat} > {sub}] {text}")
    if len(items) > max_items:
        lines.append(f"  … and {len(items) - max_items} more items")
    return "\n".join(lines)


def get_design_area_learn_urls() -> dict[str, str]:
    """Return the canonical Microsoft Learn URL for each ALZ design area.

    These are the authoritative starting points for documentation grounding.
    """
    return {
        "Azure Billing and Microsoft Entra ID Tenants":
            "https://learn.microsoft.com/azure/cloud-adoption-framework/ready/landing-zone/design-area/azure-billing-ad-tenant",
        "Identity and Access Management":
            "https://learn.microsoft.com/azure/cloud-adoption-framework/ready/landing-zone/design-area/identity-access",
        "Network Topology and Connectivity":
            "https://learn.microsoft.com/azure/cloud-adoption-framework/ready/landing-zone/design-area/network-topology-and-connectivity",
        "Security":
            "https://learn.microsoft.com/azure/cloud-adoption-framework/ready/landing-zone/design-area/security",
        "Management":
            "https://learn.microsoft.com/azure/cloud-adoption-framework/ready/landing-zone/design-area/management",
        "Resource Organization":
            "https://learn.microsoft.com/azure/cloud-adoption-framework/ready/landing-zone/design-area/resource-org",
        "Platform Automation and DevOps":
            "https://learn.microsoft.com/azure/cloud-adoption-framework/ready/landing-zone/design-area/platform-automation-devops",
        "Governance":
            "https://learn.microsoft.com/azure/cloud-adoption-framework/ready/landing-zone/design-area/governance",
    }
