import requests
from collectors.auth import get_arm_token

POLICY_INSIGHTS_API = "2019-10-01"
AUTHZ_API = "2022-06-01"

def _arm_get(url: str):
    token = get_arm_token()
    r = requests.get(url, headers={"Authorization": f"Bearer {token}"})
    r.raise_for_status()
    return r.json()

def _arm_post(url: str, body: dict):
    token = get_arm_token()
    r = requests.post(url, json=body, headers={"Authorization": f"Bearer {token}"})
    r.raise_for_status()
    return r.json()

def collect_policy_compliance_summary(scope: str):
    """
    scope examples:
      /subscriptions/<subId>
      /providers/Microsoft.Management/managementGroups/<mgId>
    """
    url = f"https://management.azure.com{scope}/providers/Microsoft.PolicyInsights/policyStates/latest/summarize?api-version={POLICY_INSIGHTS_API}"

    # empty body is fine; you can add filters later
    data = _arm_post(url, body={})

    # Pull a simple summary
    summary = {"scope": scope}
    try:
        # data.summary.results[*].nonCompliantResources / compliantResources
        results = (data.get("summary", {}) or {}).get("results", []) or []
        noncompliant = 0
        compliant = 0
        unknown = 0
        for r in results:
            noncompliant += int(r.get("nonCompliantResources", 0) or 0)
            compliant += int(r.get("compliantResources", 0) or 0)
            unknown += int(r.get("unknownResources", 0) or 0)

        total = noncompliant + compliant + unknown
        compliance_pct = round((compliant / total) * 100, 1) if total else None

        summary.update({
            "compliant_resources": compliant,
            "noncompliant_resources": noncompliant,
            "unknown_resources": unknown,
            "total_resources": total,
            "compliance_percent": compliance_pct
        })
    except Exception:
        summary.update({"compliance_percent": None})

    return {"raw": data, "summary": summary}

def collect_policy_assignments(scope: str):
    """
    Lists policy assignments at a scope.
    NOTE: For MG scope, you'd use the same endpoint with mg scope path.
    """
    url = f"https://management.azure.com{scope}/providers/Microsoft.Authorization/policyAssignments?api-version={AUTHZ_API}"
    data = _arm_get(url)
    assignments = data.get("value", []) or []

    initiative = []
    policy = []
    unknown = []

    for a in assignments:
        props = a.get("properties", {}) or {}
        pdid = (props.get("policyDefinitionId") or "").lower()

        # Initiative = policySetDefinitions
        if "/policysetdefinitions/" in pdid:
            initiative.append(a)
        elif "/policydefinitions/" in pdid:
            policy.append(a)
        else:
            unknown.append(a)

    return {
        "scope": scope,
        "assignments": assignments,
        "counts": {
            "total": len(assignments),
            "initiative": len(initiative),
            "policy": len(policy),
            "unknown": len(unknown)
        }
    }
