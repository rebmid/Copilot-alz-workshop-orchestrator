# Architecture

## Three-Layer Model

```
┌─────────────────────────────────────────────────┐
│  Layer 3 — AI Enrichment                        │
│  ai/engine/reasoning_engine.py, ai/prompts/     │
│  Consumes L1+L2 read-only. Produces advisory.   │
├─────────────────────────────────────────────────┤
│  Layer 2 — Checklist Mapping                    │
│  control_packs/, schemas/taxonomy.py,           │
│  engine/id_rewriter.py                          │
│  Canonical types, ID normalization, taxonomy.    │
├─────────────────────────────────────────────────┤
│  Layer 1 — Deterministic                        │
│  collectors/, signals/, evaluators/,            │
│  engine/scoring.py, engine/aggregation.py       │
│  Pure computation. No AI. No network calls.     │
└─────────────────────────────────────────────────┘
```

Dependencies flow **downward only**: Layer 3 → Layer 2 → Layer 1.
No upward imports. No exceptions.

---

## Layer 1 — Deterministic

**Modules**: `collectors/`, `signals/`, `evaluators/`, `engine/scoring.py`, `engine/aggregation.py`, `engine/rollup.py`, `engine/dependency_engine.py`, `engine/risk_scoring.py`, `engine/cost_simulation.py`, `engine/decision_impact.py`, `engine/maturity_trajectory.py`, `engine/scaling_rules.py`, `engine/drift_model.py`, `engine/transform_optimizer.py`

**Rules**:
- No AI imports. No prompt strings. No model calls.
- All status sets come from `schemas/taxonomy.py`.
- Evaluators return `Pass | Fail | Partial | NotAssessed` based solely on signal data.
- Scoring weights are defined in `DOMAIN_WEIGHTS` (taxonomy.py) and `STATUS_MULTIPLIER` (scoring.py). Both are frozen.

**What cannot change during stabilization**:
- Status multiplier values
- Domain weight values
- Evaluator verdict logic
- Section score formulas
- Gap score computations
- Signal→evaluator bindings

## Layer 2 — Checklist Mapping

**Modules**: `control_packs/`, `schemas/taxonomy.py`, `schemas/domain.py`, `engine/id_rewriter.py`, `alz/checklist_grounding.py`

**Rules**:
- No AI imports. No prompt strings. No model calls.
- Canonical ID format: `^[A-Z]\d{2}\.\d{2}$`
- All enum values (`ALZDesignArea`, `WAFPillar`, `ControlType`, `Severity`) are enforced at load time via `Literal` types.
- `ControlDefinition` is a frozen dataclass. No `dict[str, Any]` access patterns.

**What cannot change during stabilization**:
- Design area enum values (8 areas)
- WAF pillar enum values (5 pillars)
- Control type or severity enums
- `DESIGN_AREA_SECTION` mapping (slug → display name)
- Required control fields schema
- Checklist ID format

## Layer 3 — AI Enrichment

**Modules**: `ai/engine/reasoning_engine.py`, `ai/prompts/`, `ai/mcp_retriever.py`, `ai/build_advisor_payload.py`, `ai/schemas/`

**Rules**:
- May read Layer 1 and Layer 2 outputs. May not write to them.
- Calls into Layer 2 (`id_rewriter`, `checklist_grounding`) are post-processing guards applied to AI output — they do not modify Layer 1.
- All AI output goes into dedicated keys (see Merge Contract below).

**What AI output may NOT modify**:
- Control verdicts (`pass`/`fail`/`partial`/`not_assessed`)
- `risk_tier` values
- Maturity scores or section scores
- Checklist IDs after Layer 2 normalization
- Deterministic metadata (`signals`, `telemetry`, `scoring`)

---

## Control Pack Versioning

**Location**: `control_packs/<family>/<version>/`

**Current frozen pack**: `alz/v1.0` — 58 controls, 8 design areas.

**Version lock mechanism** (`control_packs/loader.py`):
1. SHA-256 checksum of `controls.json` is computed at load time.
2. Checked against `_FROZEN_CHECKSUMS` registry.
3. Mismatch raises `ControlPackVersionError` — assessment refuses to start.
4. Current checksum: `7fe4d340adb278f6`.

