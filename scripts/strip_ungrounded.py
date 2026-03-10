"""Remove controls from controls.json that are NOT in the official ALZ review checklist."""
import json
from alz.loader import load_alz_checklist

CONTROLS_PATH = "control_packs/alz/v1.0/controls.json"

# Load official checklist
checklist = load_alz_checklist(force_refresh=False)
items = checklist.get("items", [])
official_guids = set(item.get("guid", "") for item in items if item.get("guid"))
print(f"Official ALZ checklist GUIDs: {len(official_guids)}")

# Load control pack
with open(CONTROLS_PATH, encoding="utf-8") as f:
    data = json.load(f)

controls = data.get("controls", {})
print(f"Current controls: {len(controls)}")

# Partition
keep = {}
remove = []
for key, ctrl in controls.items():
    full_id = ctrl.get("full_id", "")
    if full_id in official_guids:
        keep[key] = ctrl
    else:
        remove.append((key, ctrl.get("name", "")))

print(f"\nKeeping (grounded): {len(keep)}")
print(f"Removing (not in checklist): {len(remove)}")
for key, name in remove:
    print(f"  - {key}: {name}")

# Update controls
data["controls"] = keep

# Update design_areas — remove any keys that no longer have controls
new_design_areas = {}
for area_key, area in data.get("design_areas", {}).items():
    area_controls = [c for c in area.get("controls", []) if c in keep]
    if area_controls:
        area["controls"] = area_controls
        new_design_areas[area_key] = area
data["design_areas"] = new_design_areas

# Update metadata
data["version"] = "1.5.0"
data["description"] = (
    f"{len(keep)} automated control evaluators grounded to the official "
    f"Azure Landing Zone Review Checklist ({len(official_guids)} controls). "
    f"Covers all 8 ALZ design areas."
)

with open(CONTROLS_PATH, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print(f"\nUpdated controls.json: {len(keep)} controls, {len(new_design_areas)} design areas")
