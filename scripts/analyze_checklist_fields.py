"""Analyze checklist field hierarchy: id, category, subcategory, service."""
import json
from collections import Counter, defaultdict
from alz.loader import load_alz_checklist

cl = load_alz_checklist(force_refresh=False)
items = cl.get("items", [])

# Map ID prefix -> design area
id_to_cat = {}
for item in items:
    item_id = item.get("id", "")
    prefix = item_id.split(".")[0] if "." in item_id else item_id
    id_to_cat[prefix] = item.get("category", "")

print("=== ID Prefix -> Category (Design Area) ===")
for prefix in sorted(id_to_cat.keys()):
    print(f"  {prefix:5s} -> {id_to_cat[prefix]}")

# Show category -> subcategory hierarchy
print("\n=== Category -> Subcategories ===")
cat_subcats = defaultdict(set)
for item in items:
    cat = item.get("category", "")
    subcat = item.get("subcategory", "")
    cat_subcats[cat].add(subcat)

for cat in sorted(cat_subcats.keys()):
    subcats = sorted(cat_subcats[cat])
    print(f"\n  {cat}:")
    for sc in subcats:
        count = sum(1 for i in items if i.get("category") == cat and i.get("subcategory") == sc)
        print(f"    {count:3d}  {sc}")

# Show 3 sample items with ALL fields
print("\n=== Sample Items (full field set) ===")
for item in items[:3]:
    print(json.dumps(item, indent=2, ensure_ascii=False))
    print()

# Check how reporting uses section/category
print("\n=== How reports use these fields ===")
print("HTML report groups by: results[].section (= checklist category)")
print("Excel workbook uses:   results[].section + results[].checklist_ids")
print("Scoring engine uses:   results[].section -> DOMAIN_WEIGHTS lookup")
