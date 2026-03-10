# collectors/management_groups.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from collectors.azure_client import AzureClient

API_VERSION = "2021-04-01"

@dataclass
class MgNode:
    id: str
    name: str
    display_name: str
    children: List["MgNode"]
    subscriptions: List[str]

def _build_tree(node_json: Dict[str, Any]) -> MgNode:
    props = node_json.get("properties", {}) or {}
    children = props.get("children", []) or []
    # Subscriptions are siblings of children in the API response
    subs_raw = props.get("subscriptions", []) or []
    sub_ids = [s.get("name", "") or s.get("id", "").rsplit("/", 1)[-1]
              for s in subs_raw]
    return MgNode(
        id=node_json.get("id", ""),
        name=node_json.get("name", ""),
        display_name=props.get("displayName", node_json.get("name", "")),
        children=[_build_tree(c) for c in children],
        subscriptions=sub_ids,
    )

def _walk(node: MgNode, depth: int = 0) -> List[Tuple[MgNode, int]]:
    out = [(node, depth)]
    for c in node.children:
        out.extend(_walk(c, depth + 1))
    return out

def collect_management_group_hierarchy(client: AzureClient, root_group_id: str) -> Dict[str, Any]:
    """
    Queries tenant-scope MG hierarchy using the descendants API for reliable
    full-depth traversal, then reconstructs the tree.
    """
    # ── Primary: descendants API (flat list of all MGs + subs) ────
    # The $expand=children approach is unreliable for recursive depth,
    # so we use descendants and rebuild the tree ourselves.
    try:
        desc_data = client.get(
            f"/providers/Microsoft.Management/managementGroups/{root_group_id}/descendants",
            api_version=API_VERSION,
        )
        descendants = desc_data.get("value", [])
    except Exception:
        descendants = []

    # Separate MGs from subscriptions
    mg_nodes: Dict[str, Dict[str, Any]] = {}
    sub_placement: Dict[str, str] = {}  # sub_id → parent_mg_name

    for d in descendants:
        dtype = d.get("type", "")
        name = d.get("name", "")
        props = d.get("properties", {})
        display_name = props.get("displayName", name)
        parent_id = props.get("parent", {}).get("id", "") or ""
        parent_name = parent_id.rsplit("/", 1)[-1] if parent_id else ""

        if dtype.endswith("/managementGroups"):
            mg_nodes[name] = {
                "name": name,
                "display_name": display_name,
                "parent": parent_name,
                "children": [],
                "subscriptions": [],
            }
        elif dtype.endswith("/subscriptions"):
            sub_placement[name] = parent_name

    # Add root MG itself (not in descendants)
    mg_nodes[root_group_id] = mg_nodes.get(root_group_id, {
        "name": root_group_id,
        "display_name": root_group_id,
        "parent": "",
        "children": [],
        "subscriptions": [],
    })

    # Wire children and subscriptions
    for mg_name, mg in mg_nodes.items():
        parent = mg["parent"]
        if parent and parent in mg_nodes and parent != mg_name:
            mg_nodes[parent]["children"].append(mg_name)

    for sub_id, parent_mg in sub_placement.items():
        if parent_mg in mg_nodes:
            mg_nodes[parent_mg]["subscriptions"].append(sub_id)

    # Build MgNode tree from root
    def _build_from_flat(mg_name: str) -> MgNode:
        mg = mg_nodes.get(mg_name, {})
        child_names = mg.get("children", [])
        return MgNode(
            id=f"/providers/Microsoft.Management/managementGroups/{mg_name}",
            name=mg_name,
            display_name=mg.get("display_name", mg_name),
            children=[_build_from_flat(c) for c in child_names],
            subscriptions=mg.get("subscriptions", []),
        )

    tree = _build_from_flat(root_group_id)
    flat = _walk(tree)

    max_depth = max(d for _, d in flat) if flat else 0
    node_count = len(flat)

    # Detect by BOTH id segment and display name (case-insensitive)
    def _matches(node: MgNode, *patterns: str) -> bool:
        name_lower = node.name.lower()
        display_lower = node.display_name.lower()
        id_lower = node.id.lower()
        for p in patterns:
            if p in name_lower or p in display_lower or p in id_lower:
                return True
        return False

    has_platform = any(_matches(n, "platform") for n, _ in flat)
    has_landingzones = any(
        _matches(n, "landing zone", "landingzones", "landing-zones", "corp", "online")
        for n, _ in flat
    )
    has_connectivity = any(_matches(n, "connect") for n, _ in flat)
    has_identity = any(_matches(n, "ident") for n, _ in flat)
    has_management = any(
        _matches(n, "management", "logging", "monitoring")
        for n, _ in flat
        if n.name.lower() != root_group_id.lower()  # exclude root MG itself
    )
    has_sandbox = any(_matches(n, "sandbox") for n, _ in flat)

    # Subscriptions directly under root
    root_subs = tree.subscriptions

    # Build compact hierarchy for AI topology reasoning
    def _to_compact(node: MgNode) -> Dict[str, Any]:
        entry: Dict[str, Any] = {
            "id": node.name,
            "display_name": node.display_name,
        }
        if node.subscriptions:
            entry["subscriptions"] = node.subscriptions
        if node.children:
            entry["children"] = [_to_compact(c) for c in node.children]
        return entry

    # Build subscription → MG lookup
    sub_to_mg: Dict[str, str] = {}
    for n, _ in flat:
        for sub_id in n.subscriptions:
            sub_to_mg[sub_id] = n.name

    return {
        "root_management_group_id": root_group_id,
        "management_group_count": node_count,
        "max_depth": max_depth,
        "has_platform_mg": has_platform,
        "has_landing_zones_mg": has_landingzones,
        "has_connectivity_mg": has_connectivity,
        "has_identity_mg": has_identity,
        "has_management_mg": has_management,
        "has_sandbox_mg": has_sandbox,
        "root_subscriptions": root_subs,
        "subscription_placement": sub_to_mg,
        "tree": {"name": root_group_id, "properties": {"displayName": tree.display_name}},
        "compact_hierarchy": _to_compact(tree),
    }

def discover_management_group_scope(client: AzureClient):
    """
    Returns:
        {
            "mode": "mg" | "subscription",
            "root_mg_id": str | None,
            "reason": str
        }
    """
    try:
        data = client.get(
            "/providers/Microsoft.Management/managementGroups",
            api_version="2020-05-01"
        )

        mgs = data.get("value", [])

        if not mgs:
            return {
                "mode": "subscription",
                "root_mg_id": None,
                "reason": "No management groups returned"
            }

        # find tenant root MG (parent = None)
        for mg in mgs:
            parent = (
                mg.get("properties", {})
                  .get("details", {})
                  .get("parent", {})
                  .get("name")
            )
            if not parent:
                return {
                    "mode": "mg",
                    "root_mg_id": mg["name"],
                    "reason": "Tenant root MG discovered"
                }

        return {
            "mode": "subscription",
            "root_mg_id": None,
            "reason": "No root MG visible with current permissions"
        }

    except Exception as e:
        return {
            "mode": "subscription",
            "root_mg_id": None,
            "reason": f"MG API not accessible: {str(e)}"
        }
