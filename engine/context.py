from dataclasses import dataclass, asdict
import json
import os
import subprocess
import requests
from azure.identity import AzureCliCredential


@dataclass
class ExecutionContext:
    tenant_id: str | None
    subscription_ids_visible: list[str]
    subscription_count_visible: int
    management_group_access: bool
    identity_type: str
    credential_method: str       # e.g. "Azure CLI", "Service Principal", "Managed Identity"
    rbac_highest_role: str       # e.g. "Reader", "Contributor", "Owner"
    rbac_scope: str              # e.g. "Subscription", "Management Group", "Resource Group"


def _get_tenant_from_az_cli() -> str | None:
    """Resolve tenant ID from the active Azure CLI session."""
    try:
        output = subprocess.check_output(
            ["az", "account", "show", "--output", "json"],
            stderr=subprocess.DEVNULL
        )
        account = json.loads(output)
        return account.get("tenantId")
    except Exception:
        return None


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
    tenant_id = _get_tenant_from_az_cli()
    if not tenant_id:
        tenant_id = os.getenv("AZURE_TENANT_ID")

    identity_type = "service_principal" if os.getenv("AZURE_CLIENT_ID") else "user"

    # ── Credential method ─────────────────────────────────────────
    if os.getenv("AZURE_CLIENT_ID") and os.getenv("AZURE_CLIENT_SECRET"):
        credential_method = "Service Principal"
    elif os.getenv("AZURE_CLIENT_ID") and not os.getenv("AZURE_CLIENT_SECRET"):
        credential_method = "Managed Identity"
    else:
        credential_method = "Azure CLI"

    # ── RBAC highest role & scope ─────────────────────────────────
    rbac_highest_role = "Unknown"
    rbac_scope = "Subscription" if subs else "Unknown"

    try:
        if subs:
            # Check role assignments on the first visible subscription
            sub_id = subs[0]
            ra_resp = requests.get(
                f"https://management.azure.com/subscriptions/{sub_id}"
                f"/providers/Microsoft.Authorization/roleAssignments"
                f"?api-version=2022-04-01&$filter=atScope()",
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

    mg_access = True
    try:
        from azure.mgmt.managementgroups import ManagementGroupsAPI
        list(ManagementGroupsAPI(credential).management_groups.list())
    except Exception:
        mg_access = False

    ctx = ExecutionContext(
        tenant_id=tenant_id,
        subscription_ids_visible=subs,
        subscription_count_visible=len(subs),
        management_group_access=mg_access,
        identity_type=identity_type,
        credential_method=credential_method,
        rbac_highest_role=rbac_highest_role,
        rbac_scope=rbac_scope,
    )

    return asdict(ctx)
