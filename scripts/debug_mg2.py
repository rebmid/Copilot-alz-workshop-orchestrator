"""Debug: test different MG API parameter formats."""
import requests
from collectors.azure_client import get_shared_credential

token = get_shared_credential().get_token("https://management.azure.com/.default").token
headers = {"Authorization": f"Bearer {token}"}

mg_id = "4830d02f-fd7b-4629-905f-a41bb5868147"
base = f"https://management.azure.com/providers/Microsoft.Management/managementGroups/{mg_id}"

# Test 1: params dict with $expand
print("=== Test 1: requests params dict ===")
resp = requests.get(base, headers=headers, params={
    "api-version": "2021-04-01",
    "$expand": "children",
    "$recurse": "true",
}, timeout=30)
data = resp.json()
children = data.get("properties", {}).get("children", [])
print(f"  Children: {len(children)}")
print(f"  Request URL: {resp.url}")

# Test 2: Manual URL with query string  
print("\n=== Test 2: Manual URL ===")
url2 = f"{base}?api-version=2021-04-01&$expand=children&$recurse=true"
resp2 = requests.get(url2, headers=headers, timeout=30)
data2 = resp2.json()
children2 = data2.get("properties", {}).get("children", [])
print(f"  Children: {len(children2)}")
print(f"  Request URL: {resp2.url}")

# Test 3: With $expand=children,subscriptions
print("\n=== Test 3: expand=children,subscriptions  ===")
url3 = f"{base}?api-version=2021-04-01&$expand=children&$recurse=true"
resp3 = requests.get(url3, headers=headers, timeout=30)
data3 = resp3.json()
children3 = data3.get("properties", {}).get("children", [])
print(f"  Children: {len(children3)}")
if children3:
    for c in children3[:5]:
        cp = c.get("properties", {})
        print(f"    {c.get('name','')} - {cp.get('displayName','')}")
