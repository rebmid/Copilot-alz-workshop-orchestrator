"""Full Reasoning Engine pipeline test — loads latest run, generates unified AI output.

This is an INTEGRATION test that requires:
  - Azure OpenAI credentials configured
  - At least one run file in out/run-*.json

Run standalone:  python test_reasoning_engine.py
Run via pytest:  pytest test_reasoning_engine.py -v
"""
import json
import glob
import os
import pytest

from ai.build_advisor_payload import build_advisor_payload


def _have_run_files():
    return len(glob.glob("out/run-*.json")) > 0


def _have_aoai_credentials():
    return bool(os.environ.get("AZURE_OPENAI_ENDPOINT") or os.environ.get("AOAI_ENDPOINT"))


# ── pytest-compatible entry point ─────────────────────────────────

@pytest.mark.skipif(not _have_run_files(), reason="No out/run-*.json files available")
@pytest.mark.skipif(not _have_aoai_credentials(), reason="Azure OpenAI credentials not configured")
def test_reasoning_engine_pipeline():
    """Full end-to-end reasoning engine pipeline test (integration)."""
    from ai.engine.reasoning_provider import AOAIReasoningProvider
    from ai.engine.reasoning_engine import ReasoningEngine
    from ai.prompts import PromptPack

    run_files = sorted(glob.glob("out/run-*.json"), reverse=True)
    latest = run_files[0]
    with open(latest, encoding="utf-8") as f:
        run = json.load(f)

    payload = build_advisor_payload(
        scoring=run["scoring"],
        results=run["results"],
        execution_context=run["execution_context"],
        delta=run.get("delta"),
        mg_hierarchy=run.get("management_groups", {}).get("compact_hierarchy"),
        signal_availability=run.get("signal_availability"),
    )

    provider = AOAIReasoningProvider()
    engine = ReasoningEngine(provider, PromptPack())

    ai_output = engine.generate(
        payload,
        run_id="test-run",
        tenant_id=run.get("execution_context", {}).get("tenant_id", ""),
        skip_implementation=False,
    )

    # Validate output structure
    assert "executive" in ai_output
    assert "initiatives" in ai_output
    assert "smart_questions" in ai_output


@pytest.mark.skipif(not _have_run_files(), reason="No out/run-*.json files available")
def test_build_advisor_payload():
    """Verify build_advisor_payload produces a valid payload from a run file."""
    run_files = sorted(glob.glob("out/run-*.json"), reverse=True)
    latest = run_files[0]
    with open(latest, encoding="utf-8") as f:
        run = json.load(f)

    payload = build_advisor_payload(
        scoring=run["scoring"],
        results=run["results"],
        execution_context=run["execution_context"],
        delta=run.get("delta"),
        mg_hierarchy=run.get("management_groups", {}).get("compact_hierarchy"),
        signal_availability=run.get("signal_availability"),
    )
    assert "failed_controls" in payload
    assert "sampled_manual_controls" in payload


# ── Standalone execution ──────────────────────────────────────────

def main():
    from ai.engine.reasoning_provider import AOAIReasoningProvider
    from ai.engine.reasoning_engine import ReasoningEngine
    from ai.prompts import PromptPack

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
        signal_availability=run.get("signal_availability"),
    )
    print(f"Payload: {len(payload['failed_controls'])} fails, "
          f"{len(payload['sampled_manual_controls'])} sampled manual\n")

    provider = AOAIReasoningProvider()
    engine = ReasoningEngine(provider, PromptPack())

    ai_output = engine.generate(
        payload,
        run_id="test-run",
        tenant_id=run.get("execution_context", {}).get("tenant_id", ""),
        skip_implementation=False,
    )

    print("\n" + "=" * 60)
    print("REASONING ENGINE OUTPUT SUMMARY")
    print("=" * 60)

    exec_block = ai_output.get("executive", {})
    print(f"\n\U0001f4cb Executive summary: {len(exec_block.get('summary', ''))} chars")
    print(f"   Business risks: {len(exec_block.get('top_business_risks', []))}")
    print(f"   Investment priorities: {len(exec_block.get('investment_priorities', []))}")
    print(f"   90-day outcomes: {len(exec_block.get('expected_outcomes_90_days', []))}")

    readiness = ai_output.get("enterprise_scale_readiness", {})
    print(f"\n\U0001f3d7\ufe0f  Enterprise-scale ready: {readiness.get('ready_for_enterprise_scale', '?')}")
    print(f"   Max subscriptions (current): {readiness.get('max_supported_subscriptions_current_state', '?')}")
    print(f"   Readiness score: {readiness.get('readiness_score', '?')}/100")
    print(f"   Blockers: {len(readiness.get('blockers', []))}")

    roadmap = ai_output.get("transformation_roadmap", {})
    rm = roadmap.get("roadmap_30_60_90", {})
    print(f"\n\U0001f5fa\ufe0f  Roadmap:")
    for phase in ("30_days", "60_days", "90_days"):
        actions = rm.get(phase, [])
        print(f"   {phase}: {len(actions)} action(s)")
        for a in actions[:3]:
            disc = a.get("caf_discipline", "")
            print(f"     \u2022 {a.get('action', '')[:80]}  [{disc}]")
    print(f"   Critical path: {len(roadmap.get('critical_path', []))} item(s)")
    traj = roadmap.get("maturity_trajectory", {})
    if traj:
        print(f"   Maturity: {traj.get('current_maturity_percent', '?')}% \u2192 "
              f"{traj.get('projected_90_day_percent', '?')}% at 90d")

    inits = ai_output.get("initiatives", [])
    print(f"\n\U0001f3af Initiatives: {len(inits)}")
    for init in inits:
        refs = len(init.get("learn_references", []))
        print(f"   [{init.get('priority', '?')}] {init.get('title', '')[:70]}  "
              f"({init.get('blast_radius', '?')}) \u2014 {refs} refs")

    impl = ai_output.get("implementation_backlog", [])
    print(f"\n\U0001f527 Implementation plans: {len(impl)}")
    for item in impl:
        iid = item.get("initiative_id", "?")
        imp = item.get("implementation", {})
        print(f"   {iid}: {len(imp.get('bicep_modules', []))} bicep, "
              f"{len(imp.get('policy_assignments', []))} policy, "
              f"{len(imp.get('rbac_roles', []))} rbac, "
              f"{len(imp.get('validation_queries', []))} queries")

    sqs = ai_output.get("smart_questions", [])
    print(f"\n\u2753 Smart questions: {len(sqs)}")
    for sq in sqs[:5]:
        print(f"   [{sq.get('type', '?')}] {sq.get('question', '')[:80]}")
        print(f"         resolves: {len(sq.get('resolves_controls', []))} control(s)")

    progress = ai_output.get("progress_analysis", {})
    print(f"\n\U0001f4c8 Progress: {progress.get('velocity', '?')} \u2014 {progress.get('maturity_trend', '')[:80]}")

    out_path = "out/reasoning_engine_output.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(ai_output, f, indent=2)
    print(f"\n\u2713 Full output saved to {out_path}")


if __name__ == "__main__":
    main()
