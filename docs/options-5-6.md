# Options 5 & 6 — Continuous ALZ Posture and Intent Router 2.0

This document defines the scope, guardrails, and acceptance criteria for implementing
**Option 5 (Continuous ALZ Posture)** and **Option 6 (Intent Router 2.0)** in the
Copilot‑ALZ Workshop Orchestrator.

These options build on the existing deterministic Azure Landing Zone (ALZ) assessment
engine by adding a **GitHub Copilot SDK–based orchestration layer**. The deterministic
engine remains the source of truth for scoring and evidence; Copilot is used strictly
for orchestration, planning, and summarization.

---

## Architectural Principles (Non‑Negotiable)

The following constraints apply to **both options**:

- Deterministic ALZ assessment logic is **not modified**
- Copilot SDK **does not change scoring results**
- No environment mutation or remediation
- Read‑only Azure access (RBAC‑controlled)
- File writes are restricted to the local output directory (e.g. `out/`)
- One‑way data flow: deterministic outputs → Copilot summarization

These guardrails preserve auditability, credibility, and enterprise safety.

---

## Option 6 — Intent Router 2.0 (Targeted Assessments)

### Problem Addressed
Running a full ALZ scan and reviewing a complete report can be expensive and noisy,
especially in time‑boxed workshops or when stakeholders only care about specific domains
(e.g. identity and networking).

### What Option 6 Adds
Option 6 introduces an **intent‑aware routing layer** that allows Copilot SDK to:
- Interpret natural language intent (e.g. “focus on identity and networking risks”)
- Select a subset of control packs / evaluators to run
- Execute a targeted assessment instead of a full scan

The deterministic engine is reused; only the **scope selection** changes.

### Core Components

1. **Pack Manifest**
   - Declarative mapping of ALZ domains to evaluator/control packs
   - Example domains: identity, networking, management groups, policy, logging

2. **Intent Router**
   - Deterministic function that maps user intent text to one or more domains
   - Returns the corresponding pack identifiers from the manifest

3. **Targeted Assessment Tool**
   - Copilot SDK tool (e.g. `run_targeted_assessment`)
   - Uses the intent router to select scope
   - Invokes the existing assessment runtime with selected packs only

4. **Copilot SDK Session**
   - Exposes the targeted assessment tool
   - Allows multi‑turn refinement (e.g. “add management groups too”)

### Acceptance Criteria

- Natural language requests result in different assessment scopes
- Only selected packs are executed (not “run everything”)
- Scoring and evidence outputs are identical to full runs for the same packs
- No scoring logic or control definitions are modified
- Outputs are written only to the local output directory

---

## Option 5 — Continuous ALZ Posture (CI/CD‑Driven Deltas)

### Problem Addressed
ALZ assessments are point‑in‑time snapshots that drift quickly. Without an automated
loop, regressions and improvements are hard to track, and “what changed and why it
matters” is difficult to explain consistently.

### What Option 5 Adds
Option 5 turns the orchestrator into a **repeatable posture pipeline** by adding:
- Scheduled or on‑demand assessment runs
- Persistent storage of assessment artifacts
- Copilot‑generated summaries of posture deltas between runs

### Core Components

1. **GitHub Actions Workflow**
   - Runs on a schedule (e.g. nightly/weekly) and on manual trigger
   - Executes the ALZ assessment in a safe environment or lab tenant
   - Uploads artifacts (run JSON, reports, output folder)

2. **Delta Comparison Step**
   - Compares the latest run with a previous baseline
   - Identifies regressions, improvements, and unchanged areas

3. **Copilot SDK Delta Summary**
   - Reads deterministic delta data
   - Produces a human‑readable summary:
     - What changed
     - Why it matters
     - Top regressions to investigate
     - Recommended next actions

4. **Optional Publishing**
   - Summary may be:
     - Stored as a markdown artifact
     - Posted to GitHub Issues or Discussions
   - Posting is optional and can be added later

### Acceptance Criteria

- Workflow produces repeatable assessment artifacts
- A delta summary is generated from deterministic data
- Copilot does not invent or alter assessment results
- Summaries are reproducible from the same inputs
- No write access outside the repository/artifact context

---

## Relationship Between Options 5 and 6

- **Option 6** improves *how* assessments are run (intent‑based scoping)
- **Option 5** improves *when and how often* assessments are run (continuous posture)

Option 6 is typically implemented first, as it:
- Reuses the existing CLI/runtime
- Requires no CI/CD or secrets initially
- Provides immediate workshop value

Option 5 builds on the same primitives to enable continuous monitoring.

---

## Definition of “Done”

### Option 6 is complete when:
- Targeted assessments can be run via natural language
- Different intents produce different scopes
- Outputs are deterministic and auditable

### Option 5 is complete when:
- Assessments run on a schedule or on demand
- Artifacts from multiple runs are retained
- Copilot produces a clear delta summary between runs

---

## Out of Scope (Explicitly Deferred)

- Automated remediation
- Environment mutation
- New collectors or evaluators
- Scoring rule changes
- MCP server integrations (may be layered later)