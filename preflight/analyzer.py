"""Preflight & Access Analyzer — probes Azure API surface before scan.

Usage:
    from preflight.analyzer import run_preflight
    result = run_preflight()
    # result["permissions"]       -> {probe_name: bool}
    # result["assessment_impact"] -> [{area, mode, reason}]
    # result["recommended_actions"] -> [str]
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, TypedDict

import requests
from azure.identity import AzureCliCredential

ARM = "https://management.azure.com"


# ── Types ─────────────────────────────────────────────────────────

class ProbeResult(TypedDict):
    ok: bool
    detail: str
    duration_ms: int


class PreflightResult(TypedDict):
    tenant_id: str
    timestamp: str
    permissions: dict[str, bool]
    scope_visibility: dict[str, Any]
    assessment_impact: list[dict[str, str]]
    recommended_actions: list[str]


@dataclass
class AzureContext:
    """Lightweight credential + subscription context for probes."""
    credential: AzureCliCredential
    tenant_id: str | None = None
    subscription_ids: list[str] = field(default_factory=list)
    _token: str | None = None
    _token_expires: float = 0.0

    def token(self) -> str:
        now = time.time()
        if self._token and now < self._token_expires - 60:
            return self._token
        access = self.credential.get_token(f"{ARM}/.default")
        self._token = access.token
        self._token_expires = access.expires_on
        return self._token

    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token()}"}


# ── Probe definitions ─────────────────────────────────────────────

def _probe_management_groups(ctx: AzureContext) -> ProbeResult:
    """Can we list management groups?"""
    start = time.perf_counter_ns()
    try:
        r = requests.get(
            f"{ARM}/providers/Microsoft.Management/managementGroups",
            headers=ctx.headers(),
            params={"api-version": "2021-04-01"},
            timeout=5,
        )
        ms = (time.perf_counter_ns() - start) // 1_000_000
        if r.status_code == 200:
            count = len(r.json().get("value", []))
            return {"ok": True, "detail": f"{count} management group(s) visible", "duration_ms": ms}
        return {"ok": False, "detail": f"HTTP {r.status_code}: {r.reason}", "duration_ms": ms}
    except Exception as e:
        ms = (time.perf_counter_ns() - start) // 1_000_000
        return {"ok": False, "detail": str(e)[:200], "duration_ms": ms}


def _probe_resource_graph(ctx: AzureContext) -> ProbeResult:
    """Can we query Resource Graph?"""
    start = time.perf_counter_ns()
    try:
        body = {
            "subscriptions": ctx.subscription_ids[:5],  # sample
            "query": "Resources | take 1",
            "options": {"resultFormat": "objectArray"},
        }
        r = requests.post(
            f"{ARM}/providers/Microsoft.ResourceGraph/resources",
            headers={**ctx.headers(), "Content-Type": "application/json"},
            params={"api-version": "2022-10-01"},
            json=body,
            timeout=5,
        )
        ms = (time.perf_counter_ns() - start) // 1_000_000
        if r.status_code == 200:
            rows = len(r.json().get("data", []))
            return {"ok": True, "detail": f"Query OK, {rows} row(s)", "duration_ms": ms}
        return {"ok": False, "detail": f"HTTP {r.status_code}: {r.reason}", "duration_ms": ms}
    except Exception as e:
        ms = (time.perf_counter_ns() - start) // 1_000_000
        return {"ok": False, "detail": str(e)[:200], "duration_ms": ms}


def _probe_policy_insights(ctx: AzureContext) -> ProbeResult:
    """Can we read Policy Insights summary?"""
    start = time.perf_counter_ns()
    try:
        # Subscription-level summarize if we have a sub, else tenant-level
        if ctx.subscription_ids:
            path = f"/subscriptions/{ctx.subscription_ids[0]}/providers/Microsoft.PolicyInsights/policyStates/latest/summarize"
        else:
            path = "/providers/Microsoft.PolicyInsights/policyStates/latest/summarize"
        r = requests.post(
            f"{ARM}{path}",
            headers={**ctx.headers(), "Content-Type": "application/json"},
            params={"api-version": "2019-10-01"},
            json={},
            timeout=5,
        )
        ms = (time.perf_counter_ns() - start) // 1_000_000
        if r.status_code == 200:
            return {"ok": True, "detail": "Policy Insights accessible", "duration_ms": ms}
        return {"ok": False, "detail": f"HTTP {r.status_code}: {r.reason}", "duration_ms": ms}
    except Exception as e:
        ms = (time.perf_counter_ns() - start) // 1_000_000
        return {"ok": False, "detail": str(e)[:200], "duration_ms": ms}


def _probe_defender(ctx: AzureContext) -> ProbeResult:
    """Can we read Defender for Cloud pricings?"""
    start = time.perf_counter_ns()
    if not ctx.subscription_ids:
        return {"ok": False, "detail": "No subscriptions in scope", "duration_ms": 0}
    try:
        sub = ctx.subscription_ids[0]
        r = requests.get(
            f"{ARM}/subscriptions/{sub}/providers/Microsoft.Security/pricings",
            headers=ctx.headers(),
            params={"api-version": "2024-01-01"},
            timeout=5,
        )
        ms = (time.perf_counter_ns() - start) // 1_000_000
        if r.status_code == 200:
            count = len(r.json().get("value", []))
            return {"ok": True, "detail": f"{count} Defender plan(s) readable", "duration_ms": ms}
        return {"ok": False, "detail": f"HTTP {r.status_code}: {r.reason}", "duration_ms": ms}
    except Exception as e:
        ms = (time.perf_counter_ns() - start) // 1_000_000
        return {"ok": False, "detail": str(e)[:200], "duration_ms": ms}


def _probe_log_analytics(ctx: AzureContext) -> ProbeResult:
    """Can we list Log Analytics workspaces?"""
    start = time.perf_counter_ns()
    if not ctx.subscription_ids:
        return {"ok": False, "detail": "No subscriptions in scope", "duration_ms": 0}
    try:
        sub = ctx.subscription_ids[0]
        r = requests.get(
            f"{ARM}/subscriptions/{sub}/providers/Microsoft.OperationalInsights/workspaces",
            headers=ctx.headers(),
            params={"api-version": "2022-10-01"},
            timeout=5,
        )
        ms = (time.perf_counter_ns() - start) // 1_000_000
        if r.status_code == 200:
            count = len(r.json().get("value", []))
            return {"ok": True, "detail": f"{count} workspace(s) visible", "duration_ms": ms}
        return {"ok": False, "detail": f"HTTP {r.status_code}: {r.reason}", "duration_ms": ms}
    except Exception as e:
        ms = (time.perf_counter_ns() - start) // 1_000_000
        return {"ok": False, "detail": str(e)[:200], "duration_ms": ms}


def _probe_aad_diagnostics(ctx: AzureContext) -> ProbeResult:
    """Can we read AAD diagnostic settings (Entra log routing)?"""
    start = time.perf_counter_ns()
    try:
        r = requests.get(
            f"{ARM}/providers/microsoft.aadiam/diagnosticSettings",
            headers=ctx.headers(),
            params={"api-version": "2017-04-01"},
            timeout=5,
        )
        ms = (time.perf_counter_ns() - start) // 1_000_000
        if r.status_code == 200:
            count = len(r.json().get("value", []))
            return {"ok": True, "detail": f"{count} AAD diagnostic setting(s)", "duration_ms": ms}
        return {"ok": False, "detail": f"HTTP {r.status_code}: {r.reason}", "duration_ms": ms}
    except Exception as e:
        ms = (time.perf_counter_ns() - start) // 1_000_000
        return {"ok": False, "detail": str(e)[:200], "duration_ms": ms}


def _probe_cost_management(ctx: AzureContext) -> ProbeResult:
    """Can we query Cost Management budgets?"""
    start = time.perf_counter_ns()
    if not ctx.subscription_ids:
        return {"ok": False, "detail": "No subscriptions in scope", "duration_ms": 0}
    try:
        sub = ctx.subscription_ids[0]
        r = requests.get(
            f"{ARM}/subscriptions/{sub}/providers/Microsoft.Consumption/budgets",
            headers=ctx.headers(),
            params={"api-version": "2023-05-01"},
            timeout=5,
        )
        ms = (time.perf_counter_ns() - start) // 1_000_000
        if r.status_code == 200:
            count = len(r.json().get("value", []))
            return {"ok": True, "detail": f"{count} budget(s) visible", "duration_ms": ms}
        return {"ok": False, "detail": f"HTTP {r.status_code}: {r.reason}", "duration_ms": ms}
    except Exception as e:
        ms = (time.perf_counter_ns() - start) // 1_000_000
        return {"ok": False, "detail": str(e)[:200], "duration_ms": ms}


GRAPH = "https://graph.microsoft.com"


def _probe_graph_api(ctx: AzureContext) -> ProbeResult:
    """Can we read Microsoft Graph API (directory roles)?"""
    start = time.perf_counter_ns()
    try:
        graph_token = ctx.credential.get_token(f"{GRAPH}/.default")
        headers = {"Authorization": f"Bearer {graph_token.token}"}
        r = requests.get(
            f"{GRAPH}/v1.0/directoryRoles",
            headers=headers,
            params={"$top": "1"},
            timeout=5,
        )
        ms = (time.perf_counter_ns() - start) // 1_000_000
        if r.status_code == 200:
            count = len(r.json().get("value", []))
            return {"ok": True, "detail": f"Graph API accessible, {count} role(s) sampled", "duration_ms": ms}
        return {"ok": False, "detail": f"HTTP {r.status_code}: {r.reason}", "duration_ms": ms}
    except Exception as e:
        ms = (time.perf_counter_ns() - start) // 1_000_000
        return {"ok": False, "detail": str(e)[:200], "duration_ms": ms}


# ── Probe registry ────────────────────────────────────────────────

PROBES: dict[str, tuple[Any, dict[str, str]]] = {
    "management_groups_read": (
        _probe_management_groups,
        {
            "area": "Governance",
            "mode": "Disabled",
            "reason": "Management group hierarchy not accessible",
            "action": "Grant Management Group Reader at tenant root scope",
        },
    ),
    "resource_graph": (
        _probe_resource_graph,
        {
            "area": "Networking & Resources",
            "mode": "Disabled",
            "reason": "Resource Graph queries will fail",
            "action": "Grant Reader role on target subscriptions",
        },
    ),
    "policy_insights": (
        _probe_policy_insights,
        {
            "area": "Governance",
            "mode": "Estimated",
            "reason": "Policy Insights access missing — compliance data unavailable",
            "action": "Grant Policy Insights Data Reader (or Reader) on subscription scope",
        },
    ),
    "defender_for_cloud": (
        _probe_defender,
        {
            "area": "Security",
            "mode": "Estimated",
            "reason": "Defender for Cloud pricing data not accessible",
            "action": "Grant Security Reader on subscription scope",
        },
    ),
    "log_analytics_reader": (
        _probe_log_analytics,
        {
            "area": "Management & Monitoring",
            "mode": "Estimated",
            "reason": "Log Analytics workspace listing not accessible",
            "action": "Grant Log Analytics Reader on subscription scope",
        },
    ),
    "aad_diagnostics": (
        _probe_aad_diagnostics,
        {
            "area": "Identity",
            "mode": "Estimated",
            "reason": "Entra ID diagnostic settings not accessible — sign-in/audit log routing unknown",
            "action": "Grant Reader on the subscription to list AAD diagnostic settings",
        },
    ),
    "cost_management_reader": (
        _probe_cost_management,
        {
            "area": "Cost Governance",
            "mode": "Estimated",
            "reason": "Cost Management data not accessible — budgets/alerts unknown",
            "action": "Grant Cost Management Reader on subscription scope",
        },
    ),
    "graph_api_reader": (
        _probe_graph_api,
        {
            "area": "Identity",
            "mode": "Estimated",
            "reason": "Microsoft Graph API not accessible — PIM, break-glass, CA coverage unavailable",
            "action": "Grant Directory.Read.All or Global Reader in Entra ID",
        },
    ),
}


# ── Context Builder ───────────────────────────────────────────────

def _get_tenant_from_cli() -> str | None:
    try:
        output = subprocess.check_output(
            ["az", "account", "show", "--output", "json"],
            stderr=subprocess.DEVNULL,
        )
        return json.loads(output).get("tenantId")
    except Exception:
        return os.getenv("AZURE_TENANT_ID")


def _get_subscriptions(ctx: AzureContext) -> list[str]:
    """List enabled subscriptions via ARM REST."""
    try:
        r = requests.get(
            f"{ARM}/subscriptions",
            headers=ctx.headers(),
            params={"api-version": "2022-01-01"},
            timeout=10,
        )
        r.raise_for_status()
        return [
            s["subscriptionId"]
            for s in r.json().get("value", [])
            if s.get("state") == "Enabled"
        ]
    except Exception:
        return []


def build_azure_context(
    *,
    credential: AzureCliCredential | None = None,
    subscription_ids: list[str] | None = None,
) -> AzureContext:
    """Build an AzureContext, discovering tenant + subs if not provided."""
    cred = credential or AzureCliCredential(process_timeout=30)
    tenant = _get_tenant_from_cli()

    ctx = AzureContext(credential=cred, tenant_id=tenant)

    if subscription_ids:
        ctx.subscription_ids = subscription_ids
    else:
        ctx.subscription_ids = _get_subscriptions(ctx)

    return ctx


# ── Main Entry Point ──────────────────────────────────────────────

def run_preflight(
    ctx: AzureContext | None = None,
    *,
    verbose: bool = False,
) -> PreflightResult:
    """
    Run all capability probes and return a structured preflight report.

    Each probe has a hard 5s timeout and is independent. Failures in one
    probe do not affect others.
    """
    if ctx is None:
        ctx = build_azure_context()

    if verbose:
        print(f"  Preflight: tenant={ctx.tenant_id}, subs={len(ctx.subscription_ids)}")

    permissions: dict[str, bool] = {}
    probe_details: dict[str, ProbeResult] = {}
    assessment_impact: list[dict[str, str]] = []
    recommended_actions: list[str] = []

    total_start = time.perf_counter_ns()

    for probe_name, (probe_fn, impact_meta) in PROBES.items():
        if verbose:
            print(f"    Probing {probe_name} …", end=" ", flush=True)

        result = probe_fn(ctx)
        permissions[probe_name] = result["ok"]
        probe_details[probe_name] = result

        if verbose:
            status = "✓" if result["ok"] else "✗"
            print(f"{status}  ({result['duration_ms']}ms) {result['detail']}")

        if not result["ok"]:
            assessment_impact.append({
                "area": impact_meta["area"],
                "mode": impact_meta["mode"],
                "reason": impact_meta["reason"],
            })
            recommended_actions.append(impact_meta["action"])

    total_ms = (time.perf_counter_ns() - total_start) // 1_000_000

    # ── Scope visibility summary ──────────────────────────────
    scope_visibility: dict[str, Any] = {
        "tenant_id": ctx.tenant_id,
        "subscriptions_count": len(ctx.subscription_ids),
        "subscriptions": ctx.subscription_ids[:20],  # cap display
        "probes_passed": sum(1 for v in permissions.values() if v),
        "probes_total": len(PROBES),
        "total_duration_ms": total_ms,
        "probe_details": probe_details,
    }

    return PreflightResult(
        tenant_id=ctx.tenant_id or "(unknown)",
        timestamp=datetime.now(timezone.utc).isoformat(),
        permissions=permissions,
        scope_visibility=scope_visibility,
        assessment_impact=assessment_impact,
        recommended_actions=recommended_actions,
    )


# ── CLI helper ────────────────────────────────────────────────────

def print_preflight_report(result: PreflightResult) -> None:
    """Pretty-print a preflight report to stdout."""
    print("\n╔══════════════════════════════════════════════╗")
    print("║         Preflight & Access Analyzer          ║")
    print("╚══════════════════════════════════════════════╝")
    print(f"  Tenant:  {result['tenant_id']}")
    print(f"  Time:    {result['timestamp']}")

    sv = result["scope_visibility"]
    print(f"  Subscriptions: {sv['subscriptions_count']}")
    print(f"  Probes:  {sv['probes_passed']}/{sv['probes_total']} passed "
          f"({sv['total_duration_ms']}ms total)")

    print("\n  ── Permission Probes ──────────────────────")
    details = sv.get("probe_details", {})
    for name, ok in result["permissions"].items():
        icon = "✓" if ok else "✗"
        detail = details.get(name, {}).get("detail", "")
        ms = details.get(name, {}).get("duration_ms", 0)
        print(f"    {icon} {name:<30s} {ms:>4d}ms  {detail}")

    if result["assessment_impact"]:
        print("\n  ── Assessment Impact ─────────────────────")
        for imp in result["assessment_impact"]:
            print(f"    ⚠ {imp['area']:24s} [{imp['mode']}]  {imp['reason']}")

    if result["recommended_actions"]:
        print("\n  ── Recommended Actions ───────────────────")
        for i, action in enumerate(result["recommended_actions"], 1):
            print(f"    {i}. {action}")

    if not result["assessment_impact"]:
        print("\n  ✓ All probes passed — full assessment capability available.")

    print()


# ── Standalone runner ─────────────────────────────────────────────

if __name__ == "__main__":
    report = run_preflight(verbose=True)
    print_preflight_report(report)

    # Optionally dump JSON
    out_dir = os.path.join(os.path.dirname(__file__), "out")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "preflight.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"  Saved to {out_path}")
