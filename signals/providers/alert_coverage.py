"""Alert & Operations maturity signal providers.

Signals:
  monitor:alert_action_mapping   — Metric alerts with vs without action groups
  monitor:action_group_coverage  — Resources with diagnostics that route to action groups
  monitor:availability_signals   — Service Health alerts + smart detection (SLO posture)

These yield **operations readiness** signals for CAF Manage.
"""
from __future__ import annotations

import time
from typing import Any

from signals.types import SignalResult, SignalStatus
from collectors.azure_client import build_client


# ══════════════════════════════════════════════════════════════════
#  5.  Alert → Action Group mapping
# ══════════════════════════════════════════════════════════════════

def fetch_alert_action_mapping(subscriptions: list[str]) -> SignalResult:
    """Detect metric alerts and whether they have action groups.

    Alert with no action group = monitoring theater.
    Uses Resource Graph to enumerate microsoft.insights/metricalerts.
    """
    start = time.perf_counter_ns()
    signal_name = "monitor:alert_action_mapping"
    try:
        from collectors.resource_graph import query_resource_graph

        query = (
            "resources "
            "| where type == 'microsoft.insights/metricalerts' "
            "| extend actions = properties.actions.actionGroups "
            "| project id, name, location, "
            "  severity = tostring(properties.severity), "
            "  enabled = tobool(properties.enabled), "
            "  actionGroupCount = array_length(actions)"
        )
        result = query_resource_graph(query, subscriptions)
        rows = [r for r in (result or []) if isinstance(r, dict)]

        total_alerts = len(rows)
        alerts_with_ag = sum(1 for r in rows if (r.get("actionGroupCount") or 0) > 0)
        alerts_without_ag = total_alerts - alerts_with_ag
        enabled_alerts = sum(1 for r in rows if r.get("enabled", False))

        # Also check for scheduled query rules (log alerts)
        query_log = (
            "resources "
            "| where type == 'microsoft.insights/scheduledqueryrules' "
            "| extend actions = properties.actions.actionGroups "
            "| project id, name, "
            "  actionGroupCount = array_length(actions)"
        )
        result_log = query_resource_graph(query_log, subscriptions)
        rows_log = [r for r in (result_log or []) if isinstance(r, dict)]
        log_alerts = len(rows_log)
        log_with_ag = sum(1 for r in rows_log if (r.get("actionGroupCount") or 0) > 0)

        total_all = total_alerts + log_alerts
        total_with_ag = alerts_with_ag + log_with_ag
        ag_ratio = round(total_with_ag / total_all, 4) if total_all > 0 else 0.0

        checks_passed = 0
        total_checks = 4
        if total_alerts > 0:
            checks_passed += 1       # Metric alerts exist
        if alerts_without_ag == 0 and total_alerts > 0:
            checks_passed += 1       # All metric alerts have AG
        if log_alerts > 0:
            checks_passed += 1       # Log alerts exist
        if ag_ratio >= 0.9:
            checks_passed += 1       # ≥90% coverage

        ms = (time.perf_counter_ns() - start) // 1_000_000
        return SignalResult(
            signal_name=signal_name,
            status=SignalStatus.OK,
            items=rows[:20],
            raw={
                "metric_alert_count": total_alerts,
                "metric_alerts_with_action_group": alerts_with_ag,
                "metric_alerts_without_action_group": alerts_without_ag,
                "metric_alerts_enabled": enabled_alerts,
                "log_alert_count": log_alerts,
                "log_alerts_with_action_group": log_with_ag,
                "action_group_coverage_ratio": ag_ratio,
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
#  6.  Action group coverage (resource → diagnostic → action group)
# ══════════════════════════════════════════════════════════════════

def fetch_action_group_coverage(subscription_id: str) -> SignalResult:
    """Measure action group presence across the subscription.

    Counts total action groups and checks that smart-detection
    (Application Insights) or service-health action groups exist.
    """
    start = time.perf_counter_ns()
    signal_name = "monitor:action_group_coverage"
    try:
        client = build_client(subscription_id=subscription_id)

        # List action groups
        ag_list: list[dict[str, Any]] = []
        try:
            data = client.get(
                f"/subscriptions/{subscription_id}/providers/microsoft.insights/actionGroups",
                api_version="2023-01-01",
            )
            ag_list = data.get("value", []) or []
        except Exception:
            pass

        total_ag = len(ag_list)

        # Classify receivers
        has_email = False
        has_webhook = False
        has_logicapp = False
        for ag in ag_list:
            props = ag.get("properties", {}) or {}
            if props.get("emailReceivers"):
                has_email = True
            if props.get("webhookReceivers"):
                has_webhook = True
            if props.get("logicAppReceivers") or props.get("azureFunctionReceivers"):
                has_logicapp = True

        checks_passed = 0
        total_checks = 4
        if total_ag > 0:
            checks_passed += 1
        if has_email:
            checks_passed += 1
        if has_webhook or has_logicapp:
            checks_passed += 1        # Automated response
        if total_ag >= 3:
            checks_passed += 1        # Separation of concern

        ms = (time.perf_counter_ns() - start) // 1_000_000
        return SignalResult(
            signal_name=signal_name,
            status=SignalStatus.OK,
            items=[{"name": ag.get("name", ""), "location": ag.get("location", "")} for ag in ag_list[:20]],
            raw={
                "action_group_count": total_ag,
                "has_email_receiver": has_email,
                "has_webhook_receiver": has_webhook,
                "has_automation_receiver": has_logicapp,
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
#  7.  SLO / Availability signals — Service Health + Smart Detection
# ══════════════════════════════════════════════════════════════════

def fetch_availability_signals(subscription_id: str) -> SignalResult:
    """Detect availability-related alert rules (Service Health, Smart Detection).

    Checks:
      - Service Health alerts configured
      - Resource Health alerts configured
      - Smart Detector / availability alert rules
    This tells us: do they operate services or just host resources?
    """
    start = time.perf_counter_ns()
    signal_name = "monitor:availability_signals"
    try:
        client = build_client(subscription_id=subscription_id)

        # Activity Log alerts (Service Health = ActivityLog alerts with serviceHealth category)
        service_health_alerts = 0
        resource_health_alerts = 0
        smart_detector_alerts = 0
        try:
            data = client.get(
                f"/subscriptions/{subscription_id}/providers/microsoft.insights/activityLogAlerts",
                api_version="2020-10-01",
            )
            alerts = data.get("value", []) or []
            for alert in alerts:
                props = alert.get("properties", {}) or {}
                condition = props.get("condition", {}) or {}
                all_of = condition.get("allOf", []) or []
                for clause in all_of:
                    field_name = (clause.get("field") or "").lower()
                    equals_val = (clause.get("equals") or "").lower()
                    if field_name == "category" and equals_val == "servicehealth":
                        service_health_alerts += 1
                    if field_name == "category" and equals_val == "resourcehealth":
                        resource_health_alerts += 1
        except Exception:
            pass

        # Smart detector alert rules
        try:
            data = client.get(
                f"/subscriptions/{subscription_id}/providers/microsoft.alertsManagement/smartDetectorAlertRules",
                api_version="2021-04-01",
            )
            rules = data.get("value", []) or []
            smart_detector_alerts = len(rules)
        except Exception:
            pass

        checks_passed = 0
        total_checks = 3
        if service_health_alerts > 0:
            checks_passed += 1
        if resource_health_alerts > 0:
            checks_passed += 1
        if smart_detector_alerts > 0:
            checks_passed += 1

        ms = (time.perf_counter_ns() - start) // 1_000_000
        return SignalResult(
            signal_name=signal_name,
            status=SignalStatus.OK,
            items=[],
            raw={
                "service_health_alert_count": service_health_alerts,
                "resource_health_alert_count": resource_health_alerts,
                "smart_detector_alert_count": smart_detector_alerts,
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
