"""Why-Risk Reasoning Agent — explains WHY a domain is a top risk.

Architecture (clean separation of concerns):

  agent/why_reasoning.py   ← deterministic payload + terminal display (this file)
  agent/why_ai.py          ← AI explanation layer (optional)
  agent/run_loader.py      ← loads runs from disk or demo fixture

Pipeline:
  1. Find the matching risk from executive_summary.top_business_risks
  2. Collect failing/partial controls tied to that risk
  3. Pull dependency impact from the knowledge graph
  4. Map affected controls to roadmap initiatives
  5. Ground initiatives with Microsoft Learn references
  6. (Optional) Send assembled evidence to the reasoning model

Usage:
    from agent.run_loader import load_run
    from agent.why_reasoning import build_why_payload, print_why_report

    run = load_run(demo=True)
    payload = build_why_payload(run, "Networking")
    print_why_report(payload)
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

from graph.knowledge_graph import ControlKnowledgeGraph
from ai.mcp_retriever import search_docs


# ──────────────────────────────────────────────────────────────────
# Step 1 — Locate the target risk
# ──────────────────────────────────────────────────────────────────

def _find_top_risk(run: dict, domain: str) -> dict:
    """Find the top business risk matching the requested domain.

    Matching strategy (in order):
      1. Exact match on ``domain`` or ``affected_domain`` key
      2. Domain keyword appears in the risk ``title``
      3. Majority of ``affected_controls`` belong to the requested section

    Raises ValueError if no match is found.
    """
    risks = (
        run.get("executive_summary", {}).get("top_business_risks", [])
        or run.get("ai", {}).get("executive", {}).get("top_business_risks", [])
    )
    domain_lower = domain.lower()

    # Build control-id → section lookup for strategy 3
    section_of: dict[str, str] = {}
    for c in run.get("results", []):
        cid = c.get("control_id", "")
        if cid:
            section_of[cid] = (c.get("section", "") or "").lower()

    for r in risks:
        # Strategy 1 — explicit domain key
        if domain_lower in (r.get("domain", "") or r.get("affected_domain", "")).lower():
            return r
        # Strategy 2 — keyword in title
        if domain_lower in (r.get("title", "") or "").lower():
            return r
        # Strategy 3 — most affected controls are in the requested section
        affected = r.get("affected_controls", [])
        if affected:
            matching = sum(1 for a in affected if domain_lower in section_of.get(a, ""))
            if matching > len(affected) / 2:
                return r

    available = [r.get("domain", r.get("affected_domain", r.get("title", "?"))) for r in risks]
    raise ValueError(f"No top risk found for domain: {domain}. Available: {available}")


# ──────────────────────────────────────────────────────────────────
# Step 2 — Collect failing controls
# ──────────────────────────────────────────────────────────────────

def _get_failed_controls(run: dict, control_ids: List[str]) -> List[dict]:
    """Return controls that failed or are partial and are in the affected set."""
    results = run.get("results", [])
    affected_set = set(control_ids)
    return [
        {
            "control_id": c["control_id"],
            "text": c.get("text", ""),
            "section": c.get("section", ""),
            "severity": c.get("severity", ""),
            "status": c.get("status", ""),
            "notes": c.get("notes", ""),
        }
        for c in results
        if c.get("control_id") in affected_set and c.get("status") in ("Fail", "Partial")
    ]


# ──────────────────────────────────────────────────────────────────
# Step 3 — Dependency impact from knowledge graph
# ──────────────────────────────────────────────────────────────────

def _get_dependency_impact(kg: ControlKnowledgeGraph, control_ids: List[str]) -> List[dict]:
    """For each failing control, find what downstream controls depend on it."""
    impacts: list[dict] = []
    for cid in control_ids:
        short = cid[:8] if len(cid) > 8 else cid
        dependents = kg.get_dependents(short)
        if dependents:
            node = kg.get_node(short)
            impacts.append({
                "control": short,
                "name": node.name if node else short,
                "blocks": dependents,
                "blocks_count": len(dependents),
            })
    return impacts


# ──────────────────────────────────────────────────────────────────
# Step 4 — Map controls to roadmap initiatives
# ──────────────────────────────────────────────────────────────────

def _map_controls_to_initiatives(run: dict, control_ids: List[str]) -> List[dict]:
    """Find transformation roadmap initiatives tied to affected controls."""
    affected_set = set(control_ids)
    initiatives = (
        run.get("transformation_plan", {}).get("initiatives", [])
        or run.get("transformation_roadmap", {}).get("initiatives", [])
        or run.get("ai", {}).get("initiatives", [])
        or []
    )
    matched: list[dict] = []
    for init in initiatives:
        init_controls = set(init.get("controls", []))
        overlap = init_controls & affected_set
        if overlap:
            matched.append({
                "initiative_id": init.get("initiative_id", ""),
                "title": init.get("title", ""),
                "phase": init.get("phase", ""),
                "controls_addressed": list(overlap),
                "priority": init.get("priority", ""),
            })
    return matched


# ──────────────────────────────────────────────────────────────────
# Step 5 — Ground initiatives with Microsoft Learn
# ──────────────────────────────────────────────────────────────────

def _ground_initiatives(initiatives: List[dict]) -> List[dict]:
    """Attach Microsoft Learn references to each initiative."""
    for init in initiatives:
        title = init.get("title", "")
        try:
            refs = search_docs(f"Azure landing zone {title}", top=2)
            init["learn_references"] = [
                {"title": r.get("title", ""), "url": r.get("url", "")}
                for r in refs
            ]
        except Exception:
            init["learn_references"] = []
    return initiatives


# ──────────────────────────────────────────────────────────────────
# Public API — deterministic payload
# ──────────────────────────────────────────────────────────────────

def build_why_payload(
    run: dict,
    domain: str,
    *,
    verbose: bool = True,
) -> dict:
    """Build the deterministic reasoning payload (no AI).

    Parameters
    ----------
    run : dict
        A loaded run JSON (from out/run-*.json or demo/demo_run.json).
    domain : str
        The domain to explain (e.g. "Networking", "Security", "Governance").
    verbose : bool
        Print progress to stdout.

    Returns
    -------
    dict with keys: domain, risk, failing_controls, dependency_impact,
    roadmap_actions.  May include "error" if no risk matches.
    """
    if verbose:
        print(f"\n🔎 Why is {domain} the top risk?")
        print("─" * 50)

    # 1 — Find the risk
    try:
        risk = _find_top_risk(run, domain)
    except ValueError as e:
        return {"error": str(e)}

    affected = risk.get("affected_controls", [])
    if verbose:
        print(f"  Risk: {risk.get('title', '?')}")
        print(f"  Affected controls: {len(affected)}")

    # 2 — Failing controls
    controls = _get_failed_controls(run, affected)
    if verbose:
        print(f"  Failing/Partial: {len(controls)}")

    # 3 — Dependency impact
    kg = ControlKnowledgeGraph()
    fail_ids = [c["control_id"] for c in controls]
    deps = _get_dependency_impact(kg, fail_ids)
    if verbose:
        blocked = sum(d["blocks_count"] for d in deps)
        print(f"  Downstream blocked: {blocked} control(s)")

    # 4 — Roadmap initiatives
    initiatives = _map_controls_to_initiatives(run, affected)
    if verbose:
        print(f"  Roadmap actions: {len(initiatives)}")

    # 5 — Ground with Learn
    if verbose:
        print("  Grounding with Microsoft Learn …")
    initiatives = _ground_initiatives(initiatives)

    return {
        "domain": domain,
        "risk": risk,
        "failing_controls": controls,
        "dependency_impact": deps,
        "roadmap_actions": initiatives,
    }


# ──────────────────────────────────────────────────────────────────
# Terminal display — judge-friendly formatted output
# ──────────────────────────────────────────────────────────────────

def _short_id(control_id: str) -> str:
    """First 8 chars of a UUID — matches checklist short-ID convention."""
    return control_id[:8] if len(control_id) > 8 else control_id


def _step_to_phase(step_num: int, total_steps: int) -> str:
    """Map a step number to a 30/60/90 day phase label."""
    if total_steps <= 1:
        return "30 days"
    if total_steps == 2:
        return "30 days" if step_num <= 1 else "60 days"
    third = total_steps / 3
    if step_num <= third:
        return "30 days"
    elif step_num <= 2 * third:
        return "60 days"
    return "90 days"


def print_why_report(result: dict) -> None:
    """Render a rich, human-readable terminal report."""

    if "error" in result:
        print(f"\n  ⚠  {result['error']}")
        return

    domain = result.get("domain", "?").upper()
    ai = result.get("ai_explanation", {})
    risk = result.get("risk", {})
    controls = result.get("failing_controls", [])
    deps = result.get("dependency_impact", [])
    actions = result.get("roadmap_actions", [])

    W = 60

    # ── Header ────────────────────────────────────────────────────
    print()
    print("╔" + "═" * W + "╗")
    print("║" + f"  {domain} IS THE TOP RISK".ljust(W) + "║")
    print("╚" + "═" * W + "╝")

    # ── Root cause ────────────────────────────────────────────────
    print()
    print("  Root cause:")
    if ai.get("root_cause"):
        for sentence in ai["root_cause"].replace(". ", ".\n").split("\n"):
            sentence = sentence.strip()
            if sentence:
                print(f"    • {sentence}")
    else:
        cause = risk.get("technical_cause", "")
        if cause:
            for part in cause.split(";"):
                part = part.strip()
                if part:
                    print(f"    • {part}")

    # ── Failing controls ──────────────────────────────────────────
    if controls:
        print()
        print("  Failing controls:")
        for c in controls:
            sid = _short_id(c["control_id"])
            icon = "✗" if c["status"] == "Fail" else "◑"
            print(f"    {icon} {sid} – {c['text']}")
            if c.get("notes"):
                note = c["notes"][:120] + (" …" if len(c["notes"]) > 120 else "")
                print(f"      └─ {note}")

    # ── Dependency impact ─────────────────────────────────────────
    if deps:
        print()
        print("  Dependency impact:")
        print("  Blocks:")
        try:
            kg = ControlKnowledgeGraph()
        except Exception:
            kg = None
        for d in deps:
            for blocked_id in d.get("blocks", []):
                if kg:
                    node = kg.get_node(blocked_id)
                    name = node.name if node else blocked_id
                else:
                    name = blocked_id
                print(f"    ↳ {name}")

    # ── Business impact (AI) ──────────────────────────────────────
    if ai.get("business_impact"):
        print()
        print("  Business impact:")
        print(f"    {ai['business_impact']}")

    # ── Fix sequence / Roadmap actions ────────────────────────────
    fix_seq = ai.get("fix_sequence", [])
    if fix_seq:
        print()
        print("  Roadmap actions:")
        for step in fix_seq:
            n = step.get("step", "?")
            action = step.get("action", "")
            url = step.get("learn_url", "")
            phase = _step_to_phase(n, len(fix_seq))
            print(f"    {phase} → {action}")
            if step.get("why_this_order"):
                print(f"      Why first: {step['why_this_order'][:120]}")
            if url:
                print(f"      Learn: {url}")
    elif actions:
        print()
        print("  Roadmap actions:")
        for a in actions:
            phase = a.get("phase", "")
            label = f"{phase} → " if phase else "• "
            print(f"    {label}{a.get('title', '?')}")
            for ref in a.get("learn_references", []):
                if ref.get("url"):
                    print(f"      Learn: {ref['url']}")

    # ── Cascade effect (AI) ───────────────────────────────────────
    if ai.get("cascade_effect"):
        print()
        print("  Cascade effect:")
        print(f"    {ai['cascade_effect']}")

    # ── Footer ────────────────────────────────────────────────────
    print()
    print("─" * (W + 2))
