"""RBAC hygiene signal provider — owner count, group vs user assignments."""
from __future__ import annotations

import time
from signals.types import SignalResult, SignalStatus


def fetch_rbac_hygiene(subscriptions: list[str]) -> SignalResult:
    """Analyze RBAC role assignments across all subscriptions for hygiene."""
    start = time.perf_counter_ns()
    signal_name = "identity:rbac_hygiene"
    try:
        from azure.identity import AzureCliCredential
        from azure.mgmt.authorization import AuthorizationManagementClient

        credential = AzureCliCredential(process_timeout=30)

        # Aggregate across all subscriptions
        assignments = []
        for sub_id in subscriptions:
            try:
                client = AuthorizationManagementClient(credential, sub_id)
                assignments.extend(client.role_assignments.list_for_subscription())  # type: ignore[attr-defined]
            except Exception:
                pass  # skip inaccessible subs

        total = len(assignments)

        # Classify
        owners = []
        contributors = []
        by_type: dict[str, int] = {"User": 0, "Group": 0, "ServicePrincipal": 0, "Unknown": 0}

        for ra in assignments:
            props = ra.properties if hasattr(ra, "properties") else ra
            principal_type = getattr(props, "principal_type", None) or "Unknown"
            role_def_id = getattr(props, "role_definition_id", "") or ""
            by_type[principal_type] = by_type.get(principal_type, 0) + 1

            # Owner role GUID: 8e3af657-a8ff-443c-a75c-2fe8c4bcb635
            if "8e3af657-a8ff-443c-a75c-2fe8c4bcb635" in role_def_id:
                owners.append({
                    "principal_id": getattr(props, "principal_id", ""),
                    "principal_type": principal_type,
                    "scope": getattr(props, "scope", ""),
                })
            # Contributor GUID: b24988ac-6180-42a0-ab88-20f7382dd24c
            if "b24988ac-6180-42a0-ab88-20f7382dd24c" in role_def_id:
                contributors.append({
                    "principal_id": getattr(props, "principal_id", ""),
                    "principal_type": principal_type,
                })

        user_count = by_type.get("User", 0)
        group_count = by_type.get("Group", 0)
        sp_count = by_type.get("ServicePrincipal", 0)
        group_ratio = round(group_count / total, 4) if total else 0.0

        # Hygiene: good = groups > users, owners < 5, etc.
        compliant_checks = 0
        total_checks = 3
        if len(owners) <= 5:
            compliant_checks += 1
        if group_ratio >= 0.5:
            compliant_checks += 1
        if sp_count > 0:  # managed identities in use
            compliant_checks += 1

        ratio = round(compliant_checks / total_checks, 4)

        ms = (time.perf_counter_ns() - start) // 1_000_000
        return SignalResult(
            signal_name=signal_name,
            status=SignalStatus.OK,
            items=owners[:10],
            raw={
                "total_assignments": total,
                "owner_count": len(owners),
                "contributor_count": len(contributors),
                "by_principal_type": by_type,
                "group_assignment_ratio": group_ratio,
                "coverage": {"applicable": total_checks, "compliant": compliant_checks, "ratio": ratio},
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
