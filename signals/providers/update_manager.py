"""Update Manager signal provider.

Detects:
  - Azure Update Manager enabled (maintenance configurations)
  - Machine guest configuration assignments
  - Patch assessment status via Resource Graph
  - VM → maintenance configuration assignment join

This yields a **patch posture** signal for CAF Manage.
"""
from __future__ import annotations

import time
from typing import Any

from signals.types import SignalResult, SignalStatus
from collectors.azure_client import build_client


def fetch_update_manager_posture(subscription_id: str) -> SignalResult:
    """Analyze Azure Update Manager and patch posture.

    Checks for maintenance configurations, guest configuration
    assignments, and per-machine patch assessment summary.
    """
    start = time.perf_counter_ns()
    signal_name = "manage:update_manager"
    try:
        client = build_client(subscription_id=subscription_id)

        # 1. Maintenance configurations
        maintenance_configs: list[dict[str, Any]] = []
        try:
            data = client.get(
                f"/subscriptions/{subscription_id}/providers/Microsoft.Maintenance/maintenanceConfigurations",
                api_version="2023-10-01-preview",
            )
            maintenance_configs = data.get("value", []) or []
        except Exception:
            pass

        mc_details = []
        for mc in maintenance_configs:
            props = mc.get("properties", {}) or {}
            mc_details.append({
                "name": mc.get("name", ""),
                "location": mc.get("location", ""),
                "maintenanceScope": props.get("maintenanceScope", ""),
                "recurEvery": (props.get("maintenanceWindow", {}) or {}).get("recurEvery", ""),
            })

        # 2. Guest configuration assignments (subset: machine-config policy)
        guest_assignments: list[dict[str, Any]] = []
        try:
            data = client.get(
                f"/subscriptions/{subscription_id}/providers/Microsoft.GuestConfiguration/guestConfigurationAssignments",
                api_version="2022-01-25",
            )
            guest_assignments = data.get("value", []) or []
        except Exception:
            pass

        compliant_assignments = 0
        for ga in guest_assignments:
            props = ga.get("properties", {}) or {}
            status = (props.get("complianceStatus") or "").lower()
            if status == "compliant":
                compliant_assignments += 1

        # 3. Patch assessment via Resource Graph (quick probe)
        assessed_machines = 0
        pending_patches_critical = 0
        try:
            from collectors.resource_graph import query_resource_graph
            query = (
                "patchassessmentresources "
                "| where type =~ 'microsoft.compute/virtualmachines/patchassessmentresults' "
                "| extend status = properties.status, "
                "  criticalCount = toint(properties.availablePatchCountByClassification.critical) "
                "| summarize machines=dcount(id), totalCritical=sum(criticalCount)"
            )
            result = query_resource_graph(query, [subscription_id])
            rows = [r for r in (result or []) if isinstance(r, dict)]
            if rows:
                row = rows[0]
                assessed_machines = row.get("machines", 0) or 0
                pending_patches_critical = row.get("totalCritical", 0) or 0
        except Exception:
            pass

        # 4. VM → maintenance configuration assignment join (Resource Graph)
        total_vms = 0
        vms_with_maintenance = 0
        try:
            from collectors.resource_graph import query_resource_graph as _rg_query
            vm_mc_query = (
                "resources "
                "| where type == 'microsoft.compute/virtualmachines' "
                "| summarize totalVMs=count()"
            )
            vm_result = _rg_query(vm_mc_query, [subscription_id])
            vm_rows = [r for r in (vm_result or []) if isinstance(r, dict)]
            if vm_rows:
                total_vms = vm_rows[0].get("totalVMs", 0) or 0

            mc_assign_query = (
                "maintenanceresources "
                "| where type == 'microsoft.maintenance/configurationassignments' "
                "| where properties.resourceId contains 'microsoft.compute/virtualmachines' "
                "| distinct tostring(properties.resourceId)"
            )
            mc_result = _rg_query(mc_assign_query, [subscription_id])
            mc_rows = [r for r in (mc_result or []) if isinstance(r, dict)]
            vms_with_maintenance = len(mc_rows)
        except Exception:
            pass

        vm_maintenance_ratio = (
            round(vms_with_maintenance / total_vms, 4) if total_vms > 0 else 0.0
        )

        # Score patch/governance maturity
        checks_passed = 0
        total_checks = 5
        if len(maintenance_configs) > 0:
            checks_passed += 1
        if len(guest_assignments) > 0:
            checks_passed += 1
        if compliant_assignments > 0:
            checks_passed += 1
        if assessed_machines > 0:
            checks_passed += 1
        if vm_maintenance_ratio >= 0.8:
            checks_passed += 1          # ≥80% VMs under maintenance config

        ratio = round(checks_passed / total_checks, 4)

        ms = (time.perf_counter_ns() - start) // 1_000_000
        return SignalResult(
            signal_name=signal_name,
            status=SignalStatus.OK,
            items=mc_details[:10],
            raw={
                "maintenance_config_count": len(maintenance_configs),
                "guest_assignment_count": len(guest_assignments),
                "compliant_assignments": compliant_assignments,
                "assessed_machines": assessed_machines,
                "pending_patches_critical": pending_patches_critical,
                "total_vms": total_vms,
                "vms_with_maintenance_config": vms_with_maintenance,
                "vm_maintenance_ratio": vm_maintenance_ratio,
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
