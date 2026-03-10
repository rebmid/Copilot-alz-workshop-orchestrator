"""Find official ALZ checklist GUIDs that match our 28 ungrounded controls."""
import json
from alz.loader import load_alz_checklist

checklist = load_alz_checklist(force_refresh=False)
items = checklist.get("items", [])

# Our 28 ungrounded controls and search terms
ungrounded = [
    ("storage-", "storage account"),
    ("keyvault", "key vault"),
    ("sql-post", "sql"),
    ("appservi", "app service"),
    ("private-", "private endpoint"),
    ("acr-post", "container registr"),
    ("nsg-cove", "network security group"),
    ("aks-post", "aks"),
    ("backup-c", "backup"),
    ("resource", "resource lock"),
    ("rbac-hyg", "rbac"),
    ("entra-lo", "entra"),
    ("pim-usag", "privileged identity"),
    ("monitor-", "log analytics"),
    ("activity", "automation"),
    ("update-m", "update"),
    ("cost-mgm", "cost management"),
    ("netwatch", "network watcher"),
    ("pim-matu", "privileged identity"),
    ("breakgla", "break-glass"),
    ("sp-owner", "service principal"),
    ("admin-ca", "conditional access"),
    ("alert-ac", "alert"),
    ("action-g", "action group"),
    ("availabi", "availability"),
    ("change-t", "change tracking"),
    ("cost-for", "cost forecast"),
    ("idle-res", "idle"),
]

official_guids = set(i.get("guid", "") for i in items)

for key, search in ungrounded:
    matches = []
    for item in items:
        text = (item.get("text", "") or "").lower()
        if search.lower() in text:
            matches.append(item)
    if matches:
        best = matches[0]  # first match
        guid = best.get("guid", "")
        sev = best.get("severity", "")
        txt = best.get("text", "")[:80]
        print(f"{key:12s} -> {guid}  [{sev}] {txt}")
    else:
        print(f"{key:12s} -> NO MATCH for '{search}'")
