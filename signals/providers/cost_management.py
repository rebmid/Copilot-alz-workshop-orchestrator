"""Cost Management signal providers.

Signals:
  cost:management_posture  — Budget, alert, and RI/savings plan presence
  cost:forecast_accuracy   — Forecast vs actual spend delta (cost predictability)
  cost:idle_resources       — Idle/underutilized VMs based on Resource Graph + metrics

These yield **financial control maturity** signals for CAF Govern.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any

from signals.types import SignalResult, SignalStatus
from collectors.azure_client import build_client


def fetch_cost_management_posture(subscription_id: str) -> SignalResult:
    """Analyze Cost Management governance posture.

    Checks for budget presence, cost alerts, and spending governance
    mechanisms that indicate CAF Govern financial maturity.
    """
    start = time.perf_counter_ns()
    signal_name = "cost:management_posture"
    try:
        client = build_client(subscription_id=subscription_id)

        # 1. Check for budgets
        budgets: list[dict[str, Any]] = []
        try:
            data = client.get(
                f"/subscriptions/{subscription_id}/providers/Microsoft.Consumption/budgets",
                api_version="2023-11-01",
            )
            budgets = data.get("value", []) or []
        except Exception:
            pass

        budget_count = len(budgets)
        budget_details = []
        has_notification = False
        for b in budgets:
            props = b.get("properties", {}) or {}
            notifs = props.get("notifications", {}) or {}
            if notifs:
                has_notification = True
            budget_details.append({
                "name": b.get("name", ""),
                "amount": props.get("amount", 0),
                "time_grain": props.get("timeGrain", ""),
                "has_notifications": bool(notifs),
            })

        # 2. Check for cost anomaly alerts (Scheduled Actions / Alerts)
        anomaly_alerts = 0
        try:
            data = client.get(
                f"/subscriptions/{subscription_id}/providers/Microsoft.CostManagement/scheduledActions",
                api_version="2023-11-01",
            )
            actions = data.get("value", []) or []
            for action in actions:
                props = action.get("properties", {}) or {}
                kind = (props.get("viewId") or "").lower()
                if "anomaly" in kind or "alert" in (props.get("displayName") or "").lower():
                    anomaly_alerts += 1
            if not anomaly_alerts:
                anomaly_alerts = len(actions)  # any cost actions count
        except Exception:
            pass

        # 3. Check for reservation / savings plan (presence only)
        has_reservations = False
        try:
            data = client.get(
                f"/subscriptions/{subscription_id}/providers/Microsoft.Capacity/reservationOrders",
                api_version="2022-11-01",
            )
            reservations = data.get("value", []) or []
            has_reservations = len(reservations) > 0
        except Exception:
            pass

        # Score financial governance maturity
        checks_passed = 0
        total_checks = 4
        if budget_count > 0:
            checks_passed += 1
        if has_notification:
            checks_passed += 1
        if anomaly_alerts > 0:
            checks_passed += 1
        if has_reservations:
            checks_passed += 1

        ratio = round(checks_passed / total_checks, 4)

        ms = (time.perf_counter_ns() - start) // 1_000_000
        return SignalResult(
            signal_name=signal_name,
            status=SignalStatus.OK,
            items=budget_details[:10],
            raw={
                "budget_count": budget_count,
                "has_budget_notifications": has_notification,
                "cost_alert_count": anomaly_alerts,
                "has_reservations": has_reservations,
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

# ══════════════════════════════════════════════════════════════════
#  Forecast vs Actual Delta  (cost predictability)
# ══════════════════════════════════════════════════════════════════

def fetch_cost_forecast_accuracy(subscription_id: str) -> SignalResult:
    """Compare forecast vs actual spend via Cost Management Query API.

    Computes: abs(forecast - actual) / forecast → cost predictability %.
    Uses the previous billing month as the reference period.
    """
    start = time.perf_counter_ns()
    signal_name = "cost:forecast_accuracy"
    try:
        client = build_client(subscription_id=subscription_id)
        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        prev_month_end = month_start - timedelta(days=1)
        prev_month_start = prev_month_end.replace(day=1)

        # Actual cost for previous full month
        actual_cost: float = 0.0
        try:
            body = {
                "type": "ActualCost",
                "timeframe": "Custom",
                "timePeriod": {
                    "from": prev_month_start.strftime("%Y-%m-%dT00:00:00Z"),
                    "to": prev_month_end.strftime("%Y-%m-%dT23:59:59Z"),
                },
                "dataset": {
                    "granularity": "None",
                    "aggregation": {
                        "totalCost": {"name": "Cost", "function": "Sum"},
                    },
                },
            }
            data = client.post(
                f"/subscriptions/{subscription_id}/providers/Microsoft.CostManagement/query",
                api_version="2023-11-01",
                body=body,
            )
            rows_data = data.get("properties", {}).get("rows", []) or []
            if rows_data:
                actual_cost = float(rows_data[0][0]) if rows_data[0] else 0.0
        except Exception:
            pass

        # Forecast for current month (proxy for predictability)
        forecast_cost: float = 0.0
        try:
            forecast_body = {
                "type": "ActualCost",
                "timeframe": "MonthToDate",
                "dataset": {
                    "granularity": "None",
                    "aggregation": {
                        "totalCost": {"name": "Cost", "function": "Sum"},
                    },
                },
                "includeForecast": True,
            }
            data = client.post(
                f"/subscriptions/{subscription_id}/providers/Microsoft.CostManagement/forecast",
                api_version="2023-11-01",
                body=forecast_body,
            )
            rows_data = data.get("properties", {}).get("rows", []) or []
            if rows_data:
                forecast_cost = sum(float(r[0]) for r in rows_data if r)
        except Exception:
            pass

        # Predictability metric
        forecast_delta = 0.0
        predictability = 0.0
        if forecast_cost > 0 and actual_cost > 0:
            forecast_delta = round(abs(forecast_cost - actual_cost) / forecast_cost, 4)
            predictability = round(1.0 - min(forecast_delta, 1.0), 4)

        checks_passed = 0
        total_checks = 3
        if actual_cost > 0:
            checks_passed += 1            # Cost data available
        if forecast_cost > 0:
            checks_passed += 1            # Forecast available
        if predictability >= 0.8:
            checks_passed += 1            # ≤20% forecast error

        ms = (time.perf_counter_ns() - start) // 1_000_000
        return SignalResult(
            signal_name=signal_name,
            status=SignalStatus.OK,
            items=[],
            raw={
                "actual_cost_prev_month": actual_cost,
                "forecast_cost": forecast_cost,
                "forecast_delta_ratio": forecast_delta,
                "cost_predictability": predictability,
                "coverage": {
                    "applicable": total_checks,
                    "compliant": checks_passed,
                    "ratio": round(checks_passed / total_checks, 4),
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


# ══════════════════════════════════════════════════════════════════
#  Idle Resource Detection  (optimization opportunity $)
# ══════════════════════════════════════════════════════════════════

def fetch_idle_resources(subscriptions: list[str]) -> SignalResult:
    """Detect idle / underutilized VMs via Azure Advisor cost recommendations.

    Advisor flags VMs with low CPU / network usage and provides
    estimated savings amounts.
    """
    start = time.perf_counter_ns()
    signal_name = "cost:idle_resources"
    try:
        from collectors.resource_graph import query_resource_graph

        # Advisor cost recommendations for underutilized VMs
        query = (
            "advisorresources "
            "| where type == 'microsoft.advisor/recommendations' "
            "| where properties.category == 'Cost' "
            "| where properties.impactedField =~ 'Microsoft.Compute/virtualMachines' "
            "| project id, vmName=properties.impactedValue, "
            "  recommendation=properties.shortDescription.solution, "
            "  savings=properties.extendedProperties.savingsAmount, "
            "  annualSavings=properties.extendedProperties.annualSavingsAmount"
        )
        result = query_resource_graph(query, subscriptions)
        rows = [r for r in (result or []) if isinstance(r, dict)]
        idle_vm_count = len(rows)

        # Total VMs for ratio
        query_vms = (
            "resources "
            "| where type == 'microsoft.compute/virtualmachines' "
            "| summarize totalVMs=count()"
        )
        result_vms = query_resource_graph(query_vms, subscriptions)
        rows_vms = [r for r in (result_vms or []) if isinstance(r, dict)]
        total_vms = rows_vms[0].get("totalVMs", 0) if rows_vms else 0

        idle_ratio = round(idle_vm_count / total_vms, 4) if total_vms > 0 else 0.0

        # Estimated savings
        total_savings = 0.0
        for r in rows:
            try:
                total_savings += float(r.get("annualSavings") or r.get("savings") or 0)
            except (ValueError, TypeError):
                pass

        checks_passed = 0
        total_checks = 3
        if total_vms > 0:
            checks_passed += 1           # VMs exist to assess
        if idle_ratio < 0.1:
            checks_passed += 1           # <10% idle
        if total_savings == 0:
            checks_passed += 1           # No savings to capture

        ms = (time.perf_counter_ns() - start) // 1_000_000
        return SignalResult(
            signal_name=signal_name,
            status=SignalStatus.OK,
            items=rows[:20],
            raw={
                "idle_vm_count": idle_vm_count,
                "total_vm_count": total_vms,
                "idle_ratio": idle_ratio,
                "estimated_annual_savings": round(total_savings, 2),
                "coverage": {
                    "applicable": total_checks,
                    "compliant": checks_passed,
                    "ratio": round(checks_passed / total_checks, 4),
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