**To update a frozen pack**:
1. Create a new version directory: `control_packs/alz/v1.1/`
2. Copy and modify `controls.json`, `signals.json`, `manifest.json`.
3. Add the new checksum to `_FROZEN_CHECKSUMS`.
4. Never modify a frozen version's files in place.

**Taxonomy enforcement** (`engine/taxonomy_validator.py`):
- Every control is validated against `ControlDefinition` schema at load time.
- Missing or invalid fields → `TaxonomyViolation` → assessment refuses to start.
- No fallback logic. No silent defaults.

**ALZ checklist auto-fetch** (`alz/loader.py`):
- Fetches from `Azure/review-checklists` GitHub repo for AI prompt grounding only.
- Never touches `controls.json`, scoring, or evaluators.
- Schema-validated on fetch: requires `items`/`checklist` list with `category`, `subcategory`, `text`, `guid` fields.
- Format drift raises `ValueError` — fails fast, no silent degradation.

---

## Merge Contract

When AI completes (`scan.py`), output assembly follows this contract:

### Protected Keys (Layer 1 — immutable)

```
results
scoring
rollups
signal_availability
signal_execution_summary
scope_summary
meta
execution_context
```

These are deep-copied before AI merge and compared after. Any replacement or in-place mutation raises `RuntimeError`.

### AI-Owned Keys (Layer 3 — written by AI merge only)

```
ai
executive_summary
transformation_plan
transformation_roadmap
enterprise_scale_readiness
smart_questions
implementation_backlog
progress_analysis
target_architecture
critical_issues
blocker_resolution
```

### Isolation Guarantees

1. **Payload isolation**: AI receives `deepcopy(advisor_payload)`, not the original. Mutations in the AI pipeline cannot leak back to deterministic structures.
2. **Post-merge verification**: All 8 protected keys are deep-compared against their pre-merge snapshots. Equality check catches both replacement (`output["scoring"] = ...`) and nested mutation (`output["scoring"]["section_scores"][0]["score"] = ...`).
3. **Fail-fast**: Violation raises `RuntimeError` and halts the pipeline. No partial output is persisted.

---

## Stabilization Rules

The following are prohibited until stabilization ends:

- New evaluators
- New control types
- New AI passes (currently 12)
- New MCP endpoints
- Scoring weight changes
- Synthetic control injection
- Checklist scope expansion
- Schema changes to `assessment_run.schema.json` or `control_definition.schema.json`

Append-only additions to AI-owned keys are permitted. Reporting-layer changes that consume existing keys are permitted.

---

## Layer 4 — Copilot SDK Workshop

```
┌─────────────────────────────────────────────────────────┐
│  scan.py --workshop-copilot                             │
│        │                                                │
│        ▼                                                │
│  src/workshop_copilot.py                                │
│  ├─ CopilotClient → CopilotSession (gpt-4o)            │
│  ├─ 6 Tool() registrations (explicit JSON schemas)      │
│  ├─ Session cache: active_run_id / active_results       │
│  └─ REPL loop                                           │
│        │                                                │
│        ▼                                                │
│  src/workshop_tools.py                                  │
│  ├─ run_scan        → subprocess scan.py                │
│  ├─ load_results    → disk + memory cache               │
│  ├─ summarize_findings → deterministic filter           │
│  ├─ generate_outputs → HTML / Excel renderers           │
│  ├─ list_runs       → run store enumeration             │
│  ├─ compare_runs    → delta analysis (latest vs prev)   │
│  └─ ensure_out_path → path guardrail                    │
│        │                                                │
│        ▼                                                │
│  out/                                                   │
│  └─ All generated artefacts confined here                │
└─────────────────────────────────────────────────────────┘
```

**Rules**:
- Exactly 6 tools exposed. No extras.
- No data fabrication — all responses grounded in loaded run data.
- No environment mutation — read-only against Azure.
- File writes confined to `out/` via `ensure_out_path()`.
- Format allow-list: `html`, `excel` only.

