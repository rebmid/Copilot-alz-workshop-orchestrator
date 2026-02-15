"""Identity deep-analysis signal providers (Microsoft Graph + Resource Graph).

Signals:
  identity:pim_maturity          — PIM eligible % for privileged roles (zero standing access)
  identity:breakglass_validation — Emergency access account health
  identity:sp_owner_risk         — Service principals with Owner role
  identity:admin_ca_coverage     — Conditional Access + MFA coverage for admin roles

Prerequisites:
  Azure CLI must have Graph API consent (Global Reader or Privileged Role Reader).
"""
from __future__ import annotations

import time
from typing import Any

from signals.types import SignalResult, SignalStatus
from collectors.azure_client import build_graph_client, build_client


# ── Privileged roles we care about ────────────────────────────────
_PRIVILEGED_ROLE_TEMPLATES = {
    "62e90394-69f5-4237-9190-012177145e10": "Global Administrator",
    "e8611ab8-c189-46e8-94e1-60213ab1f814": "Privileged Role Administrator",
}

_PRIVILEGED_ARM_ROLES = {"Owner", "User Access Administrator"}


# ══════════════════════════════════════════════════════════════════
#  1.  PIM Maturity  — eligible / total for privileged roles
# ══════════════════════════════════════════════════════════════════

