"""Management group hierarchy signal provider."""
from __future__ import annotations

import time
from typing import Any

from signals.types import SignalResult, SignalStatus
from collectors.azure_client import build_client
from collectors.management_groups import (
    collect_management_group_hierarchy,
    discover_management_group_scope,
)


def fetch_mg_hierarchy(subscription_id: str | None = None) -> SignalResult:
    """
    Discover root MG and fetch full hierarchy with subscription placement.
    Returns everything the governance evaluators need.
    """
    start = time.perf_counter_ns()
    signal_name = "arm:mg_hierarchy"

    try:
        client = build_client(subscription_id=subscription_id)
        scope = discover_management_group_scope(client)

        if scope.get("mode") != "mg" or not scope.get("root_mg_id"):
            ms = (time.perf_counter_ns() - start) // 1_000_000
            return SignalResult(
                signal_name=signal_name,
                status=SignalStatus.NOT_AVAILABLE,
                error_msg=scope.get("reason", "MG not accessible"),
                raw=scope,
                duration_ms=ms,
            )

        mg_data = collect_management_group_hierarchy(client, scope["root_mg_id"])
        ms = (time.perf_counter_ns() - start) // 1_000_000

        return SignalResult(
            signal_name=signal_name,
            status=SignalStatus.OK,
            items=[mg_data],  # single item = full hierarchy
            raw=mg_data,
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
