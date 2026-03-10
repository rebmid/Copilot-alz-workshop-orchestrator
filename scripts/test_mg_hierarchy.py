"""Test MG hierarchy API call to diagnose depth=0 bug."""
import json
from collectors.azure_client import build_client, get_shared_credential
import requests

ROOT_MG = "4830d02f-fd7b-4629-905f-a41bb5868147"

# Test 1: Current code's approach (AzureClient.get with params)
print("=== Test 1: AzureClient.get (current code) ===")
client = build_client()
data = client.get(
    f"/providers/Microsoft.Management/managementGroups/{ROOT_MG}",
    api_version="2021-04-01",
    params={"$expand": "children,subscriptions", "recurse": "true"},
)
props = data.get("properties", {})
children = props.get("children", []) or []
print(f"Children: {len(children)}")

# Test 2: Direct requests with $recurse ($ prefix)
print("\n=== Test 2: Direct URL with $recurse ===")
token = get_shared_credential().get_token("https://management.azure.com/.default").token
url = (
    f"https://management.azure.com/providers/Microsoft.Management"
    f"/managementGroups/{ROOT_MG}"
    f"?api-version=2021-04-01"
    f"&$expand=children"
    f"&$recurse=true"
)
resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
data2 = resp.json()
props2 = data2.get("properties", {})
children2 = props2.get("children", []) or []
print(f"Children: {len(children2)}")

def count_nodes(node):
    c = node.get("properties", {}).get("children", []) or []
    return 1 + sum(count_nodes(ch) for ch in c)

def max_depth(node, d=0):
    c = node.get("properties", {}).get("children", []) or []
    if not c:
        return d
    return max(max_depth(ch, d + 1) for ch in c)

if children2:
    print(f"Total nodes: {count_nodes(data2)}")
    print(f"Max depth: {max_depth(data2)}")
    for c in children2:
        cp = c.get("properties", {})
        dn = cp.get("displayName", c.get("name", ""))
        sub_c = cp.get("children", []) or []
        print(f"  {c.get('name', '')} ({dn}) - children: {len(sub_c)}")
else:
    print("No children returned!")
    print(f"Response: {json.dumps(props2, indent=2)[:500]}")
