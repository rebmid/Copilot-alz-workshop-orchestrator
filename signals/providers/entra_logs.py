"""Entra ID log availability & PIM usage signal providers.

Signals:
  identity:entra_log_availability — sign-in logs, audit logs, SP sign-ins availability
  identity:pim_usage              — PIM activation events (presence, not config)
"""
from __future__ import annotations

import time
from typing import Any

from signals.types import SignalResult, SignalStatus
from collectors.azure_client import build_client


# ── Entra Log Availability ────────────────────────────────────────

def fetch_entra_log_availability(subscription_id: str) -> SignalResult:
    """Check availability of Entra ID diagnostic log categories.

    Probes for:
      - Sign-in log availability (Entra diagnostic setting targets)
      - Audit log availability
      - Service principal sign-in activity
    We check if Entra ID diagnostic settings exist that route to a Log Analytics workspace.
    """
    start = time.perf_counter_ns()
    signal_name = "identity:entra_log_availability"
    try:
        client = build_client(subscription_id=subscription_id)

        # List diagnostic settings on the Entra ID resource
        # Entra ID diagnostics are at the AAD provider level
        try:
            data = client.get(
                "/providers/microsoft.aadiam/diagnosticSettings",
                api_version="2017-04-01",
            )
            settings = data.get("value", []) or []
        except Exception:
            settings = []

        sign_in_logs = False
        audit_logs = False
        sp_sign_in_logs = False
        workspace_targets: list[str] = []

        for ds in settings:
            props = ds.get("properties", {}) or {}
            workspace_id = props.get("workspaceId", "")
            if workspace_id:
                workspace_targets.append(workspace_id)

            for log_entry in props.get("logs", []):
                cat = (log_entry.get("category") or "").lower()
                enabled = log_entry.get("enabled", False)
                if enabled:
                    if "signin" in cat and "serviceprincipal" not in cat and "managed" not in cat:
                        sign_in_logs = True
                    if "audit" in cat:
                        audit_logs = True
                    if "serviceprincipalsignin" in cat or "serviceprincipal" in cat:
                        sp_sign_in_logs = True

        checks_passed = sum([sign_in_logs, audit_logs, sp_sign_in_logs])
        total_checks = 3
        ratio = round(checks_passed / total_checks, 4)

        ms = (time.perf_counter_ns() - start) // 1_000_000
        return SignalResult(
            signal_name=signal_name,
            status=SignalStatus.OK,
            items=settings[:10],
            raw={
                "diagnostic_settings_count": len(settings),
                "sign_in_logs_enabled": sign_in_logs,
                "audit_logs_enabled": audit_logs,
                "sp_sign_in_logs_enabled": sp_sign_in_logs,
                "workspace_targets": list(set(workspace_targets)),
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


# ── PIM Activation Events ────────────────────────────────────────

def fetch_pim_usage(subscription_id: str) -> SignalResult:
    """Detect PIM activation events (presence) via Activity Log.

    We query the Azure Activity Log for PIM-related operations.
    This detects whether PIM is actively used (activations happening),
    not whether it's configured.
    """
    start = time.perf_counter_ns()
    signal_name = "identity:pim_usage"
    try:
        client = build_client(subscription_id=subscription_id)

        # Query activity log for PIM operations (last 90 days)
        import urllib.parse
        from datetime import datetime, timedelta, timezone

        end = datetime.now(timezone.utc)
        begin = end - timedelta(days=90)
        odata_filter = (
            f"eventTimestamp ge '{begin.strftime('%Y-%m-%dT%H:%M:%SZ')}' "
            f"and eventTimestamp le '{end.strftime('%Y-%m-%dT%H:%M:%SZ')}' "
            f"and resourceProvider eq 'Microsoft.Authorization'"
        )

        try:
            data = client.get(
                f"/subscriptions/{subscription_id}/providers/Microsoft.Insights/eventtypes/management/values",
                api_version="2015-04-01",
                params={"$filter": odata_filter, "$top": "100"},
            )
            events = data.get("value", []) or []
        except Exception:
            events = []

        # Classify PIM-related events
        pim_activations = []
        pim_eligible_assignments = []
        breakglass_candidates = []

        for evt in events:
            op_name = (evt.get("operationName", {}).get("value", "") or
                       evt.get("operationName", "")).lower()
            caller = evt.get("caller", "")

            if "roleeligibilityschedule" in op_name or "roleassignmentschedule" in op_name:
                pim_activations.append({
                    "operation": op_name,
                    "caller": caller,
                    "timestamp": evt.get("eventTimestamp", ""),
                })
            if "elevateaccess" in op_name:
                breakglass_candidates.append({
                    "operation": op_name,
                    "caller": caller,
                    "timestamp": evt.get("eventTimestamp", ""),
                })

        has_pim_activity = len(pim_activations) > 0
        has_breakglass = len(breakglass_candidates) > 0

        # Zero standing access detection: if we see PIM activations but
        # low permanent owner count, that's a strong signal
        checks_passed = 0
        total_checks = 2
        if has_pim_activity:
            checks_passed += 1
        if has_breakglass:
            checks_passed += 1

        ratio = round(checks_passed / total_checks, 4)

        ms = (time.perf_counter_ns() - start) // 1_000_000
        return SignalResult(
            signal_name=signal_name,
            status=SignalStatus.OK,
            items=pim_activations[:20],
            raw={
                "pim_activation_count": len(pim_activations),
                "has_pim_activity": has_pim_activity,
                "breakglass_elevations": len(breakglass_candidates),
                "has_breakglass_activity": has_breakglass,
                "activity_events_sampled": len(events),
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
