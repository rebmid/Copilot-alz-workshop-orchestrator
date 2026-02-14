"""Policy signal providers — assignments + compliance summary."""
from __future__ import annotations

import time

from signals.types import SignalResult, SignalStatus
from collectors.azure_client import build_client
from collectors.policy import collect_policy_assignments, collect_policy_state_summary


def fetch_policy_assignments(subscription_id: str) -> SignalResult:
    start = time.perf_counter_ns()
    signal_name = "policy:assignments"
    try:
        client = build_client(subscription_id=subscription_id)
        scope = f"/subscriptions/{subscription_id}"
        data = collect_policy_assignments(client, scope)
        ms = (time.perf_counter_ns() - start) // 1_000_000
        return SignalResult(
            signal_name=signal_name,
            status=SignalStatus.OK,
            items=[data],
            raw=data,
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


def fetch_policy_compliance(subscription_id: str) -> SignalResult:
    start = time.perf_counter_ns()
    signal_name = "policy:compliance_summary"
    try:
        client = build_client(subscription_id=subscription_id)
        scope = f"/subscriptions/{subscription_id}"
        data = collect_policy_state_summary(client, scope)
        status = SignalStatus.OK if data.get("status") != "NotAvailable" else SignalStatus.NOT_AVAILABLE
        ms = (time.perf_counter_ns() - start) // 1_000_000
        return SignalResult(
            signal_name=signal_name,
            status=status,
            items=[data],
            raw=data,
            error_msg=data.get("reason", "") or "",
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
