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
from signals.providers.storage import fetch_storage_posture
from signals.providers.keyvault import fetch_keyvault_posture
from signals.providers.private_endpoints import fetch_private_endpoint_coverage
from signals.providers.nsg_coverage import fetch_nsg_coverage
from signals.providers.resource_locks import fetch_resource_locks
from signals.providers.rbac import fetch_rbac_hygiene
from signals.providers.app_services import fetch_app_service_posture
from signals.providers.sql import fetch_sql_posture
from signals.providers.containers import fetch_aks_posture, fetch_acr_posture
from signals.providers.backup import fetch_backup_coverage
from signals.providers.entra_logs import fetch_entra_log_availability, fetch_pim_usage
from signals.providers.identity_graph import (
    fetch_pim_maturity,
    fetch_breakglass_validation,
    fetch_sp_owner_risk,
    fetch_admin_ca_coverage,
)
from signals.providers.monitor_topology import fetch_workspace_topology
from signals.providers.activity_log import fetch_activity_log_analysis
from signals.providers.alert_coverage import (
    fetch_alert_action_mapping,
    fetch_action_group_coverage,
    fetch_availability_signals,
)
from signals.providers.change_tracking import fetch_change_tracking
from signals.providers.cost_management import (
    fetch_cost_management_posture,
    fetch_cost_forecast_accuracy,
    fetch_idle_resources,
)
from signals.providers.network_watcher import fetch_network_watcher_posture
from signals.providers.update_manager import fetch_update_manager_posture


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

    # ── Posture / Coverage signals (new) ──────────────────────────
    # Data & PaaS protection
    "resource_graph:storage_posture":     _rg_provider(fetch_storage_posture),
    "resource_graph:keyvault_posture":    _rg_provider(fetch_keyvault_posture),
    "resource_graph:sql_posture":         _rg_provider(fetch_sql_posture),
    "resource_graph:app_service_posture": _rg_provider(fetch_app_service_posture),
    "resource_graph:acr_posture":         _rg_provider(fetch_acr_posture),
    "resource_graph:aks_posture":         _rg_provider(fetch_aks_posture),

    # Networking / Security coverage
    "resource_graph:private_endpoints":   _rg_provider(fetch_private_endpoint_coverage),
    "resource_graph:nsg_coverage":        _rg_provider(fetch_nsg_coverage),
    "resource_graph:resource_locks":      _rg_provider(fetch_resource_locks),

    # Resilience
    "resource_graph:backup_coverage":     _rg_provider(fetch_backup_coverage),

    # Identity / RBAC
    "identity:rbac_hygiene":              _rg_provider(fetch_rbac_hygiene),

    # ── New signal categories ─────────────────────────────────────
    # Identity — Entra ID logs & PIM
    "identity:entra_log_availability":    _sub_provider(fetch_entra_log_availability),
    "identity:pim_usage":                 _sub_provider(fetch_pim_usage),
    "identity:pim_maturity":              _sub_provider(fetch_pim_maturity),
    "identity:breakglass_validation":     _sub_provider(fetch_breakglass_validation),
    "identity:sp_owner_risk":             _rg_provider(fetch_sp_owner_risk),
    "identity:admin_ca_coverage":         _sub_provider(fetch_admin_ca_coverage),

    # Management / Monitor
    "monitor:workspace_topology":         _sub_provider(fetch_workspace_topology),
    "monitor:activity_log_analysis":      _sub_provider(fetch_activity_log_analysis),
    "monitor:alert_action_mapping":       _rg_provider(fetch_alert_action_mapping),
    "monitor:action_group_coverage":      _sub_provider(fetch_action_group_coverage),
    "monitor:availability_signals":       _sub_provider(fetch_availability_signals),
    "monitor:change_tracking":            _sub_provider(fetch_change_tracking),

    # Cost Management
    "cost:management_posture":            _sub_provider(fetch_cost_management_posture),
    "cost:forecast_accuracy":             _sub_provider(fetch_cost_forecast_accuracy),
    "cost:idle_resources":                _rg_provider(fetch_idle_resources),

    # Network Watcher
    "network:watcher_posture":            _sub_provider(fetch_network_watcher_posture),

    # Update Manager
    "manage:update_manager":              _sub_provider(fetch_update_manager_posture),
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
