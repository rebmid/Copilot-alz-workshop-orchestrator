"""Verify MG hierarchy collector now returns correct depth."""
import json
from collectors.azure_client import build_client
from collectors.management_groups import collect_management_group_hierarchy

ROOT_MG = "4830d02f-fd7b-4629-905f-a41bb5868147"

client = build_client()
result = collect_management_group_hierarchy(client, ROOT_MG)

print(f"Management group count: {result['management_group_count']}")
print(f"Max depth:              {result['max_depth']}")
print(f"has_platform_mg:        {result['has_platform_mg']}")
print(f"has_landing_zones_mg:   {result['has_landing_zones_mg']}")
print(f"has_connectivity_mg:    {result['has_connectivity_mg']}")
print(f"has_identity_mg:        {result['has_identity_mg']}")
print(f"has_management_mg:      {result['has_management_mg']}")
print(f"has_sandbox_mg:         {result.get('has_sandbox_mg', False)}")
print(f"Root subscriptions:     {len(result.get('root_subscriptions', []))}")
print(f"Subscription placement: {len(result.get('subscription_placement', {}))}")
print()

# Show hierarchy
hierarchy = result.get("compact_hierarchy", {})
def show(node, indent=0):
    prefix = "  " * indent
    name = node.get("id", "")
    dn = node.get("display_name", "")
    subs = node.get("subscriptions", [])
    sub_text = f" ({len(subs)} subs)" if subs else ""
    label = f"{dn}" if dn != name else name
    print(f"{prefix}{label}{sub_text}")
    for c in node.get("children", []):
        show(c, indent + 1)

print("=== Hierarchy ===")
show(hierarchy)
