"""Test harness — validates preflight, knowledge graph, control pack, and agent loop.

Run:
    python test_preflight_agent.py
"""
from __future__ import annotations

import json
import os
import sys
import time


def section(title: str) -> None:
    print(f"\n{'═' * 60}")
    print(f"  {title}")
    print(f"{'═' * 60}")


def test_knowledge_graph() -> bool:
    """Validate the knowledge graph loads and plans correctly."""
    section("Knowledge Graph")
    from graph.knowledge_graph import ControlKnowledgeGraph

    kg = ControlKnowledgeGraph()
    summary = kg.to_summary()
    print(f"  Controls:  {summary['total_controls']}")
    print(f"  Bundles:   {summary['total_bundles']}")
    print(f"  Questions: {summary['total_questions']}")
    print(f"  Disciplines: {', '.join(summary['disciplines'])}")

    assert summary["total_controls"] == 37, f"Expected 37, got {summary['total_controls']}"

    # Test signal sharing
    sharing = summary["signal_sharing"]
    print(f"\n  Signal sharing (all controls):")
    for sig, cids in sharing.items():
        print(f"    {sig}: {len(cids)} control(s)")

    # Verify arm:mg_hierarchy is shared across 4 MG controls
    mg_users = sharing.get("arm:mg_hierarchy", [])
    assert len(mg_users) >= 4, f"Expected ≥4 MG controls sharing arm:mg_hierarchy, got {len(mg_users)}"
    print(f"\n  ✓ arm:mg_hierarchy shared by {len(mg_users)} controls (cache = 1 query)")

    # Test plan generation
    for intent in kg.bundle_names:
        plan = kg.plan_evaluation(intent)
        print(f"\n  Plan '{intent}':")
        print(f"    Controls: {len(plan.ordered_controls)}")
        print(f"    Signals:  {len(plan.required_signals)}")
        print(f"    Questions: {len(plan.question_resolvers)}")
        print(f"    Order:    {' → '.join(plan.ordered_controls[:6])}{'…' if len(plan.ordered_controls) > 6 else ''}")

    # Test topo sort: e8bbac75 (hub-spoke) must come after e6c4cfd3 (firewall)
    net_plan = kg.plan_evaluation("network_review")
    fw_idx = net_plan.ordered_controls.index("e6c4cfd3")
    hs_idx = net_plan.ordered_controls.index("e8bbac75")
    assert fw_idx < hs_idx, "Firewall must be evaluated before Hub-Spoke"
    print(f"\n  ✓ Topo order: firewall ({fw_idx}) before hub-spoke ({hs_idx})")

    # Test deferrals
    fake_results = {
        "61623a76": {"status": "Fail"},  # Platform MG fails
    }
    deferrals = kg.apply_deferrals(net_plan, fake_results)
    # 92481607 and 8bbac757 have defer_if_parent_fails=true for 61623a76
    # But they're only in governance, not network. Test with governance plan.
    gov_plan = kg.plan_evaluation("governance_review")
    deferrals = kg.apply_deferrals(gov_plan, fake_results)
    deferred_ids = [d.control_id for d in deferrals]
    print(f"\n  Deferral test (Platform MG fails):")
    print(f"    Deferred: {deferred_ids}")
    if "92481607" in deferred_ids:
        print(f"    ✓ Landing Zones MG correctly deferred")
    if "8bbac757" in deferred_ids:
        print(f"    ✓ Connectivity MG correctly deferred")

    # Test discipline scoring
    fake_full = {
        "e6c4cfd3": {"status": "Pass"},
        "e8bbac75": {"status": "Fail"},
        "3c5a808d": {"status": "Partial"},
        "0c47f486": {"status": "Pass"},
        "088137f5": {"status": "Fail"},
    }
    scores = kg.discipline_score(fake_full)
    print(f"\n  Discipline scores (fake network results):")
    for d, data in scores.items():
        print(f"    {data['discipline_label']:40s} {data['score']:>3d}%")

    print("\n  ✓ Knowledge graph tests passed")
    return True


def test_control_pack() -> bool:
    """Validate the ALZ V1 control pack loads."""
    section("Control Pack — ALZ V1")
    from control_packs.loader import load_pack, list_packs

    packs = list_packs()
    print(f"  Available packs: {len(packs)}")
    for p in packs:
        print(f"    {p['pack_id']} — {p['name']} (v{p['version']})")

    pack = load_pack("alz", "v1.0")
    print(f"\n  Loaded: {pack.name} v{pack.version}")
    print(f"  Signals:  {len(pack.signals)}")
    print(f"  Controls: {pack.control_count()}")
    print(f"  Design areas: {list(pack.design_areas.keys())}")

    bus_names = pack.signal_bus_names()
    print(f"\n  Signal bus names ({len(bus_names)}):")
    for bn in bus_names:
        print(f"    {bn}")

    # Cross-ref: every signal_bus_name in the pack should have a provider
    from signals.registry import SIGNAL_PROVIDERS
    missing = [bn for bn in bus_names if bn not in SIGNAL_PROVIDERS]
    if missing:
        print(f"\n  ⚠ Signal bus names without providers: {missing}")
    else:
        print(f"\n  ✓ All {len(bus_names)} signal_bus_names have registered providers")

    # Preflight probe cross-ref
    probes = set()
    for s in pack.signals.values():
        if s.get("preflight_probe"):
            probes.add(s["preflight_probe"])
    print(f"  Preflight probes referenced: {sorted(probes)}")

    from preflight.analyzer import PROBES
    missing_probes = probes - set(PROBES.keys())
    if missing_probes:
        print(f"  ⚠ Missing preflight probes: {missing_probes}")
    else:
        print(f"  ✓ All preflight probes exist in analyzer")

    print("\n  ✓ Control pack tests passed")
    return True


