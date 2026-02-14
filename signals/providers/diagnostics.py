"""Diagnostics coverage signal provider."""
from __future__ import annotations

import time

from signals.types import SignalResult, SignalStatus
from collectors.azure_client import build_client
from collectors.diagnostics import collect_diagnostics_coverage


def fetch_diagnostics_coverage(subscription_id: str, max_resources: int = 200) -> SignalResult:
    start = time.perf_counter_ns()
    signal_name = "monitor:diag_coverage_sample"
    try:
        client = build_client(subscription_id=subscription_id)
        data = collect_diagnostics_coverage(client, subscription_id, max_resources)
        ms = (time.perf_counter_ns() - start) // 1_000_000
        return SignalResult(
            signal_name=signal_name,
            status=SignalStatus.OK,
            items=data.get("top_missing_types", []),
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