def fetch_pim_maturity(subscription_id: str) -> SignalResult:
    """Compute PIM maturity: eligible vs permanent assignments for privileged roles.

    Result.raw includes:
      eligible_count, active_permanent_count, pim_coverage_ratio,
      role_breakdown: {roleName: {eligible, permanent}}
    """
    start = time.perf_counter_ns()
    signal_name = "identity:pim_maturity"
    try:
        graph = build_graph_client()

        # Eligible role assignments (PIM-activated)
        eligible: list[dict[str, Any]] = []
        try:
            eligible = graph.get_all(
                "/roleManagement/directory/roleEligibilityScheduleInstances",
            )
        except Exception:
            pass

        # Active / permanent role assignments
        active: list[dict[str, Any]] = []
        try:
            active = graph.get_all(
                "/roleManagement/directory/roleAssignmentScheduleInstances",
            )
        except Exception:
            pass

        # Classify by role
        role_breakdown: dict[str, dict[str, int]] = {}
        for tmpl_id, role_name in _PRIVILEGED_ROLE_TEMPLATES.items():
            role_breakdown[role_name] = {"eligible": 0, "permanent": 0}

        for e in eligible:
            tmpl = e.get("roleDefinitionId", "")
            if tmpl in _PRIVILEGED_ROLE_TEMPLATES:
                role_name = _PRIVILEGED_ROLE_TEMPLATES[tmpl]
                role_breakdown[role_name]["eligible"] += 1

        for a in active:
            tmpl = a.get("roleDefinitionId", "")
            assign_type = (a.get("assignmentType") or "").lower()
            if tmpl in _PRIVILEGED_ROLE_TEMPLATES:
                role_name = _PRIVILEGED_ROLE_TEMPLATES[tmpl]
                # "activated" = JIT via PIM; "assigned" = permanent
                if assign_type != "activated":
                    role_breakdown[role_name]["permanent"] += 1

        total_eligible = sum(v["eligible"] for v in role_breakdown.values())
        total_permanent = sum(v["permanent"] for v in role_breakdown.values())
        total_priv = total_eligible + total_permanent
        pim_ratio = round(total_eligible / total_priv, 4) if total_priv > 0 else 0.0

        checks_passed = 0
        total_checks = 3
        if total_eligible > 0:
            checks_passed += 1        # PIM in use
        if total_permanent == 0:
            checks_passed += 1        # Zero standing access
        if pim_ratio >= 0.8:
            checks_passed += 1        # ≥80% eligible

        ratio = round(checks_passed / total_checks, 4)

        ms = (time.perf_counter_ns() - start) // 1_000_000
        return SignalResult(
            signal_name=signal_name,
            status=SignalStatus.OK,
            items=[{"role": k, **v} for k, v in role_breakdown.items()],
            raw={
                "eligible_count": total_eligible,
                "active_permanent_count": total_permanent,
                "pim_coverage_ratio": pim_ratio,
                "role_breakdown": role_breakdown,
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
#  2.  Break-glass account validation
# ══════════════════════════════════════════════════════════════════

def fetch_breakglass_validation(subscription_id: str) -> SignalResult:
    """Validate emergency access (break-glass) accounts.

    Checks:
      1. Accounts exist matching common emergency-access naming patterns
      2. Accounts are excluded from at least one Conditional Access policy
      3. Accounts have recent sign-in activity (tested within 90 days)
    """
    start = time.perf_counter_ns()
    signal_name = "identity:breakglass_validation"
    try:
        graph = build_graph_client()

        # Find candidate break-glass users by naming convention
        _BG_PATTERNS = ["breakglass", "break-glass", "emergency", "bg-"]
        users: list[dict[str, Any]] = []
        try:
            all_users = graph.get_all(
                "/users",
                params={"$select": "id,displayName,userPrincipalName,signInActivity"},
            )
            for u in all_users:
                display = (u.get("displayName") or "").lower()
                upn = (u.get("userPrincipalName") or "").lower()
                if any(p in display or p in upn for p in _BG_PATTERNS):
                    users.append(u)
        except Exception:
            pass

        bg_exists = len(users) > 0

        # Check CA policies for exclusions of candidate accounts
        bg_ids = {u["id"] for u in users}
        excluded_from_ca = False
        try:
            ca_policies = graph.get_all(
                "/identity/conditionalAccess/policies",
            )
            for pol in ca_policies:
                conditions = pol.get("conditions", {}) or {}
                users_cond = conditions.get("users", {}) or {}
                exclude_users = set(users_cond.get("excludeUsers", []))
                if bg_ids & exclude_users:
                    excluded_from_ca = True
                    break
        except Exception:
            pass

        # Recent sign-in activity
        recent_login = False
        from datetime import datetime, timedelta, timezone
        cutoff = datetime.now(timezone.utc) - timedelta(days=90)
        for u in users:
            sia = u.get("signInActivity", {}) or {}
            last = sia.get("lastSignInDateTime", "")
            if last:
                try:
                    dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
                    if dt >= cutoff:
                        recent_login = True
                        break
                except Exception:
                    pass

        checks_passed = sum([bg_exists, excluded_from_ca, recent_login])
        total_checks = 3

        ms = (time.perf_counter_ns() - start) // 1_000_000
        return SignalResult(
            signal_name=signal_name,
            status=SignalStatus.OK,
            items=[{
                "displayName": u.get("displayName", ""),
                "userPrincipalName": u.get("userPrincipalName", ""),
                "lastSignIn": (u.get("signInActivity", {}) or {}).get("lastSignInDateTime", ""),
            } for u in users[:5]],
            raw={
                "breakglass_accounts_found": len(users),
                "bg_exists": bg_exists,
                "excluded_from_ca": excluded_from_ca,
                "recent_login_test": recent_login,
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
#  3.  Service Principals with Owner — attack path indicator
# ══════════════════════════════════════════════════════════════════

def fetch_sp_owner_risk(subscriptions: list[str]) -> SignalResult:
    """Detect service principals assigned Owner role (Resource Graph).

    This is a major attack path indicator.
    """
    start = time.perf_counter_ns()
    signal_name = "identity:sp_owner_risk"
    try:
        from collectors.resource_graph import query_resource_graph
        query = (
            "authorizationresources "
            "| where type == 'microsoft.authorization/roleassignments' "
            "| where properties.roleDefinitionName == 'Owner' "
            "| where properties.principalType == 'ServicePrincipal' "
            "| project principalId=tostring(properties.principalId), "
            "  scope=tostring(properties.scope), "
            "  roleDefinitionId=tostring(properties.roleDefinitionId)"
        )
        result = query_resource_graph(query, subscriptions)
        rows = [r for r in (result or []) if isinstance(r, dict)]

        sp_owner_count = len(rows)
        # Also check for User Access Administrator
        query_uaa = (
            "authorizationresources "
            "| where type == 'microsoft.authorization/roleassignments' "
            "| where properties.roleDefinitionName == 'User Access Administrator' "
            "| where properties.principalType == 'ServicePrincipal' "
            "| project principalId=tostring(properties.principalId), "
            "  scope=tostring(properties.scope)"
        )
        result_uaa = query_resource_graph(query_uaa, subscriptions)
        rows_uaa = [r for r in (result_uaa or []) if isinstance(r, dict)]
        sp_uaa_count = len(rows_uaa)

        checks_passed = 0
        total_checks = 2
        if sp_owner_count == 0:
            checks_passed += 1
        if sp_uaa_count == 0:
            checks_passed += 1

        ms = (time.perf_counter_ns() - start) // 1_000_000
        return SignalResult(
            signal_name=signal_name,
            status=SignalStatus.OK,
            items=rows[:20],
            raw={
                "sp_owner_count": sp_owner_count,
                "sp_uaa_count": sp_uaa_count,
                "total_risky_sp_assignments": sp_owner_count + sp_uaa_count,
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
#  4.  Admin Conditional Access / MFA coverage
# ══════════════════════════════════════════════════════════════════

def fetch_admin_ca_coverage(subscription_id: str) -> SignalResult:
    """Check Conditional Access MFA enforcement for admin roles.

    Compares admin directory role membership against CA policies
    that require MFA, ensuring privileged users are protected.
    """
    start = time.perf_counter_ns()
    signal_name = "identity:admin_ca_coverage"
    try:
        graph = build_graph_client()

        # Get admin directory roles and their members
        _ADMIN_ROLE_TEMPLATES = {
            "62e90394-69f5-4237-9190-012177145e10": "Global Administrator",
            "e8611ab8-c189-46e8-94e1-60213ab1f814": "Privileged Role Administrator",
            "f28a1f94-e89e-4e1b-8e7f-c58e0e4f0b3e": "Security Administrator",
        }

        admin_member_ids: set[str] = set()
        admin_role_ids: set[str] = set()
        try:
            roles = graph.get_all("/directoryRoles", api="v1.0")
            for role in roles:
                tmpl = role.get("roleTemplateId", "")
                if tmpl in _ADMIN_ROLE_TEMPLATES:
                    role_id = role["id"]
                    admin_role_ids.add(role_id)
                    try:
                        members = graph.get_all(
                            f"/directoryRoles/{role_id}/members",
                            params={"$select": "id"},
                            api="v1.0",
                        )
                        for m in members:
                            admin_member_ids.add(m.get("id", ""))
                    except Exception:
                        pass
        except Exception:
            pass

        total_admins = len(admin_member_ids)

        # Get CA policies that require MFA
        ca_requires_mfa = False
        admins_covered_by_mfa = 0
        try:
            ca_policies = graph.get_all(
                "/identity/conditionalAccess/policies",
            )
            for pol in ca_policies:
                state = (pol.get("state") or "").lower()
                if state != "enabled":
                    continue

                grant = pol.get("grantControls", {}) or {}
                built_in = [c.lower() for c in (grant.get("builtInControls", []) or [])]
                if "mfa" not in built_in:
                    continue

                # Does this policy target admin roles?
                conditions = pol.get("conditions", {}) or {}
                users_cond = conditions.get("users", {}) or {}
                include_roles = set(users_cond.get("includeRoles", []))
                include_all = "all" in [str(u).lower() for u in users_cond.get("includeUsers", [])]
                exclude_users = set(users_cond.get("excludeUsers", []))

                if include_all or (include_roles & set(_ADMIN_ROLE_TEMPLATES.keys())):
                    ca_requires_mfa = True
                    admins_covered_by_mfa = total_admins - len(admin_member_ids & exclude_users)
                    break
        except Exception:
            pass

        coverage_ratio = (
            round(admins_covered_by_mfa / total_admins, 4) if total_admins > 0 else 0.0
        )

        checks_passed = 0
        total_checks = 3
        if total_admins > 0:
            checks_passed += 1          # admins enumerable
        if ca_requires_mfa:
            checks_passed += 1          # MFA policy exists
        if coverage_ratio >= 0.9:
            checks_passed += 1          # ≥90% covered

        ms = (time.perf_counter_ns() - start) // 1_000_000
        return SignalResult(
            signal_name=signal_name,
            status=SignalStatus.OK,
            items=[],
            raw={
                "total_admin_members": total_admins,
                "admin_roles_checked": list(_ADMIN_ROLE_TEMPLATES.values()),
                "ca_mfa_policy_exists": ca_requires_mfa,
                "admins_covered_by_mfa": admins_covered_by_mfa,
                "mfa_coverage_ratio": coverage_ratio,
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
