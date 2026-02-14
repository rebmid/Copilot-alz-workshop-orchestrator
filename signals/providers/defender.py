"""Defender signal providers — pricings + secure score."""
from __future__ import annotations

import time

from signals.types import SignalResult, SignalStatus
from collectors.azure_client import build_client
from collectors.defender import collect_defender_pricings, collect_secure_score


def fetch_defender_pricings(subscription_id: str) -> SignalResult:
    start = time.perf_counter_ns()
    signal_name = "defender:pricings"
    try:
        client = build_client(subscription_id=subscription_id)
        data = collect_defender_pricings(client, subscription_id)
        ms = (time.perf_counter_ns() - start) // 1_000_000
        return SignalResult(
            signal_name=signal_name,
            status=SignalStatus.OK,
            items=data.get("plans", []),
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


def fetch_secure_score(subscription_id: str) -> SignalResult:
    start = time.perf_counter_ns()
    signal_name = "defender:secure_score"
    try:
        client = build_client(subscription_id=subscription_id)
        data = collect_secure_score(client)
        status = SignalStatus.OK if data.get("status") == "OK" else SignalStatus.NOT_AVAILABLE
        ms = (time.perf_counter_ns() - start) // 1_000_000
        return SignalResult(
            signal_name=signal_name,
            status=status,
            items=data.get("scores", []),
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
