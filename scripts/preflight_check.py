"""Pre-flight check: verify scan is ready to run."""
from alz.loader import load_alz_checklist
from control_packs.loader import load_pack
from evaluators.checklist_driven import register_checklist_evaluators
from signals.validation import validate_signal_bindings
from evaluators.registry import EVALUATORS

# Import all evaluator modules
import evaluators.networking, evaluators.governance, evaluators.security
import evaluators.data_protection, evaluators.resilience, evaluators.identity
import evaluators.network_coverage, evaluators.management, evaluators.cost
import evaluators.network_topology, evaluators.identity_access
import evaluators.resource_organization, evaluators.platform_automation, evaluators.billing

# Register data-driven
checklist = load_alz_checklist(force_refresh=False)
items = checklist.get("items", [])
new = register_checklist_evaluators(items)

pack = load_pack("alz", "v1.0")
violations = validate_signal_bindings(pack)
critical = [v for v in violations if v["type"] != "missing_evaluator"] if violations else []

print(f"Checklist items:         {len(items)}")
print(f"Hand-written evaluators: {len(EVALUATORS) - new}")
print(f"Data-driven evaluators:  {new}")
print(f"Total evaluators:        {len(EVALUATORS)}")
print(f"Pack controls:           {len(pack.controls)}")
print(f"Binding violations:      {len(critical)} critical")
print(f"Coverage:                {len(EVALUATORS)}/{len(items)} ({len(EVALUATORS)*100//len(items)}%)")
print()

if critical:
    print("CRITICAL ISSUES:")
    for v in critical[:5]:
        detail = v.get("detail", "")[:80]
        print(f"  ! {detail}")
    print("\nFIX BEFORE RUNNING SCAN")
else:
    print("All clear — ready to scan.")
    print()
    print("  python scan.py --mg-scope 4830d02f-fd7b-4629-905f-a41bb5868147")
