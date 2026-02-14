import os, json
from datetime import datetime, timezone

def save_run(out_root, tenant_id, payload):
    tenant = tenant_id or "unknown"
    path = os.path.join(out_root, tenant)
    os.makedirs(path, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    file = os.path.join(path, f"{ts}.json")

    with open(file, "w") as f:
        json.dump(payload, f, indent=2)

    return file

def get_last_run(out_root, tenant_id):
    tenant = tenant_id or "unknown"
    path = os.path.join(out_root, tenant)
    if not os.path.isdir(path):
        return None

    files = sorted(os.listdir(path))
    if not files:
        return None

    return os.path.join(path, files[-1])
