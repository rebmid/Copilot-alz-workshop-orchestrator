from dataclasses import dataclass, asdict
import json
import os
import subprocess
from azure.identity import AzureCliCredential
from azure.mgmt.resource.subscriptions import SubscriptionClient

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
    sub_client = SubscriptionClient(credential)
    subs = [s.subscription_id for s in sub_client.subscriptions.list() if s.subscription_id]

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
