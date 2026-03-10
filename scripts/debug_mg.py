"""Debug: test MG hierarchy API call to diagnose missing children."""
from collectors.azure_client import build_client
import json

client = build_client()

# Test 1: Using $expand=children with recurse
print("=== Test 1: $expand=children,subscriptions + recurse=true ===")
data = client.get(
    "/providers/Microsoft.Management/managementGroups/4830d02f-fd7b-4629-905f-a41bb5868147",
    api_version="2021-04-01",
    params={"$expand": "children,subscriptions", "recurse": "true"},
)
props = data.get("properties", {})
children = props.get("children", [])
print(f"Children count: {len(children)}")
if children:
    for c in children[:5]:
        cprops = c.get("properties", {})
        print(f"  {c.get('name','')} - {cprops.get('displayName','')}")
else:
    print("No children!")
    print("Props keys:", list(props.keys()))

# Test 2: Using descendants API
print("\n=== Test 2: Descendants API ===")
import requests
from collectors.azure_client import get_shared_credential
token = get_shared_credential().get_token("https://management.azure.com/.default").token
resp = requests.get(
    "https://management.azure.com/providers/Microsoft.Management"
    "/managementGroups/4830d02f-fd7b-4629-905f-a41bb5868147/descendants"
    "?api-version=2021-04-01",
    headers={"Authorization": f"Bearer {token}"},
    timeout=20,
)
resp.raise_for_status()
descendants = resp.json().get("value", [])
mgs = [d for d in descendants if "managementGroups" in (d.get("type") or "")]
subs = [d for d in descendants if "subscriptions" in (d.get("type") or "")]
print(f"Descendant MGs: {len(mgs)}")
print(f"Descendant subs: {len(subs)}")
for mg in mgs[:10]:
    dprops = mg.get("properties", {})
    print(f"  {mg.get('name','')} - {dprops.get('displayName','')}")