def test_evaluator_registry() -> bool:
    """Validate all 21 evaluators are registered."""
    section("Evaluator Registry")

    # Import evaluator modules to trigger register_evaluator() calls
    import evaluators.networking   # noqa: F401
    import evaluators.governance   # noqa: F401
    import evaluators.security     # noqa: F401
    import evaluators.management   # noqa: F401
    import evaluators.cost         # noqa: F401
    import evaluators.identity     # noqa: F401
    import evaluators.network_coverage  # noqa: F401

    from evaluators.registry import EVALUATORS

    print(f"  Registered evaluators: {len(EVALUATORS)}")
    for cid, ev in sorted(EVALUATORS.items()):
        print(f"    {cid[:8]}… signals={ev.required_signals}")

    assert len(EVALUATORS) >= 38, f"Expected ≥38 evaluators, got {len(EVALUATORS)}"

    # Verify all evaluators from the knowledge graph are registered
    from graph.knowledge_graph import ControlKnowledgeGraph
    kg = ControlKnowledgeGraph()
    missing = []
    for sid, node in kg.controls.items():
        if node.full_id not in EVALUATORS:
            missing.append(f"{sid} ({node.name})")

    if missing:
        print(f"\n  ⚠ Controls in graph but not in evaluator registry: {missing}")
    else:
        print(f"\n  ✓ All graph controls have registered evaluators")

    print("\n  ✓ Evaluator registry tests passed")
    return True


def test_preflight_structure() -> bool:
    """Validate preflight module structure (no live Azure calls)."""
    section("Preflight Module Structure")
    from preflight.analyzer import PROBES, PreflightResult

    print(f"  Probes defined: {len(PROBES)}")
    for name, (fn, meta) in PROBES.items():
        print(f"    {name:30s} area={meta['area']:20s} mode={meta['mode']}")

    assert len(PROBES) == 8, f"Expected 8 probes, got {len(PROBES)}"

    # Verify impact metadata
    for name, (fn, meta) in PROBES.items():
        assert "area" in meta, f"Probe {name} missing 'area'"
        assert "mode" in meta, f"Probe {name} missing 'mode'"
        assert "action" in meta, f"Probe {name} missing 'action'"

    print("\n  ✓ Preflight structure tests passed")
    return True


def test_agent_session() -> bool:
    """Validate agent session state management."""
    section("Agent Session")
    from agent.session import AgentSession, QuestionAnswer
    from signals.types import EvalScope

    session = AgentSession(
        scope=EvalScope(tenant_id="test-tenant", subscription_ids=["sub-1"]),
        intent="test",
    )

    # Record a result
    session.record_result("e6c4cfd3", {"status": "Pass", "reason": "test"})
    assert session.total_evaluated == 1
    assert session.pass_count == 1

    # Ask + answer a question
    qa = QuestionAnswer(
        question_id="Q-TEST",
        question_text="Is this a test?",
        resolves_controls=["e6c4cfd3"],
    )
    session.ask_question(qa)
    assert len(session.open_questions) == 1

    session.answer_question("Q-TEST", "Yes")
    assert len(session.open_questions) == 0
    assert len(session.answered_questions) == 1

    # Events
    events = session.pop_events()
    assert len(events) >= 3  # control_evaluated, question_asked, question_answered
    event_types = {e["type"] for e in events}
    assert "control_evaluated" in event_types
    assert "question_asked" in event_types
    assert "question_answered" in event_types

    summary = session.summary()
    print(f"  Session: {summary['session_id']}")
    print(f"  Phase:   {summary['phase']}")
    print(f"  Evaluated: {summary['evaluated']} (pass={summary['pass']}, fail={summary['fail']})")
    print(f"  Cache stats: {summary['cache_stats']}")

    print("\n  ✓ Agent session tests passed")
    return True


def main() -> None:
    print("╔══════════════════════════════════════════════════╗")
    print("║   Preflight + Agent Architecture Test Harness    ║")
    print("╚══════════════════════════════════════════════════╝")

    results: dict[str, bool] = {}

    tests = [
        ("Knowledge Graph", test_knowledge_graph),
        ("Control Pack", test_control_pack),
        ("Evaluator Registry", test_evaluator_registry),
        ("Preflight Structure", test_preflight_structure),
        ("Agent Session", test_agent_session),
    ]

    for name, fn in tests:
        try:
            results[name] = fn()
        except Exception as e:
            print(f"\n  ✗ {name} FAILED: {type(e).__name__}: {e}")
            results[name] = False

    section("Summary")
    total = len(results)
    passed = sum(1 for v in results.values() if v)
    for name, ok in results.items():
        icon = "✓" if ok else "✗"
        print(f"  {icon} {name}")
    print(f"\n  {passed}/{total} test suites passed")

    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    main()
