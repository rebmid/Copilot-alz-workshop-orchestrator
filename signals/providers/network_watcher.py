"""Network Watcher signal provider.

Detects:
  - Network Watcher enabled per region
  - NSG Flow Logs v2 configured
  - Traffic Analytics enabled
  - Connection Monitor presence

This yields a **network observability** signal for CAF Ready (Network).
"""
from __future__ import annotations

import time
from typing import Any

from signals.types import SignalResult, SignalStatus
from collectors.azure_client import build_client


def fetch_network_watcher_posture(subscription_id: str) -> SignalResult:
    """Analyze Network Watcher observability posture.

    Determines if Network Watcher, flow logs, and Traffic Analytics
    are properly configured across regions with deployed workloads.
    """
    start = time.perf_counter_ns()
    signal_name = "network:watcher_posture"
    try:
        client = build_client(subscription_id=subscription_id)

        # 1. List Network Watchers
        watchers: list[dict[str, Any]] = []
        try:
            data = client.get(
                f"/subscriptions/{subscription_id}/providers/Microsoft.Network/networkWatchers",
                api_version="2024-01-01",
            )
            watchers = data.get("value", []) or []
        except Exception:
            pass

        watcher_regions = [w.get("location", "") for w in watchers]

        # 2. Check for NSG Flow Logs (global across all watchers)
        flow_logs: list[dict[str, Any]] = []
        flow_log_v2_count = 0
        traffic_analytics_count = 0
        for watcher in watchers:
            watcher_id = watcher.get("id", "")
            if not watcher_id:
                continue
            try:
                data = client.get(
                    f"{watcher_id}/flowLogs",
                    api_version="2024-01-01",
                )
                fl_items = data.get("value", []) or []
                for fl in fl_items:
                    props = fl.get("properties", {}) or {}
                    flow_logs.append({
                        "name": fl.get("name", ""),
                        "location": fl.get("location", ""),
                        "enabled": props.get("enabled", False),
                        "version": props.get("format", {}).get("version", 1),
                    })
                    if props.get("enabled", False):
                        fmt = props.get("format", {}) or {}
                        if fmt.get("version", 1) >= 2:
                            flow_log_v2_count += 1
                    # Traffic Analytics
                    ta_config = props.get("flowAnalyticsConfiguration", {}) or {}
                    na_config = ta_config.get("networkWatcherFlowAnalyticsConfiguration", {}) or {}
                    if na_config.get("enabled", False):
                        traffic_analytics_count += 1
            except Exception:
                pass

        # 3. Check for Connection Monitors
        conn_monitor_count = 0
        for watcher in watchers:
            watcher_id = watcher.get("id", "")
            if not watcher_id:
                continue
            try:
                data = client.get(
                    f"{watcher_id}/connectionMonitors",
                    api_version="2024-01-01",
                )
                monitors = data.get("value", []) or []
                conn_monitor_count += len(monitors)
            except Exception:
                pass

        # Score network observability
        checks_passed = 0
        total_checks = 4
        if len(watchers) > 0:
            checks_passed += 1
        if flow_log_v2_count > 0:
            checks_passed += 1
        if traffic_analytics_count > 0:
            checks_passed += 1
        if conn_monitor_count > 0:
            checks_passed += 1

        ratio = round(checks_passed / total_checks, 4)

        ms = (time.perf_counter_ns() - start) // 1_000_000
        return SignalResult(
            signal_name=signal_name,
            status=SignalStatus.OK,
            items=flow_logs[:20],
            raw={
                "watcher_count": len(watchers),
                "watcher_regions": watcher_regions,
                "flow_log_total": len(flow_logs),
                "flow_log_v2_count": flow_log_v2_count,
                "traffic_analytics_count": traffic_analytics_count,
                "connection_monitor_count": conn_monitor_count,
                "coverage": {
                    "applicable": total_checks,
                    "compliant": checks_passed,
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
