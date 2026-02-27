
Workshop Mode
Purpose
Workshop Mode is a guided, facilitator‑oriented execution mode designed for interactive workshops, demos, and architectural reviews. It layers explanation, comparison, and narrative guidance on top of the existing deterministic engine without changing the core evaluation logic.
This document reflects all Workshop Mode features added in the current branch, including run persistence, comparison, drift analysis, and assistant‑style facilitation.


Design Principles
Workshop Mode is intentionally:

Deterministic – the engine remains stateless; no hidden memory or AI‑side persistence
Explainable – every statement is grounded in run artifacts
Low risk – no mutation of customer environments, no privileged actions
Incremental – added as a new entry point alongside existing CLI flows


Core Concepts
Runs
A run is a single execution of the assessment pipeline:

Scope → collectors → evaluators → reports
Output materialized as structured artifacts (JSON, reports)
Each run is self‑contained. Workshop Mode does not assume implicit history; it operates only on runs that exist on disk .


Run Persistence (New)
Workshop Mode introduces a lightweight run persistence convention to enable comparison and replay.
Recommended Layout
out/
  runs/
    <timestamp>/
      run.json


Key characteristics:

Every scan produces a named, timestamped run directory
No database or service dependency
Compatible with real runs and demo JSONs copied into the same structure
This is a convention, not a refactor. The deterministic engine remains unchanged .


Active Run & Caching (New)
Workshop Mode maintains a single active run per session:

active_run_id
active_results (loaded once, cached in memory)
Behavior:

run_scan(...) → creates a new run and immediately activates it
load_results('latest') → resolves the most recent run on disk and activates it
All summarization and explanation tools default to the active run unless overridden
This avoids repeated file reads while keeping behavior explicit and deterministic .


Comparing Runs (New)
compare_runs
Workshop Mode supports deterministic comparison between two runs.
Capabilities:

Select two runs explicitly or default to latest vs previous
Compute deltas across evaluated domains
Surface additions, removals, regressions, and improvements
Comparison logic is activated only when two run artifacts are available. There is no implicit “previous run” concept beyond what exists on disk .


Delta / Continuous Posture
The comparison feature enables continuous posture analysis:

Baseline vs hardened configuration
Before / after remediation
Demo drift using seeded historical runs
The delta logic is already present in the engine; Workshop Mode exposes it as a first‑class workshop capability .


Drift Analysis (New)
Workshop Mode exposes drift analysis as a structured capability.

Identifies where posture has changed between runs
Distinguishes configuration drift from signal noise
Designed for narrative explanation, not automated remediation
This leverages existing engine components without altering scoring or evaluation semantics .


Why‑Reasoning (New)
Workshop Mode includes why‑reasoning to support facilitator‑led discussion.
Purpose:

Explain why a domain is flagged
Trace findings back to concrete evidence
Avoid speculative or unsupported claims
Why‑reasoning never invents data; it operates strictly over run results and known evaluation logic .


Demo & Historical Runs (New)
Workshop Mode explicitly supports demo and historical runs.
Patterns:

Demo JSONs may be copied into out/runs/
Optional separation using a --run-source flag (e.g., demo/ vs out/)
Same agent behavior regardless of run source
This allows predictable storytelling while preserving real‑world behavior.


Tool Surface (Workshop Assistant)
Workshop Mode constrains the assistant to a small, explicit tool set:
Recommended MVP tools:

run_scan(scope) → execute a scan
load_results(run_id | 'latest') → activate an existing run
summarize_findings(run_id, filters) → structured summaries
compare_runs(run_a, run_b) → delta analysis
generate_outputs(run_id, formats) → reports (HTML, XLSX)
Each tool:

Accepts typed inputs
Returns structured data
Enforces safety constraints
No new business logic is introduced at the tool layer .


Guardrails & Safety (New)
Workshop Mode enforces strict guardrails:

Read‑only with respect to customer environments
File writes restricted to controlled output directories
No tools capable of mutating infrastructure
Assistant positioned as a facilitator, not an operator
These constraints are explicit and intentional to minimize risk during live workshops .


Typical Workshop Flow

Baseline RunExecute initial scan
Activate run
DiscussionSummarize findings
Explain why domains are flagged
Change or ScenarioConfiguration change or demo pivot
Follow‑up RunExecute second scan
Compare against baseline
Delta ReviewDiscuss drift, improvements, and regressions


Non‑Goals
Workshop Mode explicitly does not:

Add AI memory or hidden state
Introduce databases or services
Refactor the deterministic engine
Automate remediation
These are deliberate exclusions to preserve trust, explainability, and auditability .


Summary
The current branch elevates Workshop Mode from a simple execution wrapper into a first‑class facilitation experience:

Persistent, replayable runs
Deterministic comparison and drift analysis
Why‑reasoning for explanation
Guardrailed assistant interaction
All new capabilities are additive, low‑risk, and grounded in existing engine behavior.
