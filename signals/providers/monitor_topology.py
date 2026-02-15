"""Azure Monitor workspace topology signal provider.

Detects:
  - Number of Log Analytics workspaces
  - Central vs per-subscription distribution
  - Sentinel enabled?
  - Cross-region log flow
"""
from __future__ import annotations

import time
from typing import Any

from signals.types import SignalResult, SignalStatus
from collectors.azure_client import build_client


def fetch_workspace_topology(subscription_id: str) -> SignalResult:
    """Discover Log Analytics workspace topology across the subscription.

    Returns workspace count, distribution model, Sentinel enablement,
    and cross-region analysis.
    """
    start = time.perf_counter_ns()
    signal_name = "monitor:workspace_topology"
    try:
        client = build_client(subscription_id=subscription_id)

        # List workspaces
        data = client.get(
            f"/subscriptions/{subscription_id}/providers/Microsoft.OperationalInsights/workspaces",
            api_version="2022-10-01",
        )
        workspaces = data.get("value", []) or []

        workspace_details: list[dict[str, Any]] = []
        regions: set[str] = set()
        sentinel_enabled_count = 0

        for ws in workspaces:
            ws_name = ws.get("name", "")
            ws_id = ws.get("id", "")
            ws_location = ws.get("location", "")
            ws_props = ws.get("properties", {}) or {}
            sku = ws_props.get("sku", {}).get("name", "unknown")
            retention = ws_props.get("retentionInDays", 0)

            regions.add(ws_location.lower())

            # Check for Sentinel (SecurityInsights solution)
            sentinel_on = False
            try:
                sentinel_data = client.get(
                    f"{ws_id}/providers/Microsoft.SecurityInsights/onboardingStates",
                    api_version="2024-03-01",
                )
                states = sentinel_data.get("value", []) or []
                if states:
                    sentinel_on = True
                    sentinel_enabled_count += 1
            except Exception:
                # Sentinel API may not be available — not a failure
                pass

            workspace_details.append({
                "name": ws_name,
                "id": ws_id,
                "location": ws_location,
                "sku": sku,
                "retention_days": retention,
                "sentinel_enabled": sentinel_on,
            })

        total = len(workspaces)
        is_centralized = total <= 2  # 1 primary + 1 optional DR
        cross_region = len(regions) > 1

        # SOC maturity indicators
        soc_checks_passed = 0
        soc_total = 4
        if total >= 1:
            soc_checks_passed += 1  # Has workspace
        if is_centralized:
            soc_checks_passed += 1  # Centralized model
        if sentinel_enabled_count > 0:
            soc_checks_passed += 1  # SIEM present
        if any(w["retention_days"] >= 90 for w in workspace_details):
            soc_checks_passed += 1  # Adequate retention

        ratio = round(soc_checks_passed / soc_total, 4) if soc_total else 0.0

        ms = (time.perf_counter_ns() - start) // 1_000_000
        return SignalResult(
            signal_name=signal_name,
            status=SignalStatus.OK,
            items=workspace_details,
            raw={
                "workspace_count": total,
                "is_centralized": is_centralized,
                "sentinel_enabled_count": sentinel_enabled_count,
                "has_sentinel": sentinel_enabled_count > 0,
                "cross_region_flow": cross_region,
                "regions": sorted(regions),
                "max_retention_days": max((w["retention_days"] for w in workspace_details), default=0),
                "coverage": {
                    "applicable": soc_total,
                    "compliant": soc_checks_passed,
                    "ratio": ratio,
                },
            },
            duration_ms=ms,
        )
    except Exception as e:
        ms = (time.perf_counter_ns() - start) // 1_000_000
        return SignalResult(
            signal_name=signal_name,
            status=SignalStatus.ERROR,
            error_msg=str(e),
            duration_ms=ms,
        )
