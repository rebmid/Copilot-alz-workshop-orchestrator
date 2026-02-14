"""Signal registry — maps signal names to provider functions.

Controls never call Azure directly. They request signals by name.
The registry handles dispatch, caching, and consistent evidence formatting.
"""
from __future__ import annotations

from typing import Any, Callable

from signals.types import EvalScope, SignalResult, SignalStatus
from signals.cache import SignalCache

# ── Provider imports ──────────────────────────────────────────────
from signals.providers.resource_graph import (
    fetch_azure_firewalls,
    fetch_vnets,
    fetch_public_ips,
    fetch_route_tables,
    fetch_nsg_list,
)
from signals.providers.management_groups import fetch_mg_hierarchy
from signals.providers.policy import fetch_policy_assignments, fetch_policy_compliance
from signals.providers.defender import fetch_defender_pricings, fetch_secure_score
from signals.providers.diagnostics import fetch_diagnostics_coverage


# Type: (scope) -> SignalResult
# Each provider receives the scope and extracts what it needs.
ProviderFn = Callable[[EvalScope], SignalResult]


def _rg_provider(fetch_fn: Callable) -> ProviderFn:
    """Wrap a Resource Graph fetch that needs subscription list."""
    def _inner(scope: EvalScope) -> SignalResult:
        subs = scope.subscription_ids
        if not subs:
            return SignalResult(
                signal_name="",
                status=SignalStatus.NOT_AVAILABLE,
                error_msg="No subscriptions in scope",
            )
        return fetch_fn(subs)
    return _inner


def _sub_provider(fetch_fn: Callable) -> ProviderFn:
    """Wrap a provider that needs a single subscription_id."""
    def _inner(scope: EvalScope) -> SignalResult:
        sub = scope.subscription_ids[0] if scope.subscription_ids else None
        if not sub:
            return SignalResult(
                signal_name="",
                status=SignalStatus.NOT_AVAILABLE,
                error_msg="No subscriptions in scope",
            )
        return fetch_fn(sub)
    return _inner


def _mg_provider(scope: EvalScope) -> SignalResult:
    sub = scope.subscription_ids[0] if scope.subscription_ids else None
    return fetch_mg_hierarchy(subscription_id=sub)


def _diag_provider(scope: EvalScope) -> SignalResult:
    sub = scope.subscription_ids[0] if scope.subscription_ids else None
    if not sub:
        return SignalResult(
            signal_name="monitor:diag_coverage_sample",
            status=SignalStatus.NOT_AVAILABLE,
            error_msg="No subscriptions in scope",
        )
    return fetch_diagnostics_coverage(sub)


# ── Master registry ──────────────────────────────────────────────
SIGNAL_PROVIDERS: dict[str, ProviderFn] = {
    # Resource Graph signals
    "resource_graph:azure_firewall": _rg_provider(fetch_azure_firewalls),
    "resource_graph:vnets":          _rg_provider(fetch_vnets),
    "resource_graph:public_ips":     _rg_provider(fetch_public_ips),
    "resource_graph:route_tables":   _rg_provider(fetch_route_tables),
    "resource_graph:nsgs":           _rg_provider(fetch_nsg_list),

    # ARM / Management Groups
    "arm:mg_hierarchy":              _mg_provider,

    # Policy
    "policy:assignments":            _sub_provider(fetch_policy_assignments),
    "policy:compliance_summary":     _sub_provider(fetch_policy_compliance),

    # Defender
    "defender:pricings":             _sub_provider(fetch_defender_pricings),
    "defender:secure_score":         _sub_provider(fetch_secure_score),

    # Diagnostics / Monitoring
    "monitor:diag_coverage_sample":  _diag_provider,
}


class SignalBus:
    """
    Fetch signals by name with automatic caching.
    If 10 controls require "arm:mg_hierarchy", it's queried once.
    """

    def __init__(self, cache: SignalCache | None = None):
        self.cache = cache or SignalCache()
        self.events: list[dict[str, Any]] = []  # for streaming

    def fetch(
        self,
        signal_name: str,
        scope: EvalScope,
        *,
        freshness_seconds: int | None = None,
    ) -> SignalResult:
        """Fetch a signal, returning from cache if fresh."""
        scope_dict = {
            "tenant_id": scope.tenant_id,
            "mg_id": scope.management_group_id,
            "subs": sorted(scope.subscription_ids),
            "rg": scope.resource_group,
        }

        # Check cache first
        cached = self.cache.get(signal_name, scope_dict, freshness_seconds=freshness_seconds)
        if cached is not None:
            self._emit("signal_returned", signal_name, cache_hit=True, ms=0)
            return cached

        # Fetch from provider
        provider = SIGNAL_PROVIDERS.get(signal_name)
        if provider is None:
            result = SignalResult(
                signal_name=signal_name,
                status=SignalStatus.ERROR,
                error_msg=f"Unknown signal: {signal_name}",
            )
            return result

        self._emit("signal_requested", signal_name)
        result = provider(scope)
        result.signal_name = signal_name  # ensure consistent naming

        # Cache it
        self.cache.put(signal_name, scope_dict, result)
        self._emit("signal_returned", signal_name, cache_hit=False, ms=result.duration_ms)

        return result

    def fetch_many(
        self,
        signal_names: list[str],
        scope: EvalScope,
    ) -> dict[str, SignalResult]:
        """Fetch multiple signals. Returns {name: result}."""
        return {name: self.fetch(name, scope) for name in signal_names}

    def _emit(self, event_type: str, signal_name: str, **kwargs: Any) -> None:
        self.events.append({"type": event_type, "signal": signal_name, **kwargs})

    def reset_events(self) -> list[dict[str, Any]]:
        events = self.events.copy()
        self.events.clear()
        return events
