from dataclasses import dataclass, asdict
import json
import os
import subprocess
import requests
from azure.identity import AzureCliCredential


@dataclass
class ExecutionContext:
    tenant_id: str | None
    tenant_display_name: str | None  # e.g. "Contoso"
    tenant_default_domain: str | None  # e.g. "contoso.onmicrosoft.com"
    subscription_ids_visible: list[str]
    subscription_count_visible: int
    subscription_count_total: int     # licence-level total (from Graph or MG)
    coverage_percent: float           # visible / total * 100
    management_group_access: bool
    identity_type: str
    credential_method: str       # e.g. "Azure CLI", "Service Principal", "Managed Identity"
    rbac_highest_role: str       # e.g. "Reader", "Contributor", "Owner"
    rbac_scope: str              # e.g. "Subscription", "Management Group", "Resource Group"


def _get_tenant_from_az_cli() -> dict:
    """Resolve tenant ID, display name, and domain from the active Azure CLI session."""
    try:
        # shell=True needed on Windows where az is a .cmd batch script
        output = subprocess.check_output(
            "az account show --output json",
            shell=True,
            stderr=subprocess.DEVNULL,
        )
        account = json.loads(output)
        return {
            "tenant_id": account.get("tenantId"),
            "tenant_display_name": account.get("tenantDisplayName"),
            "tenant_default_domain": account.get("tenantDefaultDomain"),
        }
    except Exception:
        return {"tenant_id": None, "tenant_display_name": None, "tenant_default_domain": None}


def discover_execution_context(credential: AzureCliCredential) -> dict:
    # List subscriptions via ARM REST API (works with all azure-mgmt-resource versions)
    token = credential.get_token("https://management.azure.com/.default").token
    resp = requests.get(
        "https://management.azure.com/subscriptions?api-version=2022-01-01",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    resp.raise_for_status()
    subs = [
        s["subscriptionId"]
        for s in resp.json().get("value", [])
        if s.get("state") == "Enabled"
    ]

    # Tenant: resolve from active Azure CLI session
    cli_tenant = _get_tenant_from_az_cli()
    tenant_id = cli_tenant.get("tenant_id") or os.getenv("AZURE_TENANT_ID")
    tenant_display_name = cli_tenant.get("tenant_display_name")
    tenant_default_domain = cli_tenant.get("tenant_default_domain")

    identity_type = "service_principal" if os.getenv("AZURE_CLIENT_ID") else "user"

    # ── Credential method ─────────────────────────────────────────
    if os.getenv("AZURE_CLIENT_ID") and os.getenv("AZURE_CLIENT_SECRET"):
        credential_method = "Service Principal"
    elif os.getenv("AZURE_CLIENT_ID") and not os.getenv("AZURE_CLIENT_SECRET"):
        credential_method = "Managed Identity"
    else:
        credential_method = "Azure CLI"

    # ── Management-group access (probe first so RBAC scope can reference it) ─
    mg_access = True
    try:
        from azure.mgmt.managementgroups import ManagementGroupsAPI
        list(ManagementGroupsAPI(credential).management_groups.list())
    except Exception:
        mg_access = False

    # ── RBAC highest role & scope ─────────────────────────────────
    rbac_highest_role = "Unknown"
    rbac_scope = "Subscription" if subs else "Unknown"

    try:
        if subs:
            # Resolve the current principal's object ID so we only inspect
            # *their* role assignments, not every assignment on the subscription.
            principal_id = None
            try:
                me_resp = requests.get(
                    "https://graph.microsoft.com/v1.0/me",
                    headers={
                        "Authorization": "Bearer "
                        + credential.get_token("https://graph.microsoft.com/.default").token
                    },
                    timeout=10,
                )
                if me_resp.ok:
                    principal_id = me_resp.json().get("id")
            except Exception:
                pass  # Graph may not be reachable; fall back to unfiltered

            # Check role assignments on the first visible subscription
            sub_id = subs[0]
            filter_expr = (
                f"assignedTo('{principal_id}')"
                if principal_id
                else "atScope()"
            )
            ra_resp = requests.get(
                f"https://management.azure.com/subscriptions/{sub_id}"
                f"/providers/Microsoft.Authorization/roleAssignments"
                f"?api-version=2022-04-01&$filter={filter_expr}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=15,
            )
            if ra_resp.ok:
                assignments = ra_resp.json().get("value", [])
                # Map role definition IDs to well-known roles
                _WELL_KNOWN = {
                    "acdd72a7-3385-48ef-bd42-f606fba81ae7": "Reader",
                    "b24988ac-6180-42a0-ab88-20f7382dd24c": "Contributor",
                    "8e3af657-a8ff-443c-a75c-2fe8c4bcb635": "Owner",
                }
                _ROLE_RANK = {"Reader": 1, "Contributor": 2, "Owner": 3}
                best_rank = 0
                for ra in assignments:
                    rd_id = (ra.get("properties", {}).get("roleDefinitionId") or "").rsplit("/", 1)[-1]
                    role_name = _WELL_KNOWN.get(rd_id)
                    if role_name and _ROLE_RANK.get(role_name, 0) > best_rank:
                        best_rank = _ROLE_RANK[role_name]
                        rbac_highest_role = role_name
                if best_rank == 0:
                    rbac_highest_role = "Custom"

        # Scope: if MG access, note it
        if mg_access:
            rbac_scope = "Management Group"
    except Exception:
        pass  # best-effort — don't crash on RBAC introspection

    # ── Total subscription count (best-effort via MG root descendants) ─
    total_subs = len(subs)
    try:
        if mg_access:
            mg_resp = requests.get(
                f"https://management.azure.com/providers/Microsoft.Management"
                f"/managementGroups/{tenant_id}/descendants"
                f"?api-version=2021-04-01",
                headers={"Authorization": f"Bearer {token}"},
                timeout=20,
            )
            if mg_resp.ok:
                descendants = mg_resp.json().get("value", [])
                total_subs = sum(
                    1 for d in descendants
                    if (d.get("type") or "").endswith("/subscriptions")
                )
                total_subs = max(total_subs, len(subs))
    except Exception:
        pass

    coverage = round(len(subs) / max(total_subs, 1) * 100, 1)

    ctx = ExecutionContext(
        tenant_id=tenant_id,
        tenant_display_name=tenant_display_name,
        tenant_default_domain=tenant_default_domain,
        subscription_ids_visible=subs,
        subscription_count_visible=len(subs),
        subscription_count_total=total_subs,
        coverage_percent=coverage,
        management_group_access=mg_access,
        identity_type=identity_type,
        credential_method=credential_method,
        rbac_highest_role=rbac_highest_role,
        rbac_scope=rbac_scope,
    )

    return asdict(ctx)
