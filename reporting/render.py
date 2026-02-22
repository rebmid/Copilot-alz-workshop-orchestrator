from jinja2 import Environment, FileSystemLoader, select_autoescape
import os, re

from schemas.taxonomy import bucket_domain as _bucket_domain
from engine.scoring import section_scores as _compute_section_scores


# ── Signal-type classification (locked rules) ────────────────────
def _signal_type(ctrl: dict) -> str:
    """Classify a control's signal type.

    Rules (locked):
      - signal_used present and single  → Confirmed
      - signal_used present and comma   → Derived
      - status == 'Manual' AND no signal → Assumed
    """
    sig = ctrl.get("signal_used")
    if sig:
        return "Derived" if "," in str(sig) else "Confirmed"
    if ctrl.get("status") == "Manual":
        return "Assumed"
    return "Assumed"


# ── Confidence badge thresholds ──────────────────────────────────
def _confidence_badge(value) -> str:
    """Map a numeric confidence (0-1) or string to ⚠/Medium/High."""
    if isinstance(value, str):
        val_map = {"high": 1.0, "medium": 0.8, "low": 0.5}
        value = val_map.get(value.lower(), 0.5)
    if value is None:
        return "Unknown"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "Unknown"
    if v < 0.7:
        return "Low"
    if v <= 0.9:
        return "Medium"
    return "High"


def _confidence_numeric(ctrl: dict) -> float:
    """Convert a control's confidence to a float 0-1."""
    c = ctrl.get("confidence")
    if isinstance(c, (int, float)):
        return float(c) if c <= 1 else c / 100.0
    mapping = {"high": 1.0, "medium": 0.8, "low": 0.5}
    return mapping.get(str(c).lower(), 0.5) if c else 0.5


def _domain_for_question(question: dict, results_by_id: dict) -> str:
    """Best-effort domain assignment for a smart question."""
    for key in ("domain", "category"):
        val = question.get(key)
        if val:
            return val
    sections: dict[str, int] = {}
    for cid in question.get("resolves_controls", []):
        ctrl = results_by_id.get(cid)
        if ctrl:
            s = ctrl.get("section", "Other")
            sections[s] = sections.get(s, 0) + 1
    if sections:
        return max(sections, key=sections.get)
    return "General"


# ═════════════════════════════════════════════════════════════════
#  REPORT CONTEXT BUILDER  — 5-Section CSA Decision-Driven Layout
# ═════════════════════════════════════════════════════════════════

