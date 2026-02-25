# CONTRIBUTING.md

## Copilot SDK–Governed Azure Landing Zone Orchestration Platform

---

# 1. Repository Purpose

This repository implements a **GitHub Copilot SDK–powered orchestration layer** over a deterministic Azure Landing Zone (ALZ) governance engine.

The deterministic engine performs all:

* Azure state collection
* Control evaluation
* Scoring
* Delta computation

GitHub Copilot SDK provides:

* Intent routing
* Tool orchestration
* Structured summarization
* Narrative generation

Copilot does **not** perform scoring, evaluation, delta computation, or infrastructure modification.

### Current Repository Status

* Copilot SDK integration is implemented.
* MVP tool surface (intent selection, run execution, summarization) exists.
* Output refinement and structured validation improvements are ongoing.
* Deterministic engine remains unchanged and authoritative.

This system is designed to:

* Scale CSA-led workshops
* Enable continuous ALZ posture tracking
* Support intentional, scoped governance assessments

---

# 2. Problems This System Solves

### Problem A — Workshops Don't Scale

Manual CSA facilitation introduces variability and human bottlenecks.

### Problem B — Posture Drift

Point-in-time assessments become stale without automated delta tracking.

### Problem C — "Run Everything" Noise

Full scans are inefficient for time-boxed or domain-specific engagements.

All contributions must align with solving one or more of these problems.

---

# 3. Value Created

## Business / Field Value

* Faster time-to-insight in workshops via guided orchestration.
* More consistent delivery through deterministic + guardrailed execution.
* Continuous posture visibility with actionable delta tracking.
* Automated generation of tracking artifacts (issues/reports).

## Engineering Value

* Shared `intent → scope → run → summarize` pipeline across workshop and CI/CD.
* Reusable deterministic execution path.
* Clear separation between evaluation logic and AI summarization.
* Guardrails that prevent AI authority expansion.

---

# 4. System Architecture

This platform uses **one orchestration surface and two entry points**.

## Entry Point A — Interactive Workshop

User → Copilot SDK → Intent selection → Scoped run → Evidence summary

## Entry Point B — CI/CD Continuous Posture

Trigger → Intent → Deterministic run → Delta → Copilot summary → Artifact

## Core Pipeline

```
Intent (schema)
  → Scope resolution
    → Deterministic run
      → Delta computation
        → Copilot summarization
          → Outputs (issues / reports / dialogue)
```

The deterministic engine remains authoritative.
Copilot is an orchestration layer.

---

# 5. Azure Access Model

This repository may operate against live Azure environments using **read-only access**.

### Permitted

* Azure state collection via deterministic collectors
* Read-only API access required for governance evaluation
* Evidence retrieval for scoring and reporting

### Prohibited

* Azure resource mutation
* Remediation execution
* Infrastructure modification
* Privileged write operations

### Enforcement Rules

* Azure access must use least-privilege read-only roles.
* Copilot SDK must never directly call Azure APIs.
* Azure authentication and RBAC configuration must occur outside Copilot logic.
* Copilot consumes structured deterministic output only.

Architecture boundary:

```
Azure → Deterministic Engine → Copilot → Structured Output
```

Never:

```
Copilot → Azure
```

---

# 6. Architectural Invariants (DO NOT BREAK)

These constraints are non-negotiable.

## Deterministic Authority

* Collectors, evaluators, and scoring logic must not be modified by Copilot.
* Delta computation must remain deterministic.
* Control definitions must not be generated or altered by AI.
* Governance logic must remain version-controlled.

## Environment Safety

* No Azure resource mutation.
* No remediation logic via Copilot.
* No infrastructure changes initiated by the agent.
* No privilege escalation.

## Tool Surface Restrictions

* Copilot may only call predefined tool handlers.
* No arbitrary shell execution.
* No dynamic evaluator injection.
* No runtime control-pack expansion outside intent schema.
* Copilot must never invent scope; it may only select from declared intents.

## File System Guardrails

* All writes must remain inside `out/`.
* No external persistence of tenant data.
* No uncontrolled artifact storage.

PRs violating these invariants will be rejected.

---

# 7. Copilot SDK Boundaries

Copilot may:

* Select from predefined intents.
* Call approved tool handlers.
* Summarize deterministic run results.
* Explain delta impacts.
* Provide structured executive narratives.

Copilot must not:

* Compute deltas.
* Modify scoring.
* Select evaluators dynamically.
* Alter governance logic.
* Suggest environment mutations.
* Access Azure APIs directly.

Copilot is an orchestrator — not a governance authority.

---

