# Copilot Enterprise Workshop Orchestrator

### Deterministic Azure Landing Zone Governance — Multi-Turn, Tool-Restricted, Enterprise Guardrailed

This project implements a GitHub Copilot SDK–powered **enterprise workshop orchestrator** over a deterministic Azure Landing Zone (ALZ) governance engine.

> **Copilot does not score controls.**
> **Copilot does not mutate the environment.**

Copilot acts as a multi-turn orchestration layer, selecting from explicit, guardrailed tools that execute deterministic governance logic and return structured, traceable evidence.

---

## What Makes This Enterprise-Grade

- **One-way data flow:** deterministic → AI
- **Tool-restricted execution surface**
- **No scoring modification**
- **No environment mutation**
- **No file writes outside `out/`**
- **Structured output validation**
- **Microsoft Learn grounding via MCP**

> **This is not a chatbot.**
>
> It is a controlled governance orchestration layer over live Azure telemetry.

---

## Deterministic Reasoning Foundation

The underlying assessment engine performs structured, multi-stage reasoning over live Azure telemetry:

1. Deterministic control evaluation
2. Dependency graph impact analysis
3. Initiative ordering based on structural constraints
4. Causal "why-risk" chain construction
5. Microsoft Learn–grounded remediation guidance

**The AI does not score. It reasons over scored evidence.**

### What the Engine Produces