def _build_report_context(output: dict) -> dict:
    """
    Derive the 5-section CSA Decision-Driven report context from
    structured JSON fields only.  No scoring-engine changes.

    Sections:
      1. Foundation Gate
      2. Top Business Risks (cards)
      3. 30/60/90 Roadmap
      4. Design Area Breakdown (hierarchical)
      5. Workshop Decision Funnel
    """
    scoring = output.get("scoring", {})
    ai = output.get("ai", {})
    meta = output.get("meta", {})
    exec_ctx = output.get("execution_context", {})
    results = output.get("results", [])
    results_by_id = {r["control_id"]: r for r in results if "control_id" in r}
    auto_cov = scoring.get("automation_coverage", {})

    # Shared lookups
    esr = ai.get("enterprise_scale_readiness", {})
    executive = ai.get("executive", {})
    initiatives = ai.get("initiatives", [])
    init_by_id = {i["initiative_id"]: i for i in initiatives if "initiative_id" in i}
    roadmap_src = ai.get("transformation_roadmap", {})
    trajectory = roadmap_src.get("maturity_trajectory", {})

    # ── 1. FOUNDATION GATE ────────────────────────────────────────
    ready = esr.get("ready_for_enterprise_scale")
    blockers_raw = esr.get("blockers", [])
    min_inits = esr.get("minimum_initiatives_required", [])

    gate_blockers = []
    for b in blockers_raw:
        resolving_id = b.get("resolving_initiative", "")
        resolving_init = init_by_id.get(resolving_id, {})
        # Derive confidence from controls in that initiative
        init_controls = resolving_init.get("controls", [])
        conf_values = [_confidence_numeric(results_by_id[c])
                       for c in init_controls if c in results_by_id]
        avg_conf = sum(conf_values) / len(conf_values) if conf_values else None
        # Derive dependencies from resolving initiative
        deps = resolving_init.get("dependencies", [])
        dep_titles = [init_by_id[d].get("title", d)
                      for d in deps if d in init_by_id] if deps else []

        gate_blockers.append({
            "category": b.get("category", "Unknown"),
            "description": b.get("description", ""),
            "severity": b.get("severity", ""),
            "resolving_initiative_id": resolving_id,
            "resolving_initiative_title": resolving_init.get("title", resolving_id),
            "confidence": _confidence_badge(avg_conf),
            "dependencies": dep_titles,
        })

    # Improvement opportunities (when ready): scaling recommendations
    improvement_opportunities = esr.get("scaling_recommendations", [])

    foundation_gate = {
        "ready": ready,
        "readiness_score": esr.get("readiness_score"),
        "max_subscriptions": esr.get("max_supported_subscriptions_current_state"),
        "blockers": gate_blockers,
        "minimum_initiatives": min_inits,
        "improvement_opportunities": improvement_opportunities,
        "overall_maturity": scoring.get("overall_maturity_percent"),
        "automated_controls": auto_cov.get("automated_controls", auto_cov.get("data_driven", 0)),
        "total_controls": auto_cov.get("total_controls", 0),
        "automation_percent": auto_cov.get("automation_percent"),
    }

    # ── 2. TOP BUSINESS RISKS (card layout) ──────────────────────
    raw_risks = executive.get("top_business_risks", [])[:5]

    risk_cards = []
    for risk in raw_risks:
        affected = risk.get("affected_controls", [])
        # Derive design area from majority section of affected controls
        section_counts: dict[str, int] = {}
        ctrl_confs: list[float] = []
        for cid in affected:
            ctrl = results_by_id.get(cid, {})
            sec = ctrl.get("section")
            if sec:
                section_counts[sec] = section_counts.get(sec, 0) + 1
            ctrl_confs.append(_confidence_numeric(ctrl))
        design_area = max(section_counts, key=section_counts.get) if section_counts else "Unknown"
        avg_risk_conf = sum(ctrl_confs) / len(ctrl_confs) if ctrl_confs else None

        # Derive signal type badge (majority of affected controls)
        sig_counts = {"Confirmed": 0, "Derived": 0, "Assumed": 0}
        for cid in affected:
            ctrl = results_by_id.get(cid, {})
            sig_counts[_signal_type(ctrl)] += 1
        signal_badge = max(sig_counts, key=sig_counts.get) if any(sig_counts.values()) else "Assumed"

        # Derive fix initiative by matching affected_controls ∩ init.controls
        fix_initiative = None
        for init in initiatives:
            if set(affected) & set(init.get("controls", [])):
                fix_initiative = {
                    "id": init.get("initiative_id"),
                    "title": init.get("title"),
                    "blast_radius": init.get("blast_radius"),
                }
                break

        # Score drivers (structured, from metadata)
        status_breakdown = {"Fail": 0, "Partial": 0, "Pass": 0, "Manual": 0}
        severity_set = set()
        for cid in affected:
            ctrl = results_by_id.get(cid, {})
            st = ctrl.get("status", "Manual")
            status_breakdown[st] = status_breakdown.get(st, 0) + 1
            sev = ctrl.get("severity")
            if sev:
                severity_set.add(sev)

        score_drivers = []
        if "Critical" in severity_set or "High" in severity_set:
            score_drivers.append(f"Contains {', '.join(sorted(severity_set))} severity controls")
        score_drivers.append(f"{len(affected)} affected control(s)")
        if status_breakdown.get("Fail", 0):
            score_drivers.append(f"{status_breakdown['Fail']} in Fail state")
        if fix_initiative:
            score_drivers.append(f"Blast radius: {fix_initiative['blast_radius']}")

        risk_cards.append({
            "title": risk.get("title", ""),
            "design_area": design_area,
            "risk_level": risk.get("severity", "Medium"),
            "signal_badge": signal_badge,
            "confidence": _confidence_badge(avg_risk_conf),
            "business_impact": risk.get("business_impact", ""),
            "technical_cause": risk.get("technical_cause", ""),
            "score_drivers": score_drivers,
            "fix_initiative": fix_initiative,
            "affected_count": len(affected),
        })

    # ── 3. 30/60/90 ROADMAP ──────────────────────────────────────
    roadmap_phases = roadmap_src.get("roadmap_30_60_90", {})
    phase_labels = [
        ("30_days", "0–30 Days", "Foundational blockers"),
        ("60_days", "30–60 Days", "Risk reducers"),
        ("90_days", "60–90 Days", "Optimization"),
    ]

    roadmap_sections = []
    for phase_key, phase_label, phase_desc in phase_labels:
        entries = roadmap_phases.get(phase_key, [])
        phase_items = []
        for entry in entries:
            iid = entry.get("initiative_id", "")
            init = init_by_id.get(iid, {})
            controls = init.get("controls", [])

            # Risks reduced: count of top_business_risks whose affected_controls
            # overlap with this initiative's controls
            risks_reduced = 0
            for risk in raw_risks:
                if set(risk.get("affected_controls", [])) & set(controls):
                    risks_reduced += 1

            # Prerequisites (dependencies)
            deps = entry.get("dependency_on", [])
            # Estimated effort from initiative.delivery_model
            effort = init.get("delivery_model", {}).get("estimated_duration", "")
            blast = init.get("blast_radius", "")

            phase_items.append({
                "initiative_id": iid,
                "title": entry.get("action", init.get("title", "")),
                "caf_discipline": entry.get("caf_discipline", init.get("caf_discipline", "")),
                "controls_count": len(controls),
                "risks_reduced": risks_reduced,
                "dependencies": deps,
                "estimated_effort": effort,
                "blast_radius": blast,
                "owner_role": entry.get("owner_role", init.get("owner_role", "")),
                "success_criteria": entry.get("success_criteria", init.get("success_criteria", "")),
            })

        roadmap_sections.append({
            "key": phase_key,
            "label": phase_label,
            "description": phase_desc,
            "entries": phase_items,
        })

    # ── 4. DESIGN AREA BREAKDOWN (hierarchical) ──────────────────
    section_scores = _compute_section_scores(results) if results else scoring.get("section_scores", [])

    # Group results by section
    controls_by_section: dict[str, list] = {}
    for r in results:
        sec = r.get("section", "Other")
        controls_by_section.setdefault(sec, []).append(r)

    design_areas = []
    for ss in section_scores:
        sec_name = ss["section"]
        sec_controls = controls_by_section.get(sec_name, [])

        # Per-control enrichment for the controls table
        enriched_controls = []
        conf_values = []
        for ctrl in sec_controls:
            sig_type = _signal_type(ctrl)
            conf_val = _confidence_numeric(ctrl)
            conf_values.append(conf_val)

            # "Why We Think This" from notes + evidence + signal_used
            why_parts = []
            sig = ctrl.get("signal_used")
            if sig:
                why_parts.append(f"Signal: {sig}")
            notes = ctrl.get("notes")
            if notes:
                why_parts.append(notes)
            evidence = ctrl.get("evidence", [])
            if evidence:
                for ev in evidence[:3]:
                    if isinstance(ev, dict):
                        why_parts.append(str(ev.get("detail", ev.get("value", ""))))
                    elif isinstance(ev, str):
                        why_parts.append(ev)

            enriched_controls.append({
                "control_id": ctrl.get("control_id", ""),
                "text": ctrl.get("text", ctrl.get("question", "")),
                "status": ctrl.get("status", "Manual"),
                "signal_type": sig_type,
                "why": " · ".join(why_parts) if why_parts else "No signal data available",
                "severity": ctrl.get("severity", ""),
                "confidence": _confidence_badge(conf_val),
            })

        # Section-level confidence: average of control confidences
        avg_section_conf = sum(conf_values) / len(conf_values) if conf_values else None

        design_areas.append({
            "section": sec_name,
            "maturity_percent": ss.get("maturity_percent"),
            "counts": ss.get("counts", {}),
            "automated_controls": ss.get("automated_controls", 0),
            "total_controls": ss.get("total_controls", 0),
            "automation_percent": ss.get("automation_percent", 0),
            "critical_fail_count": ss.get("critical_fail_count", 0),
            "critical_partial_count": ss.get("critical_partial_count", 0),
            "confidence": _confidence_badge(avg_section_conf),
            "controls": enriched_controls,
        })

    # Sort by risk: critical fails desc, maturity asc
    design_areas.sort(key=lambda s: (
        -(s.get("critical_fail_count", 0) + s.get("critical_partial_count", 0)),
        s["maturity_percent"] if s["maturity_percent"] is not None else 9999,
        s["section"],
    ))

    # ── 5. WORKSHOP DECISION FUNNEL ──────────────────────────────
    smart_qs = ai.get("smart_questions", [])

    # Build per-domain grouping
    domain_questions: dict[str, list] = {}
    for q in smart_qs:
        domain = _bucket_domain(_domain_for_question(q, results_by_id))
        domain_questions.setdefault(domain, []).append(q)

    # Build per-domain risks and blockers
    domain_risks: dict[str, list] = {}
    for risk in raw_risks:
        for cid in risk.get("affected_controls", []):
            ctrl = results_by_id.get(cid, {})
            sec = ctrl.get("section")
            if sec:
                domain = _bucket_domain(sec)
                domain_risks.setdefault(domain, [])
                if risk not in domain_risks[domain]:
                    domain_risks[domain].append(risk)

    domain_blockers: dict[str, list] = {}
    for b in blockers_raw:
        cat = b.get("category", "")
        domain = _bucket_domain(cat) if cat else "General"
        domain_blockers.setdefault(domain, []).append(b)

    # All domains that have questions, risks, or blockers
    all_domains = sorted(set(
        list(domain_questions.keys()) +
        list(domain_risks.keys()) +
        list(domain_blockers.keys())
    ))

    workshop_funnel = []
    for domain in all_domains:
        d_risks = domain_risks.get(domain, [])[:3]
        d_blockers = domain_blockers.get(domain, [])[:3]
        d_questions = domain_questions.get(domain, [])[:3]

        # Count controls impacted if questions/smart-qs are implemented
        controls_impacted = set()
        for q in domain_questions.get(domain, []):
            controls_impacted.update(q.get("resolves_controls", []))

        workshop_funnel.append({
            "domain": domain,
            "risks": [{"title": r.get("title"), "severity": r.get("severity")} for r in d_risks],
            "blockers": [{"description": b.get("description"), "severity": b.get("severity")} for b in d_blockers],
            "questions": [{
                "question": q.get("question", ""),
                "type": q.get("type", ""),
                "follow_up": q.get("follow_up_recommendation", ""),
                "impact_if_yes": q.get("impact_if_yes", ""),
                "impact_if_no": q.get("impact_if_no", ""),
                "controls_impacted": len(q.get("resolves_controls", [])),
            } for q in d_questions],
            "total_controls_impacted": len(controls_impacted),
        })

    return {
        "foundation_gate": foundation_gate,
        "risk_cards": risk_cards,
        "roadmap_sections": roadmap_sections,
        "trajectory": trajectory if isinstance(trajectory, dict) else {},
        "design_areas": design_areas,
        "workshop_funnel": workshop_funnel,
    }


def generate_report(output: dict, template_name: str = "report_template.html", out_path: str = None):
    base_dir = os.path.dirname(__file__)
    env = Environment(
        loader=FileSystemLoader(base_dir),
        autoescape=select_autoescape(["html", "xml"])
    )

    # Build derived report context and merge
    report_ctx = _build_report_context(output)
    context = {**output, **report_ctx}

    template = env.get_template(template_name)
    html = template.render(**context)

    if out_path is None:
        out_path = os.path.join(os.getcwd(), "report.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
