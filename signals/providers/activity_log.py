"""Activity Log analysis signal provider.

Detects from Azure Activity Logs:
  - Manual vs IaC deployment ratio
  - Policy remediation activity
  - Firewall / NSG rule churn
  - RBAC change frequency

This yields a **platform automation maturity** signal.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any

from signals.types import SignalResult, SignalStatus
from collectors.azure_client import build_client


def fetch_activity_log_analysis(subscription_id: str) -> SignalResult:
    """Analyze Activity Log for deployment patterns and automation maturity.

    Scans the last 90 days of activity logs and categorizes operations
    into IaC-driven vs manual, policy remediations, and security churn.
    """
    start = time.perf_counter_ns()
    signal_name = "monitor:activity_log_analysis"
    try:
        client = build_client(subscription_id=subscription_id)

        end = datetime.now(timezone.utc)
        begin = end - timedelta(days=90)
        odata_filter = (
            f"eventTimestamp ge '{begin.strftime('%Y-%m-%dT%H:%M:%SZ')}' "
            f"and eventTimestamp le '{end.strftime('%Y-%m-%dT%H:%M:%SZ')}'"
        )

        try:
            data = client.get(
                f"/subscriptions/{subscription_id}/providers/Microsoft.Insights/eventtypes/management/values",
                api_version="2015-04-01",
                params={"$filter": odata_filter, "$top": "1000"},
            )
            events = data.get("value", []) or []
        except Exception:
            events = []

        # Classify events
        total_writes = 0
        iac_writes = 0
        manual_writes = 0
        policy_remediations = 0
        rbac_changes = 0
        nsg_changes = 0
        firewall_changes = 0

        # IaC caller patterns
        iac_callers = {
            "deploymentscript", "templatespec", "deployments",
            "microsoft.resources/deployments", "blueprint",
        }
        iac_user_agents = {"azurecli", "terraform", "pulumi", "bicep", "arm-template"}

        for evt in events:
            op_name = ""
            if isinstance(evt.get("operationName"), dict):
                op_name = (evt["operationName"].get("value") or "").lower()
            else:
                op_name = (evt.get("operationName") or "").lower()

            status_val = ""
            if isinstance(evt.get("status"), dict):
                status_val = (evt["status"].get("value") or "").lower()
            else:
                status_val = (evt.get("status") or "").lower()

            caller = (evt.get("caller") or "").lower()
            http_method = (evt.get("httpRequest", {}) or {}).get("method", "").upper()

            # Only count successful write operations
            if status_val not in ("succeeded", "accepted", "started"):
                continue
            if "/write" not in op_name and "/action" not in op_name:
                continue

            total_writes += 1

            # Deployment-related → IaC
            is_iac = False
            for pattern in iac_callers:
                if pattern in op_name:
                    is_iac = True
                    break
            if not is_iac:
                # Check user-agent heuristics from caller
                for ua in iac_user_agents:
                    if ua in caller:
                        is_iac = True
                        break

            if is_iac:
                iac_writes += 1
            else:
                manual_writes += 1

            # Classify specific operations
            if "microsoft.authorization/roleassignment" in op_name:
                rbac_changes += 1
            if "microsoft.network/networksecuritygroups" in op_name:
                nsg_changes += 1
            if "microsoft.network/azurefirewalls" in op_name or "microsoft.network/firewallpolicies" in op_name:
                firewall_changes += 1
            if "policyinsights" in op_name and "remediat" in op_name:
                policy_remediations += 1

        # Compute automation maturity score
        iac_ratio = round(iac_writes / total_writes, 4) if total_writes else 0.0

        automation_checks = 0
        total_checks = 4
        if iac_ratio >= 0.5:
            automation_checks += 1  # >50% IaC-driven
        if policy_remediations > 0:
            automation_checks += 1  # Active policy remediation
        if total_writes > 10:
            automation_checks += 1  # Non-trivial activity
        if rbac_changes < total_writes * 0.2:
            automation_checks += 1  # Low RBAC churn relative to total

        ratio = round(automation_checks / total_checks, 4)

        ms = (time.perf_counter_ns() - start) // 1_000_000
        return SignalResult(
            signal_name=signal_name,
            status=SignalStatus.OK,
            items=[],
            raw={
                "total_write_operations": total_writes,
                "iac_writes": iac_writes,
                "manual_writes": manual_writes,
                "iac_ratio": iac_ratio,
                "policy_remediations": policy_remediations,
                "rbac_changes": rbac_changes,
                "nsg_changes": nsg_changes,
                "firewall_changes": firewall_changes,
                "activity_events_sampled": len(events),
                "sample_window_days": 90,
                "coverage": {
                    "applicable": total_checks,
                    "compliant": automation_checks,
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
