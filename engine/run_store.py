import os, json, re
from datetime import datetime, timezone


def _slugify(name: str) -> str:
    """Convert a display name to a filesystem-safe folder name."""
    slug = re.sub(r"[^\w\s-]", "", name.strip())
    slug = re.sub(r"[\s]+", "_", slug)
    return slug[:64] or "unknown"


def save_run(out_root, tenant_id, payload, tenant_name: str = ""):
    slug = _slugify(tenant_name) if tenant_name else (tenant_id or "unknown")
    path = os.path.join(out_root, slug)
    os.makedirs(path, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    file = os.path.join(path, f"{ts}.json")

    with open(file, "w") as f:
        json.dump(payload, f, indent=2)

    return file

def get_last_run(out_root, tenant_id, tenant_name: str = ""):
    slug = _slugify(tenant_name) if tenant_name else (tenant_id or "unknown")
    path = os.path.join(out_root, slug)
    if not os.path.isdir(path):
        # Fall back to GUID folder for backward compat
        if tenant_id:
            path = os.path.join(out_root, tenant_id)
        if not os.path.isdir(path):
            return None

    files = sorted(f for f in os.listdir(path) if f.endswith(".json"))
    if not files:
        return None

    return os.path.join(path, files[-1])


def get_last_run_data(out_root, tenant_id, tenant_name: str = ""):
    """Return (path, parsed_dict) for the most recent run, or (None, None)."""
    path = get_last_run(out_root, tenant_id, tenant_name=tenant_name)
    if not path:
        return None, None
    with open(path, encoding="utf-8") as f:
        return path, json.load(f)


def list_runs(out_root, tenant_id, tenant_name: str = ""):
    """Return a list of (path, meta_dict) for all runs, oldest first.

    Only reads the 'meta' key from each file for speed.
    Backwards-compatible with runs that have no meta.tag.
    """
    slug = _slugify(tenant_name) if tenant_name else (tenant_id or "unknown")
    folder = os.path.join(out_root, slug)
    if not os.path.isdir(folder):
        if tenant_id:
            folder = os.path.join(out_root, tenant_id)
        if not os.path.isdir(folder):
            return []

    runs = []
    for fname in sorted(f for f in os.listdir(folder) if f.endswith(".json")):
        fpath = os.path.join(folder, fname)
        try:
            with open(fpath, encoding="utf-8") as f:
                data = json.load(f)
            runs.append((fpath, data.get("meta", {})))
        except (json.JSONDecodeError, OSError):
            continue
    return runs