# 8. Implementation Design (Options 5 + 6)

This repository integrates:

## Option 6 — Intent Router 2.0

Structured, declarative intent-based scope selection (e.g., identity focus, time-boxed sessions, regulated tenant scenarios).

## Option 5 — Continuous ALZ Posture

Scheduled scans, deterministic delta computation, Copilot summarization, and automatic creation of tracking artifacts (GitHub Issues or report output).

These are designed together using a shared intent schema to avoid duplicated execution paths.

---

# 9. Step-by-Step Contribution Guidance

## Step 0 — Baseline Validation

Before introducing changes:

* Confirm `scan.py` remains the single deterministic entry point.
* Confirm collectors, evaluators, and scoring are untouched.
* Confirm Copilot SDK remains orchestration-only.

If any of these are violated, stop and correct first.

---

## Step 1 — Introduce Intent Schema

Create or modify:

```
/agent/intents.py
```

Intent definitions must include:

* name
* description
* domains
* timebox
* control_packs

Intents are declarative only.
No dynamic logic or runtime evaluator injection.

---

## Step 2 — Implement available_intents()

Must:

* Return intent names + descriptions only.
* Not execute scans.
* Prevent Copilot from inventing scope.
* Ensure scope selection is auditable and testable.

---

## Step 3 — Implement run_intent()

```
run_intent(intent_name, overrides) → RunResult
```

Must:

* Resolve intent → control packs.
* Call deterministic execution path.
* Return run_id + metadata.

Must not:

* Inject evaluators dynamically.
* Modify scoring logic.
* Expand tool surface implicitly.

---

## Step 4 — Log Intent Decisions

Each run must record:

* selected_intent
* intent_reason
* resolved_scope
* timestamp
* prior_run_reference (if delta mode)

This ensures workshop transparency and CI traceability.

---

## Step 5 — CI/CD Continuous Posture

CI mode must:

1. Use intent schema.
2. Execute deterministic run.
3. Compute deterministic delta.
4. Pass structured delta JSON to Copilot.
5. Publish artifacts.

### Supported Output Targets

* GitHub Issue containing delta summary
* Structured report artifact (HTML / Markdown)
* Input artifact for subsequent workshop session

Copilot must not compute delta logic.

---

## Step 6 — Deterministic Delta Enforcement

Delta logic must:

* Compare previous and current run JSON.
* Identify newly failing and newly passing controls.
* Compute domain score differences.

No AI involvement in scoring or delta computation.

---

## Why This Sequencing Matters

* Intent schema first prevents scope drift.
* Shared `run_intent()` ensures one execution path for workshop and CI.
* Deterministic delta preserves scoring authority.
* Copilot remains explanatory, not analytical.

This preserves deterministic-first architecture while enabling orchestration flexibility.

---

# 10. Logging & Audit Requirements

All Copilot tool calls must log:

* tool_name
* arguments
* run_id

All run artifacts must include:

* intent metadata
* resolved scope
* delta reference (if applicable)

Failures must be logged with run_id and must not trigger fabricated summaries.

The system must remain enterprise-auditable.

---

# 11. Data Handling & Privacy

* Azure tenant data is processed for assessment purposes only.
* No environment data is retained outside `out/`.
* Copilot does not persist tenant data.
* Logs must not expose sensitive identifiers beyond necessary evidence references.
* External telemetry must not include tenant-sensitive data.

---

# 12. Testing Requirements

All contributions must include:

* Unit tests for new tools.
* Guardrail enforcement tests.
* Intent resolution validation tests.
* Delta stability tests (if modified).

Tests must not require live Azure access.

---

# 13. PR Submission Checklist

Before submitting:

* [ ] Deterministic engine unchanged.
* [ ] No expansion of AI authority.
* [ ] Guardrails preserved.
* [ ] No Azure mutation introduced.
* [ ] No writes outside `out/`.
* [ ] Logging added where applicable.
* [ ] Tests included.
* [ ] Documentation updated.

---

# 14. Responsible AI Model

This repository enforces one-way data flow:

```
Azure → Deterministic Engine → Copilot → Structured Output
```

AI outputs must:

* Be grounded in deterministic run JSON.
* Not alter governance logic.
* Not mutate infrastructure.
* Not compute scoring.
* Not persist external data.

This is a governed orchestration system — not a general-purpose autonomous agent.

---

# Final Positioning

This repository represents:

* Deterministic governance authority
* Guardrailed Copilot orchestration
* Enterprise-ready architecture
* Read-only Azure assessment capability
* Intent-driven scope control
* Continuous posture enforcement

Any contribution must preserve that posture.