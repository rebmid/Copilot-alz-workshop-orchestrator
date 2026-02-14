"""PASS A + B + C — cluster → enrich → transformation roadmap."""
import json
from ai.build_advisor_payload import build_advisor_payload
from ai.narrative import cluster_initiatives, generate_transformation_roadmap
from ai.mcp_retriever import enrich_with_mcp

import glob

# Load latest run
run_files = sorted(glob.glob("out/run-*.json"), reverse=True)
if not run_files:
    raise SystemExit("No run files found in out/")
latest = run_files[0]
print(f"Using: {latest}")
with open(latest, encoding="utf-8") as f:
    run = json.load(f)

payload = build_advisor_payload(
    scoring=run["scoring"],
    results=run["results"],
    execution_context=run["execution_context"],
    delta=run.get("delta"),
    mg_hierarchy=run.get("management_groups", {}).get("compact_hierarchy"),
)

print(f"Payload: {len(payload['failed_controls'])} fails, "
      f"{len(payload['sampled_manual_controls'])} sampled manual\n")

# PASS A — cluster
clusters = cluster_initiatives(payload)
print("=== PASS A: Initiatives ===")
plan_items = clusters.get("initiative_execution_plan", [])
for init in plan_items:
    print(f"  [{init['priority']}] {init['title']}  ({init['blast_radius']})")

# PASS B — enrich with Microsoft Learn references
print("\n=== PASS B: Enriching with Learn references ===")
enriched = enrich_with_mcp(plan_items)
clusters["initiative_execution_plan"] = enriched

# PASS C — transformation roadmap
print("\n=== PASS C: Transformation Roadmap ===")
roadmap = generate_transformation_roadmap(payload, enriched)
if roadmap:
    for phase in ("30_days", "60_days", "90_days"):
        actions = roadmap.get("roadmap", {}).get(phase, [])
        print(f"\n  {phase}: {len(actions)} actions")
        for a in actions:
            print(f"    • {a['action'][:90]}  [{a.get('caf_discipline','')}]")

    proj = roadmap.get("projected_maturity", {})
    print(f"\n  Projected maturity: {proj.get('current_percent')}% → "
          f"{proj.get('after_30_days')}% → {proj.get('after_60_days')}% → "
          f"{proj.get('after_90_days')}%")

    cpath = roadmap.get("critical_path", [])
    print(f"  Critical path: {len(cpath)} items")

    clusters["transformation_roadmap"] = roadmap
else:
    print("  ⚠ Roadmap generation failed or skipped")

print("\n=== Full Output ===")
print(json.dumps(clusters, indent=2))
