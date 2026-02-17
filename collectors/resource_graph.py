from azure.identity import AzureCliCredential
from azure.mgmt.resourcegraph import ResourceGraphClient
from azure.mgmt.resourcegraph.models import QueryRequest, QueryRequestOptions
import requests
from collectors.azure_client import get_shared_credential


def get_subscriptions():
    credential = get_shared_credential()
    token = credential.get_token("https://management.azure.com/.default").token
    resp = requests.get(
        "https://management.azure.com/subscriptions?api-version=2022-01-01",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    resp.raise_for_status()
    return [
        s["subscriptionId"]
        for s in resp.json().get("value", [])
        if s.get("state") == "Enabled"
    ]


def query_resource_graph(query: str, subscriptions: list):
    credential = get_shared_credential()
    client = ResourceGraphClient(credential)

    request = QueryRequest(
        subscriptions=subscriptions,
        query=query,
        options=QueryRequestOptions(result_format="objectArray")
    )

    response = client.resources(request)
    return response.data


def collect_rg_data():
    print("Collecting Resource Graph data...")

    subscriptions = get_subscriptions()

    results = {}

    # 1️⃣ VNets
    vnet_query = """
    Resources
    | where type =~ 'microsoft.network/virtualnetworks'
    | project name, resourceGroup, location, id
    """
    results["vnets"] = query_resource_graph(vnet_query, subscriptions)

    # 2️⃣ Azure Firewalls
    firewall_query = """
    Resources
    | where type =~ 'microsoft.network/azurefirewalls'
    | project name, resourceGroup, location, id
    """
    results["firewalls"] = query_resource_graph(firewall_query, subscriptions)

    # 3️⃣ Public IPs
    public_ip_query = """
    Resources
    | where type =~ 'microsoft.network/publicipaddresses'
    | project name, resourceGroup, location, id
    """
    results["public_ips"] = query_resource_graph(public_ip_query, subscriptions)

    print("Resource Graph collection complete.")
    return results
