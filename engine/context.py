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
    )

    return asdict(ctx)
