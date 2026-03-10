"""End-to-end verification of all 38 new evaluators against live Azure signals."""
import json
from signals.types import EvalScope
from signals.registry import SignalBus
from evaluators.registry import EVALUATORS, evaluate_control
from control_packs.loader import load_pack

# Ensure all evaluator modules imported
import evaluators.network_topology     # noqa: F401
import evaluators.identity_access      # noqa: F401
import evaluators.resource_organization  # noqa: F401
import evaluators.platform_automation  # noqa: F401
import evaluators.billing              # noqa: F401

# Load scope from current assessment context
d = json.load(open("assessment.json", encoding="utf-8"))
ctx = d.get("execution_context", {})
subs = ctx.get("subscription_ids_visible", [])
tenant = ctx.get("tenant_id", "")

scope = EvalScope(tenant_id=tenant, subscription_ids=subs)
bus = SignalBus()

# All 38 new evaluator control IDs
new_ids = [
    # Network Topology (18)
    "9dcd6250-9c4a-4382-aa9b-5b84c64fc1fe",
    "48682fb1-1e86-4458-a686-518ebd47393d",
    "c76cb5a2-abe2-11ed-afa1-0242ac120002",
    "ee1ac551-c4d5-46cf-b035-d0a3c50d87ad",
    "1d7aa9b6-4704-4489-a804-2d88e79d17b7",
    "153e8908-ae28-4c84-a33b-6b7808b9fe5c",
    "614658d3-558f-4d77-849b-821112df27ee",
    "f2aad7e3-bb03-4adc-8606-4123d342a917",
    "b1c82a3f-2320-4dfa-8972-7ae4823c8930",
    "7dd61623-a364-4a90-9eca-e48ebd54cd7d",
    "715d833d-4708-4527-90ac-1b142c7045ba",
    "22d6419e-b627-4d95-9e7d-019fa759387f",
    "e8143efa-0301-4d62-be54-ca7b5ce566dc",
    "c10d51ef-f999-455d-bba0-5c90ece07447",
    "d38ad60c-bc9e-4d49-b699-97e5d4dcf707",
    "b3e4563a-4d87-4397-98b6-62d6d15f512a",
    "2363cefe-179b-4599-be0d-5973cd4cd21b",
    "359c373e-7dd6-4162-9a36-4a907ecae48e",
    # Identity & Access (8)
    "4348bf81-7573-4512-8f46-9061cc198fea",
    "53e8908a-e28c-484c-93b6-b7808b9fe5c4",
    "1049d403-a923-4c34-94d0-0018ac6a9e01",
    "14658d35-58fd-4772-99b8-21112df27ee4",
    "984a859c-773e-47d2-9162-3a765a917e1f",
    "348ef254-c27d-442e-abba-c7571559ab91",
    "d505ebcb-79b1-4274-9c0d-a27c8bea489c",
    "e6a83de5-de32-4c19-a248-1607d5d1e4e6",
    # Resource Org (6)
    "667313b4-f566-44b5-b984-a859c773e7d2",
    "33b6b780-8b9f-4e5c-9104-9d403a923c34",
    "74d00018-ac6a-49e0-8e6a-83de5de32c19",
    "5de32c19-9248-4160-9d5d-1e4e614658d3",
    "250d81ce-8bbe-4f85-9051-6a18a8221e50",
    "19ca3f89-397d-44b1-b5b6-5e18661372ac",
    # Platform Automation (3)
    "108d5099-a11d-4445-bd8b-e12a5e95412e",
    "2cdc9d99-dbcc-4ad4-97f5-e7d358bdfa73",
    "cc87a3bc-c572-4ad2-92ed-8cabab66160f",
    # Billing (3)
    "32952499-58c8-4e6f-ada5-972e67893d55",
    "54f0d8b1-22a3-4c0d-8ce2-58b9e086c93a",
    "685cb4f2-ac9c-4b19-9167-993ed0b32415",
]

print(f"Testing {len(new_ids)} evaluators against live signals ({len(subs)} subs)...")
print()

counts = {"Pass": 0, "Fail": 0, "Partial": 0, "NotApplicable": 0, "Error": 0, "SignalError": 0}
icons = {"Pass": "+", "Fail": "X", "Partial": "~", "NotApplicable": "-", "Error": "!", "SignalError": "!"}

for cid in new_ids:
    ev = EVALUATORS.get(cid)
    if not ev:
        print(f"  [?] NOT REGISTERED  {cid}")
        continue
    try:
        result = evaluate_control(cid, scope, bus, run_id="e2e-test")
    except Exception as exc:
        print(f"  [!] EXCEPTION       {type(ev).__name__[:35]:35s} {str(exc)[:90]}")
        counts["Error"] = counts.get("Error", 0) + 1
        continue
    status = result.get("status", "Unknown")
    reason = result.get("reason", "")[:90]
    name = type(ev).__name__
    icon = icons.get(status, "?")
    print(f"  [{icon}] {status:15s} {name[:35]:35s} {reason}")
    counts[status] = counts.get(status, 0) + 1

print()
print(f"Pass: {counts['Pass']}, Fail: {counts['Fail']}, Partial: {counts['Partial']}, "
      f"N/A: {counts['NotApplicable']}, Error: {counts.get('Error',0) + counts.get('SignalError',0)}")
