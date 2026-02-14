# collectors/policy.py
from __future__ import annotations
from typing import Any, Dict, List, Optional
from collectors.azure_client import AzureClient

ASSIGN_API = "2022-06-01"
STATE_API = "2019-10-01"

def collect_policy_assignments(client: AzureClient, scope: str) -> Dict[str, Any]:
    """
    scope examples:
      /subscriptions/<subId>
      /providers/Microsoft.Management/managementGroups/<mgId>
    """
    data = client.get(f"{scope}/providers/Microsoft.Authorization/policyAssignments", api_version=ASSIGN_API)
    items = data.get("value", []) or []

    initiative = 0
    policy = 0
    unknown = 0

    for a in items:
        props = a.get("properties", {}) or {}
        pid = (props.get("policyDefinitionId") or "").lower()
        if "/policysetdefinitions/" in pid:
            initiative += 1
        elif "/policydefinitions/" in pid:
            policy += 1
        else:
            unknown += 1

    return {
        "scope": scope,
        "total": len(items),
        "initiative": initiative,
        "policy": policy,
        "unknown": unknown
    }

def collect_policy_state_summary(client: AzureClient, scope: str) -> Dict[str, Any]:
    """
    Policy Insights state summary.
    NOTE: In some tenants/subscriptions, you may get empty summaries depending on registrations and access.
    """
    data = client.post(f"{scope}/providers/Microsoft.PolicyInsights/policyStates/latest/summarize", api_version=STATE_API)

    # Try to interpret summarize structure
    # The response typically includes "value": [{"results": {"nonCompliantResources": ..}}]
    value = data.get("value", []) or []
    if not value:
        return {
            "scope": scope,
            "status": "NotAvailable",
            "reason": "Policy state summary returned no data.",
            "compliant_resources": 0,
            "noncompliant_resources": 0,
            "unknown_resources": 0,
            "total_resources": 0,
            "compliance_percent": None
        }

    results = (value[0].get("results") or {}) if isinstance(value[0], dict) else {}
    compliant = results.get("compliantResources", 0) or 0
    noncompliant = results.get("nonCompliantResources", 0) or 0
    total = results.get("totalResources", 0) or (compliant + noncompliant)
    unknown = max(0, total - compliant - noncompliant)

    compliance_percent = None
    if total > 0:
        compliance_percent = round((compliant / total) * 100.0, 1)

    status = "OK" if total > 0 else "NotAvailable"
    reason = None if total > 0 else "Policy state summary returned zero evaluated resources."

    return {
        "scope": scope,
        "status": status,
        "reason": reason,
        "compliant_resources": compliant,
        "noncompliant_resources": noncompliant,
        "unknown_resources": unknown,
        "total_resources": total,
        "compliance_percent": compliance_percent
    }
