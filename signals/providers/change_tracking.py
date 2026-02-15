"""Change Tracking / Change Analysis signal provider.

Signals:
  monitor:change_tracking — Drift detection capability (Change Analysis, AMA Change Tracking)

Checks for:
  - Microsoft.ChangeAnalysis resource provider registration
  - Change Tracking solution on Log Analytics
  - Automation Account / AMA change tracking extensions
"""
from __future__ import annotations

import time
from typing import Any

from signals.types import SignalResult, SignalStatus
from collectors.azure_client import build_client


def fetch_change_tracking(subscription_id: str) -> SignalResult:
    """Detect Change Analysis / Change Tracking enablement.

    Checks:
      1. Microsoft.ChangeAnalysis RP registered on subscription
      2. Change Tracking solution deployed to Log Analytics workspace(s)
      3. VM extensions for Change Tracking (AMA or MMA)
    """
    start = time.perf_counter_ns()
    signal_name = "monitor:change_tracking"
    try:
        client = build_client(subscription_id=subscription_id)

        # 1. Check RP registration for Microsoft.ChangeAnalysis
        change_analysis_registered = False
        try:
            data = client.get(
                f"/subscriptions/{subscription_id}/providers/Microsoft.ChangeAnalysis",
                api_version="2021-04-01",
            )
            reg_state = (data.get("registrationState") or "").lower()
            change_analysis_registered = reg_state == "registered"
        except Exception:
            pass

        # 2. Check for ChangeTracking solution in workspaces
        change_tracking_solution = False
        try:
            data = client.get(
                f"/subscriptions/{subscription_id}/providers/Microsoft.OperationsManagement/solutions",
                api_version="2015-11-01-preview",
            )
            solutions = data.get("value", []) or []
            for sol in solutions:
                sol_name = (sol.get("name") or "").lower()
                plan = sol.get("plan", {}) or {}
                product = (plan.get("product") or "").lower()
                if "changetracking" in sol_name or "changetracking" in product:
                    change_tracking_solution = True
                    break
        except Exception:
            pass

        # 3. Probe for VM extensions related to change tracking (via RG)
        ct_extensions = 0
        try:
            from collectors.resource_graph import query_resource_graph
            query = (
                "resources "
                "| where type == 'microsoft.compute/virtualmachines/extensions' "
                "| where properties.type in~ ('ChangeTracking-Linux', 'ChangeTracking-Windows', "
                "     'MicrosoftMonitoringAgent', 'AzureMonitorLinuxAgent', 'AzureMonitorWindowsAgent') "
                "| summarize count()"
            )
            result = query_resource_graph(query, [subscription_id])
            rows = [r for r in (result or []) if isinstance(r, dict)]
            if rows:
                ct_extensions = rows[0].get("count_", 0) or 0
        except Exception:
            pass

        checks_passed = 0
        total_checks = 3
        if change_analysis_registered:
            checks_passed += 1
        if change_tracking_solution:
            checks_passed += 1
        if ct_extensions > 0:
            checks_passed += 1

        ratio = round(checks_passed / total_checks, 4)

        ms = (time.perf_counter_ns() - start) // 1_000_000
        return SignalResult(
            signal_name=signal_name,
            status=SignalStatus.OK,
            items=[],
            raw={
                "change_analysis_registered": change_analysis_registered,
                "change_tracking_solution": change_tracking_solution,
                "change_tracking_extensions": ct_extensions,
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
