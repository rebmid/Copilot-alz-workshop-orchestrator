"""Backup coverage signal provider — VM backup status."""
from __future__ import annotations

from signals.types import SignalResult, SignalStatus
from signals.providers.resource_graph import _query_rg


def fetch_backup_coverage(subscriptions: list[str]) -> SignalResult:
    """Check VM backup status via Recovery Services vaults and backup items."""
    # Get all VMs
    vm_query = """
    Resources
    | where type =~ 'microsoft.compute/virtualmachines'
    | project name, resourceGroup, location, id, vmId=properties.vmId
    """
    vm_r = _query_rg(vm_query, subscriptions)

    if vm_r.status != SignalStatus.OK:
        vm_r.signal_name = "resource_graph:backup_coverage"
        return vm_r

    vms = vm_r.items or []
    total_vms = len(vms)

    # Get all protected VMs via Recovery Services
    backup_query = """
    RecoveryServicesResources
    | where type =~ 'microsoft.recoveryservices/vaults/backupfabrics/protectioncontainers/protecteditems'
    | extend sourceId = tostring(properties.sourceResourceId),
             status   = tostring(properties.protectionStatus),
             health   = tostring(properties.healthStatus)
    | project sourceId, status, health
    """
    backup_r = _query_rg(backup_query, subscriptions)
    protected_ids = set()
    if backup_r.status == SignalStatus.OK:
        for item in (backup_r.items or []):
            sid = (item.get("sourceId") or "").lower()
            if sid:
                protected_ids.add(sid)

    # Match VMs to backup
    protected_vms = sum(1 for vm in vms if vm.get("id", "").lower() in protected_ids)
    unprotected = [
        {"name": vm.get("name"), "id": vm.get("id"), "resourceGroup": vm.get("resourceGroup")}
        for vm in vms if vm.get("id", "").lower() not in protected_ids
    ]

    ratio = round(protected_vms / total_vms, 4) if total_vms else 0.0

    return SignalResult(
        signal_name="resource_graph:backup_coverage",
        status=SignalStatus.OK,
        items=unprotected[:20],
        raw={
            "query": "backup_coverage",
            "total_vms": total_vms,
            "protected_vms": protected_vms,
            "coverage": {"applicable": total_vms, "compliant": protected_vms, "ratio": ratio},
            "unprotected_vms": unprotected[:20],
        },
        duration_ms=vm_r.duration_ms + (backup_r.duration_ms if backup_r.status == SignalStatus.OK else 0),
    )