- Scores every control in the [Azure Landing Zone Review Checklist](https://github.com/Azure/review-checklists) against live Azure telemetry
- Builds a dependency-ordered 30-60-90 transformation roadmap
- Performs causal "why-risk" analysis across domains
- Grounds remediation in official Microsoft Learn documentation

---

## Built for Cloud Solution Architects

Designed for CSA-led enterprise engagements, this system replaces slideware and checklist interviews with deterministic telemetry analysis.

**Run one command → enter a Copilot-facilitated workshop session over scored governance evidence.**

> [!IMPORTANT]
> 🔍 **Open the interactive demo report:**
> 👉 **[View the HTML assessment report](https://htmlpreview.github.io/?https://github.com/rebmid/Reasoning-Agent-Azure-Landing-Zone-Assessment-Advisor/blob/main/docs/demo/Contoso-ALZ-Platform-Readiness-Report-Sample.html)**
>
> Generated from a real Azure Test/Lab "Contoso" tenant using read-only access.

---
## 📸 Demo Walkthrough

### 1️⃣ Platform Snapshot

Deterministic maturity scoring across ALZ design areas with automation coverage and enterprise readiness scoring.

![Platform Snapshot](docs/demo/report-hero.png)

---

### 2️⃣ Enterprise Readiness Blockers

Foundation gaps that prevent enterprise-scale adoption — derived from failed controls and dependency graph impact.

![Enterprise Readiness Blockers](docs/demo/01_enterprise-readiness-blockers.png)

---

### 3️⃣ Top Business Risks

Deterministically ranked business risks with root cause and score drivers.

![Top Business Risks](docs/demo/02_top-business-risks.png)

---

### 4️⃣ 30-60-90 Transformation Roadmap

Dependency-ordered remediation initiatives with maturity trajectory projections.

![Roadmap Traceability](docs/demo/03_roadmap-traceability.png)

---

### 5️⃣ Design Area Breakdown

ALZ design area maturity breakdown with automation %, critical failures, and control status distribution.

![Design Area Breakdown](docs/demo/04_design_area_breakdown.png)

---

### 6️⃣ Workshop Decision Funnel

CSA decision framing — blockers → risks → remediation path.

![Workshop Decision Funnel](docs/demo/04_workshop_decision_funnel.png)

---

### 7️⃣ CSA Workbook – 30-60-90 Plan

Customer-ready Excel roadmap aligned to checklist IDs and owners.

![Excel 30-60-90 Roadmap](docs/demo/05_excel_30_60_90_roadmap.png)

---

### 8️⃣ CSA Workbook – Executive Summary

Executive framing with top risks, maturity metrics, and engagement summary.

![Excel Executive Summary](docs/demo/05_excel_executive_summary.png)

---

### 9️⃣ Full Checklist Control Details

Control-level scoring mapped directly to Azure Review Checklist IDs.

![Excel Control Details](docs/demo/05_excel_landing_zone_checklist_control_details.png)

---

### 🔎 Execution Context

Assessment scope, subscriptions evaluated, and API access confirmation.

![Execution Context](docs/demo/00a_execution-context.png)

## Architectural Characteristics

| Principle | Implementation |
|------------|----------------|
| **Deterministic First** | All scoring, risk tiers, and control verdicts are computed from live Azure signals before AI executes |
| **Checklist-Grounded** | Every remediation item maps to an official Azure Review Checklist ID — no synthetic identifiers |
| **One-Way Data Flow** | AI consumes scored results but cannot modify deterministic outputs |
| **Schema-Enforced Output** | All AI responses are validated against JSON schemas before acceptance |
| **Documentation-Grounded** | Microsoft Learn MCP integration enriches outputs with official implementation guidance |
| **Traceable Deliverables** | CSA Workbook, HTML Report, and Run JSON preserve referential integrity end-to-end |


---

## End-to-End Reasoning Architecture

> **Architecture Principle — One-Way Data Flow**
>
> Deterministic assessment **feeds** the AI reasoning layer. Control verdicts and risk scores are final before AI executes.

```
Azure Tenant / Demo
        │
        ▼
Deterministic ALZ Assessment
(Resource Graph + Policy + Defender)
        │
        ▼
Control Scoring Engine
        │
        │─────── one-way feed ──────┐
        │                           ▼
        ├────────► CSA Workbook    AI Reasoning Engine
        │                           │
        │                           ▼
        │                     MCP Grounding Layer
        │            (Microsoft Learn retrieval + patterns)
        │                           │
        │                           ▼
        │                         WHY Reasoning Layer
        │
        └───────────────────────────┘
                    │
                    ▼
          Traceable Deliverables
```

### Data Collection

- Azure Resource Graph
- Policy + Compliance
- Defender for Cloud
- Management Group hierarchy

### Evaluation Engine

- Signal Bus routes platform telemetry → control evaluators
- ALZ control pack scoring → Pass / Fail / Partial / Manual
- Weighted maturity + risk model

### AI Reasoning Engine

| Pass | Name | Output |
|------|------|--------|
| 1 | **Roadmap & Initiatives** | 30-60-90 plan + initiative dependency graph |
| 2 | **Executive Briefing** | Top risks + maturity narrative |
| 3 | **Implementation Decision** | ALZ implementation pattern selection per initiative |
| 4 | **Sequence Justification** | Initiative ordering rationale + engagement recommendations |
| 5 | **Enterprise-Scale Readiness** | Readiness assessment against ALZ design areas |
| 6 | **Smart Questions** | Targeted discovery questions for the customer |
| 7 | **Implementation Backlog** | Per-initiative execution plans |
| 8 | **Microsoft Learn Grounding** | MCP SDK retrieval + ALZ-aware contextualisation |
| 9 | **Target Architecture** | Recommended architecture with execution units |
| 10 | **Critical Issues** | Top failing controls advisory with course of action |
| 11 | **Blocker Resolution** | Enterprise readiness blocker resolution summary |

### Why-Risk Agent (Deterministic Reasoning Layer)

- Failing controls → dependency graph impact
- Root cause → cascade effect
- Roadmap action that fixes it
- Microsoft Learn remediation reference

## Prerequisites

| Requirement | Details |
|---|---|
| **Python** | 3.12 or later |
| **Azure CLI** | Installed and authenticated (`az login`) |
| **Azure Permissions** | Reader role (minimum) on target subscriptions. Management Group Reader for full hierarchy visibility. |
| **Azure OpenAI** | Required for AI features. Needs a `gpt-4.1` deployment (or any chat-completion model). Set env vars (see [Configuration](#configuration)). |
| **Git** | For cloning the repository |

### Required Azure Resource Providers

The tool queries Azure Resource Graph and ARM APIs using **read-only** calls. The following resource providers must be registered on the target subscriptions for all signals to return data. Most are registered by default on any subscription that has used the service — but if a signal returns empty, missing provider registration is the most common cause.

| Resource Provider | Signal(s) | Registered by Default? |
|---|---|---|
| `Microsoft.ResourceGraph` | All Resource Graph queries | ✅ Yes |
| `Microsoft.Network` | Firewalls, VNets, Public IPs, NSGs, Route Tables, Private Endpoints, DDoS | ✅ Yes |
| `Microsoft.Storage` | Storage Account Posture | ✅ Yes |
| `Microsoft.KeyVault` | Key Vault Posture | ✅ Yes |
| `Microsoft.Sql` | SQL Server Posture | Only if SQL is used |
| `Microsoft.Web` | App Service Posture | Only if App Service is used |
| `Microsoft.ContainerRegistry` | Container Registry Posture | Only if ACR is used |
| `Microsoft.ContainerService` | AKS Cluster Posture | Only if AKS is used |
| `Microsoft.RecoveryServices` | VM Backup Coverage | Only if Backup is configured |
| `Microsoft.Compute` | VM inventory (for backup coverage) | ✅ Yes |
| `Microsoft.Security` | Defender plans, Secure Score | ✅ Yes |
| `Microsoft.Authorization` | RBAC hygiene, Resource Locks, Policy assignments | ✅ Yes (built-in) |
| `Microsoft.PolicyInsights` | Policy compliance summary | ✅ Yes |
| `Microsoft.Management` | Management Group hierarchy | ✅ Yes |
| `Microsoft.Insights` | Diagnostics coverage | ✅ Yes |

To check registration status:

```bash
az provider show -n Microsoft.RecoveryServices --query "registrationState" -o tsv
```

To register a missing provider (requires Contributor or Owner):

```bash
az provider register -n Microsoft.RecoveryServices
```

> **Note:** If a resource type doesn't exist in the subscription (e.g., no AKS clusters), the evaluator returns **NotApplicable** — not an error. Missing provider registration only matters when you *have* those resources but the signal returns empty.

---

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/rebmid/Reasoning-Agent-Azure-Landing-Zone-Assessment-Advisor.git
cd Reasoning-Agent-Azure-Landing-Zone-Assessment-Advisor
```

### 2. Create a virtual environment

**Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file in the project root (this file is git-ignored):

```env
AZURE_OPENAI_ENDPOINT=https://<your-resource>.openai.azure.com/
AZURE_OPENAI_KEY=<your-api-key>
```

The tool expects a **`gpt-4.1`** deployment (or any chat-completion model) on the Azure OpenAI resource. See [Configuration](#configuration) for details.

> **Without these credentials**, the assessment still runs — all deterministic scoring, control evaluation, and data collection work normally. However, the 11-pass AI reasoning pipeline will be skipped (`⚠ AI skipped`), meaning these report sections will be empty:
> - 30-60-90 Transformation Roadmap
> - Executive Briefing & Top Business Risks
> - Enterprise-Scale Readiness & Blockers
> - Critical Issues & Course of Action
> - Workshop Decision Funnel smart questions
> - Microsoft Learn MCP grounding
>
> Use `--no-ai` to explicitly skip AI, or omit the `.env` file to skip silently.

### 5. Authenticate with Azure

```bash
az login
```

If you have multiple tenants, target the correct one:

```bash
az login --tenant <tenant-id>
```

### 6. Run the assessment

```bash
python scan.py
```

That's it. The tool will:

1. Discover your Azure execution context (tenant, subscriptions, identity)
2. Fetch the latest ALZ checklist from GitHub (~243 controls)
3. Run all evaluators against your environment
4. Score every control with weighted domain scoring
5. Run the 11-pass AI reasoning pipeline (requires `.env` — see step 4)
6. Ground recommendations in Microsoft Learn documentation via MCP
7. Output all artifacts to the `out/` directory

---

## Configuration

### Environment Variables

| Variable | Required | Description |
|---|---|---|
| `AZURE_OPENAI_ENDPOINT` | For AI features | Your Azure OpenAI resource endpoint URL (e.g. `https://myresource.openai.azure.com/`) |
| `AZURE_OPENAI_KEY` | For AI features | API key for the Azure OpenAI resource |
| `GITHUB_TOKEN` | For Copilot Workshop | Personal access token — alternatively, authenticate via `gh auth login` |

All variables can be set in a `.env` file in the project root (loaded automatically via `python-dotenv`) or as system environment variables.

### Azure OpenAI Model

The tool defaults to the **`gpt-4.1`** deployment name. To use a different model, modify the `AOAIClient` initialization in `ai/engine/aoai_client.py`.

### API Version

Default: `2024-02-15-preview`. Configurable in `AOAIClient.__init__()`.

## CLI Reference

```
python scan.py                 # Standard assessment
python scan.py --tenant-wide   # Cross-subscription enterprise scan
```

| Flag | Description |
|---|---|
| `--pretty` | Pretty-print the final JSON to stdout after the run |
| `--preflight` | Run preflight access probes and exit — validates permissions without a full assessment |
| `--why DOMAIN` | Explain **why** a domain is the top risk — runs causal reasoning over an existing assessment |
| `--demo` | Use the bundled demo fixture (`demo/demo_run.json`) instead of live Azure data — no Azure connection required |
| `--no-ai` | Skip AI reasoning passes (useful for testing or environments without Azure OpenAI) |
| `--no-html` | Skip HTML report generation |
| `--on-demand INTENT` | Run a targeted evaluation via `IntentOrchestrator` (e.g. `enterprise_readiness`) — output saved to `out/run-*-on-demand.json` |
| `--workshop-copilot` | Enter the interactive Copilot SDK workshop session (see below) |

---

## Copilot Workshop Session

The workshop session provides an interactive, multi-turn Copilot experience with 4 guardrailed tools for running assessments, exploring findings, and generating reports.

### Demo Mode (no Azure connection required)

```bash
python scan.py --workshop-copilot --demo
```

Uses the bundled demo fixture (`demo/demo_run.json`) — no Azure credentials or Azure OpenAI needed. The demo fixture includes pre-computed AI output, so report sections like the roadmap and executive briefing are populated. Great for testing, demos, and learning the workflow.

> **Note:** Demo mode loads a static fixture. It does **not** run evaluators, the AI pipeline, or MCP grounding. To get fresh AI-enriched output, use live mode with `.env` configured.

### Live Mode (real Azure environment)

```bash
python scan.py --workshop-copilot
```

Runs against your authenticated Azure subscription. The live scan takes 5–10 minutes depending on environment size. If `.env` is configured with Azure OpenAI credentials, the full 11-pass AI reasoning pipeline runs — otherwise AI is skipped and only deterministic scoring is produced.

### Prerequisites

- **GitHub token** — either set `GITHUB_TOKEN` env var or authenticate via `gh auth login`
- **Azure CLI** (live mode only) — `az login` and confirm the correct subscription with `az account show`
- **Azure OpenAI** (live mode, for AI features) — `.env` file with `AZURE_OPENAI_ENDPOINT` and `AZURE_OPENAI_KEY` (see [Configuration](#configuration))

### Debug Mode

To see all SDK events during a session (useful for troubleshooting):

```powershell
$env:WORKSHOP_DEBUG = "1"
python scan.py --workshop-copilot --demo
```

### Workshop Tools

Once inside the session, you can ask the Copilot to use any of these tools:

| Tool | Description | Example Prompt |
|---|---|---|
| `run_scan` | Execute a deterministic ALZ assessment scan | *"run a scan"* |
| `load_results` | Load a completed run into memory | *"load the latest results"* |
| `summarize_findings` | Filter findings by design area, severity, or failure status | *"show critical Security findings"* |
| `generate_outputs` | Produce HTML report or Excel workbook | *"generate an HTML report"* |

### Typical Workshop Flow

1. **"run a scan"** — executes the assessment (instant in demo, 5–10 min live)
2. **"load results"** — loads the run into the session
3. **"summarize findings"** — explore findings by design area or severity
4. **"generate an HTML report"** — produce the customer-facing deliverable

---

## Output Artifacts

All outputs are written to the `out/` directory:

| File | Description |
|---|---|
| `run-YYYYMMDD-HHMM.json` | Complete assessment data — controls, scores, AI output, delta, execution context |
| `report.html` | Interactive executive HTML report with score breakdowns and gap analysis |
| `run-YYYYMMDD-HHMM_CSA_Workbook.xlsm` | 3-sheet CSA deliverable workbook — macro-enabled (see [CSA Workbook Deep Dive](#csa-workbook-deep-dive)) |
| `target_architecture.json` | Target architecture recommendation — derived from scored controls and checklist alignment, with component recommendations and Learn references |
| `preflight.json` | *(preflight mode only)* Access probe results |

Additionally, `assessment.json` is written to the project root as a convenience copy.

---

## How It Works

### 1. Data Collection

The **collectors** module queries Azure APIs via Resource Graph, Defender, Policy, and Management Group endpoints to gather raw infrastructure data:

- **Resource Graph** — VNets, firewalls, public IPs, NSGs, route tables, storage accounts, Key Vaults, private endpoints, diagnostic settings, and more
- **Defender** — security score, coverage tier, recommendations
- **Policy** — policy definitions, assignments, and compliance state
- **Management Groups** — full hierarchy tree

All queries use `AzureCliCredential` — the same identity you authenticated with via `az login`.

### 2. Evaluation & Scoring

The **Signal Bus** architecture routes collected data through registered evaluators:

1. The ALZ checklist is fetched live from GitHub (~243 controls across Security, Networking, Governance, Identity, Platform, and Management domains)
2. Each control is matched to an evaluator (or marked `Manual` if no automated check exists)
3. Evaluators emit `Pass`, `Fail`, `Partial`, or `Info` verdicts with evidence
4. The **scoring engine** applies domain weights and severity multipliers to produce a composite risk score
5. **Automation coverage** is calculated — typically 20-30% of controls have automated evidence, with the rest requiring customer conversation

### 3. AI Reasoning Engine

The AI layer is a **consumer** of the deterministic scoring output — it receives the scored controls, risk tiers, and evidence via `build_advisor_payload()` and produces advisory content. It never modifies or feeds back into deterministic verdicts.

When AI is enabled, a **multi-stage reasoning pipeline** runs against Azure OpenAI:

| Pass | Prompt | Output | max_tokens |
|---|---|---|---|
| 1 | `roadmap.txt` | 30-60-90 transformation roadmap + named initiatives | 8000 |
| 2 | `exec.txt` | Executive briefing with business risk narrative | 8000 |
| 3 | `implementation_decision.txt` | ALZ implementation pattern selection per initiative | 8000 |
| 4 | `sequence_justification.txt` | Initiative ordering rationale + engagement recommendations | 8000 |
| 5 | `readiness.txt` | Enterprise-scale landing zone technical readiness | 8000 |
| 6 | `smart_questions.txt` | Customer discovery questions per domain | 8000 |
| 7 | `implementation.txt` × N | Implementation backlog (one item per initiative) | 4000 |
| 8 | *(MCP grounding)* | Learn doc refs, code samples, full-page enrichment | — |
| 9 | `target_architecture.txt` | Target architecture + `grounding.txt` enrichment | 8000 |
| 10 | `critical_issues.txt` | Top failing controls advisory with course of action | 8000 |
| 11 | `blocker_resolution.txt` | Enterprise readiness blocker resolution summary | 8000 |

The `AOAIClient` includes built-in resilience:
- **JSON fence stripping** — removes markdown ````json```` wrappers from model output
- **Truncation repair** — closes dangling brackets and strings when output is cut off
- **Retry loop** — up to 2 retries on invalid JSON responses

### 4. Grounding via Microsoft Learn MCP

The tool uses the **official MCP Python SDK** (Streamable HTTP transport) to connect to Microsoft's documentation API at `https://learn.microsoft.com/api/mcp`:

| MCP Tool | Purpose |
|---|---|
| `microsoft_docs_search` | Retrieves curated 500-token content chunks for each initiative |
| `microsoft_code_sample_search` | Fetches Bicep/Terraform code samples for infrastructure recommendations |
| `microsoft_docs_fetch` | Downloads full documentation pages as markdown for deep grounding |

If MCP is unreachable, a **fallback** uses the public Learn search REST API (`https://learn.microsoft.com/api/search`) to provide title + URL + description.

Grounding runs for:
- Each initiative in the transformation roadmap
- Each identified gap
- The target architecture

### 5. Report Generation

**HTML Report** (`report.html`):
- **Platform Readiness Snapshot** — tenant maturity score, automation coverage, enterprise-scale landing zone technical readiness
- **Landing Zone Adoption Blockers** — AI-identified barriers to ALZ adoption
- **Platform Risk Prioritization** — 5-tier risk classification (Critical → Hygiene) with confidence indicators
- **Highest-Impact Remediation Sequence** — prioritised initiative roadmap
- **Maturity After Roadmap Execution** — projected score improvement
- **Capability Unlock View** — capabilities enabled by completing each initiative
- **Domain Deep Dive** — per-section control tables split into ALZ Core and Operational Overlay, with automation %, critical fail counts, and risk sorting
- **Assessment Scope & Confidence** — subscription coverage, signal availability, and data-collection provenance
- **Customer Validation Required** — controls needing manual review or customer conversation
- **ALZ Design Area References** — links to official ALZ design area documentation
- **Data Collection Provenance** — collector execution metadata and timestamps

**CSA Workbook** (`CSA_Workbook_v1.xlsm`):
- See [CSA Workbook Deep Dive](#csa-workbook-deep-dive) below

---

## CSA Workbook Deep Dive

The workbook is the primary **customer-facing deliverable** — a 3-sheet Excel file ready for CSA engagements:

### Sheet 0: `0_Executive_Summary`

| Section | Content |
|---|---|
| **CSA Engagement Framing** | Engagement Objective, Key Message, Customer Outcome — ready-made talking points |
| **Assessment Metrics** | Total controls, automated %, pass/fail/partial counts, risk score |
| **Top Business Risks** | AI-identified risks with severity, affected domain, and recommended mitigation |

### Sheet 1: `1_30-60-90_Roadmap`

A phased transformation plan where each action item includes:

- **Phase** (30 / 60 / 90 day)
- **Action** and **Checklist ID** (canonical ALZ checklist ID, e.g. `A01.01`)
- **CAF Discipline** alignment
- **Owner** and **Success Criteria**
- **Dependencies**
- **Related Controls** — mapped from `checklist_id` → item controls (GUIDs) → checklist IDs
- **Related Risks** — reverse-mapped through `top_business_risks[].affected_controls`

### Sheet 2: `2_Control_Details`

All ~243 controls in a flat table with 19 columns:

| Column | Description |
|---|---|
| A: Control ID | Checklist GUID (shortened) |
| B: Section | ALZ domain (Security, Networking, …) |
| C: Severity | Critical / High / Medium / Low |
| D: Status | Pass / Fail / Partial / Manual |
| E: Text | Original checklist text |
| F: Notes | Evidence notes from evaluator |
| G: Evidence Count | Number of evidence items |
| H: Learn URL | Microsoft Learn documentation link |
| I: Training URL | Microsoft training link |
| J: Checklist Name | Control name from ALZ checklist |
| K: Checklist Description | Full description from ALZ checklist |
| L: WAF Pillar | Well-Architected Framework alignment |
| M: Grounded Summary | AI-enriched summary with Learn references |
| N: Grounded URL | Learn documentation URL from MCP |
| O: Grounded Code | Bicep/Terraform code sample from MCP |
| P: Grounded Fetch | Full-page markdown excerpt |
| Q: Related Items | Checklist IDs of related remediation items |
| R: Category | ALZ category |
| S: Discussion Points | Customer discovery items mapped by control (224/243 populated) |

---

## Why-Risk Reasoning (`--why`)

After a full assessment, drill into **why** a specific domain was flagged as the top risk:

```bash
python scan.py --why Networking --demo
```

This runs a **6-step causal reasoning pipeline** over the existing assessment data:

| Step | What it does |
|---|---|
| 1. **Find risk** | Matches the domain to a top business risk from the executive summary |
| 2. **Failing controls** | Extracts every Fail/Partial control tied to the risk |
| 3. **Dependency impact** | Queries the knowledge graph for downstream controls blocked by failures |
| 4. **Roadmap initiatives** | Finds transformation plan actions that address the affected controls |
| 5. **Learn grounding** | Attaches Microsoft Learn references to each initiative via MCP |
| 6. **AI causal explanation** | Sends the assembled evidence to the reasoning model for root-cause analysis |

The AI output includes:
- **Root cause** — why the domain is the top risk (current-state framing)
- **Business impact** — specific consequences tied to the evidence
- **Fix sequence** — ordered remediation steps with dependency rationale and Learn URLs
- **Cascade effect** — which downstream controls will automatically improve

Output is saved to `out/why-{domain}.json`. Use `--no-ai` to get the raw evidence payload without the AI narration.

---

## Preflight Mode

Before running a full assessment, validate your Azure permissions:

```bash
python scan.py --preflight
```

Preflight probes check:
- Subscription visibility
- Resource Graph query access
- Management group read access
- Defender API access
- Policy read access

Results are saved to `out/preflight.json` and printed to the console with pass/fail indicators.

---

## Scoring Model

### Domain Weights

| Domain | Weight | Rationale |
|---|---|---|
| Security | 1.5× | Highest impact on breach risk |
| Networking | 1.4× | Network segmentation is foundational |
| Identity | 1.4× | Identity is the new perimeter |
| Governance | 1.3× | Policy enforcement and compliance |
| Platform | 1.2× | Landing zone structural integrity |
| Management | 1.1× | Operational visibility |

### Severity Weights

| Severity | Points |
|---|---|
| Critical | 6 |
| High | 5 |
| Medium | 3 |
| Low | 1 |
| Info | 0 |

### Status Multipliers

| Status | Multiplier | Meaning |
|---|---|---|
| Fail | 1.0× | Full risk weight applied |
| Partial | 0.6× | Reduced weight — some mitigation in place |
| Pass | 0× | No risk contribution |
| Manual | 0× | Not scored — requires customer discussion |

**Composite risk score** = Σ (severity_weight × status_multiplier × domain_weight) for all controls

---

## Troubleshooting

| Problem | Solution |
|---|---|
| `AZURE_OPENAI_KEY / AZURE_OPENAI_ENDPOINT not set` | Create a `.env` file with your Azure OpenAI credentials (see [Quick Start step 4](#4-configure-environment-variables)), or run with `--no-ai` to skip AI |
| Report sections are empty (roadmap, executive briefing, critical issues) | AI credentials are not configured. Create a `.env` file — without it, the 11-pass AI pipeline is silently skipped |
| `No subscriptions found` | Ensure `az login` succeeded and your identity has Reader on at least one subscription |
| `Management group hierarchy not visible` | Your identity needs Management Group Reader — the tool still works, but MG-related controls will be `Manual` |
| `Unterminated string` / JSON parse errors in AI output | The tool auto-repairs truncated JSON. If it persists, check your Azure OpenAI quota and model deployment name (`gpt-4.1`) |
| `MCP connection failed` | The tool falls back to the public Learn search API automatically. No action needed. |
| `ModuleNotFoundError` | Ensure your virtual environment is activated and `pip install -r requirements.txt` completed successfully |
| `az: command not found` | Install the [Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli) |
| Slow execution | Large tenants take longer. Use `--tenant-wide` only when needed. AI passes add ~60-90s. |
| Workshop session: `GITHUB_TOKEN` errors | Set `GITHUB_TOKEN` env var with a personal access token, or run `gh auth login` |

## Built with AI Assistance

This project was developed using GitHub Copilot as an AI pair programmer for code generation, refactoring, and test scaffolding.  
All architecture, control logic, Azure integration, and reasoning workflows were designed and implemented by the author.

## License

Copyright (c) 2026 Rebekah Midkiff