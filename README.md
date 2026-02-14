# Azure Landing Zone Assessor (`lz-assessor`)

A comprehensive, automated Azure Landing Zone assessment tool designed for **Cloud Solution Architects (CSAs)** conducting customer engagements. It evaluates an Azure tenant against Microsoft's [Azure Landing Zone (ALZ) checklist](https://github.com/Azure/review-checklists), scores controls deterministically, then enriches the results with AI-generated advisory output — producing a ready-to-deliver **CSA workbook**, **executive HTML report**, and **target architecture** in a single command.

## Why This Matters
Enterprise customers struggle to understand whether their Azure environment & existing landing zone is truly ready for enterprise-scale operations. This provides a reliable way to assess the maturity and enterprise-scale readiness of their Azure landing zone and identify the gaps that block transformation.

This reasoning agent:
- Uses **read-only RBAC** (safe for customer tenants)
- Evaluates **real Azure telemetry**
- Selects controls based on **user intent**
- Produces a **defensible 30-60-90 roadmap**

The output is a **CSA-ready workbook**, not just an assessment.

---

## Demo Screenshots

| Reasoning Engine | Control Evaluation |
|---|---|
| ![Reasoning Engine](docs/demo/01_reasoning-engine.png) | ![Control Evaluation](docs/demo/02_control-evaluation.png) |

| Roadmap Traceability | Executive Briefing |
|---|---|
| ![Roadmap Traceability](docs/demo/03_roadmap-traceability.png) | ![Executive Briefing](docs/demo/04_executive-briefing.png) |

---

## Table of Contents

- [Features](#features)
- [Architecture Overview](#architecture-overview)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [CLI Reference](#cli-reference)
- [Output Artifacts](#output-artifacts)
- [How It Works](#how-it-works)
  - [1. Data Collection](#1-data-collection)
  - [2. Evaluation & Scoring](#2-evaluation--scoring)
  - [3. AI Reasoning Engine](#3-ai-reasoning-engine)
  - [4. Grounding via Microsoft Learn MCP](#4-grounding-via-microsoft-learn-mcp)
  - [5. Report Generation](#5-report-generation)
- [CSA Workbook Deep Dive](#csa-workbook-deep-dive)
- [On-Demand Evaluation Mode](#on-demand-evaluation-mode)
- [Preflight Mode](#preflight-mode)
- [Scoring Model](#scoring-model)
- [Extending the Tool](#extending-the-tool)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## Features

| Capability | Description |
|---|---|
| **Live ALZ Checklist** | Always fetches the latest checklist from the `Azure/review-checklists` GitHub repo — never stale |
| **Automated Evaluators** | 20+ evaluators run Azure Resource Graph, Defender, Policy, and Management Group queries to score controls as Pass / Fail / Partial |
| **Weighted Scoring** | Domain-weighted risk scoring (Security 1.5×, Networking 1.4×, Identity 1.4×, Governance 1.3×, Platform 1.2×, Management 1.1×) with severity multipliers |
| **7-Pass AI Advisory Pipeline** | GPT-4.1 generates a transformation roadmap, executive briefing, enterprise-scale readiness assessment, smart questions, implementation backlog, target architecture, and grounded references |
| **Microsoft Learn MCP Grounding** | Official MCP SDK retrieves curated documentation, code samples, and full-page markdown from Microsoft Learn to ground all AI recommendations |
| **CSA Workbook (Excel)** | 3-sheet deliverable: Executive Summary with engagement framing, 30-60-90 Roadmap mapped to controls + risks, and a full Control Details sheet with 19 data columns including "Questions to Ask" |
| **Executive HTML Report** | Jinja2-rendered interactive report with score breakdowns, risk heatmaps, and gap tables |
| **Target Architecture** | AI-generated JSON artifact describing recommended architecture components, connected via grounding to Microsoft Learn references |
| **Delta Tracking** | Compares current run against previous runs to show control-level changes over time |
| **Preflight Probes** | Validates Azure access before a full run — catches permission gaps early |
| **On-Demand Intent Evaluation** | Workshop-style targeted assessments (e.g., `enterprise_readiness`) via an agent orchestrator |
| **Pluggable Provider Architecture** | Swap `AOAIReasoningProvider` for any model — Phi, mock, or custom — in one line |

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                          scan.py                                 │
│                   (Composition Root / CLI)                        │
└────────┬───────────────────┬──────────────────┬──────────────────┘
         │                   │                  │
    ┌────▼────┐      ┌──────▼──────┐    ┌──────▼──────┐
    │Collectors│      │  Evaluators  │    │  AI Engine   │
    │ (Azure)  │      │(Signal Bus)  │    │ (7 passes)   │
    └────┬────┘      └──────┬──────┘    └──────┬──────┘
         │                   │                  │
  Resource Graph      Control Packs      Azure OpenAI
  Defender            Scoring Engine     MCP Retriever
  Policy              Domain Weights     Prompt Templates
  Mgmt Groups         Delta Engine       Grounding (Learn)
         │                   │                  │
         └───────────┬───────┘──────────┬───────┘
                     │                  │
              ┌──────▼──────┐   ┌──────▼──────┐
              │  CSA Workbook│   │ HTML Report  │
              │  (Excel)     │   │ (Jinja2)     │
              └─────────────┘   └─────────────┘
```

---

## Project Structure

```
lz-assessor/
├── scan.py                      # Entry point — CLI, orchestration, output assembly
├── requirements.txt             # Python dependencies
├── .env                         # Environment variables (Azure OpenAI keys)
├── .gitignore                   # Excludes secrets, outputs, caches
│
├── docs/                        # Documentation assets
│   └── demo/                    #   Demo screenshots for README
│
├── alz/                         # ALZ checklist loader
│   └── loader.py                #   Fetches live from GitHub main branch
│
├── collectors/                  # Azure data collectors
│   ├── resource_graph.py        #   Resource Graph queries (VNets, firewalls, IPs, NSGs, …)
│   ├── defender.py              #   Microsoft Defender for Cloud status
│   ├── management_groups.py     #   Management group hierarchy
│   ├── policy.py                #   Azure Policy definitions
│   ├── policy_assignments.py    #   Policy assignment status
│   └── policy_compliance.py     #   Policy compliance data
│
├── signals/                     # Signal Bus architecture
│   ├── types.py                 #   EvalScope, Signal, EvalResult type definitions
│   ├── registry.py              #   SignalBus — routes signals to evaluators
│   ├── cache.py                 #   Signal caching layer
│   └── providers/               #   Signal data providers
│       ├── resource_graph.py    #     Resource Graph signal provider
│       ├── policy.py            #     Policy signal provider
│       ├── defender.py          #     Defender signal provider
│       ├── management_groups.py #     MG tree signal provider
│       └── diagnostics.py       #     Diagnostics signal provider
│
├── evaluators/                  # Control evaluators (auto-register on import)
│   ├── networking.py            #   Network controls (VNet, firewall, NSG, DDoS, …)
│   ├── governance.py            #   Governance controls (tags, naming, policy, …)
│   ├── security.py              #   Security controls (Defender, encryption, RBAC, …)
│   └── registry.py              #   Evaluator registration infrastructure
│
├── control_packs/               # Control pack definitions
│   ├── loader.py                #   Loads versioned control packs
│   └── alz/                     #   ALZ v1.0 control pack
│
├── engine/                      # Core assessment engine
│   ├── adapter.py               #   Bridges evaluators to scoring
│   ├── assessment_runtime.py    #   Deterministic assessment runner
│   ├── context.py               #   Azure execution context discovery
│   ├── scoring.py               #   Weighted scoring model + automation coverage
│   ├── delta.py                 #   Run-over-run delta computation
│   ├── rollup.py                #   Section-level result rollups
│   └── run_store.py             #   Persists/retrieves historical runs
│
├── graph/                       # Knowledge graph
│   ├── controls.json            #   Control → CAF discipline → dependency mappings
│   └── knowledge_graph.py       #   Graph query utilities
│
├── ai/                          # AI advisory module
│   ├── mcp_retriever.py         #   Microsoft Learn MCP SDK client (search, code, fetch)
│   ├── build_advisor_payload.py #   Prepares scoring data for AI consumption
│   ├── engine/
│   │   ├── aoai_client.py       #   Azure OpenAI JSON client (retry, repair, lint)
│   │   ├── reasoning_engine.py  #   7-pass AI pipeline orchestrator
│   │   └── reasoning_provider.py#   ReasoningProvider protocol + AOAI implementation
│   ├── prompts/                 #   Prompt templates (Jinja-style .txt files)
│   │   ├── system.txt           #     System persona
│   │   ├── roadmap.txt          #     30-60-90 roadmap + initiatives
│   │   ├── exec.txt             #     Executive briefing
│   │   ├── readiness.txt        #     Enterprise-scale readiness
│   │   ├── smart_questions.txt  #     Customer discovery questions
│   │   ├── implementation.txt   #     Implementation backlog items
│   │   ├── target_architecture.txt # Target architecture design
│   │   └── grounding.txt        #     MCP grounding enrichment
│   └── schemas/                 #   JSON schemas for AI output validation
│       └── domain.py            #     Domain model types
│
├── schemas/                     # Shared domain schemas
│   └── domain.py                #   Assessment domain types
│
├── agent/                       # Agent / workshop mode
│   ├── intent_orchestrator.py   #   Routes user intents to evaluators
│   ├── workshop.py              #   Workshop agent loop
│   └── session.py               #   Session state management
│
├── preflight/                   # Preflight access validation
│   └── analyzer.py              #   Probes Azure permissions before full run
│
├── reporting/                   # Output generation
│   ├── render.py                #   Jinja2 HTML report generator
│   ├── report_template.html     #   HTML template for executive report
│   └── csa_workbook.py          #   CSA workbook builder (3-sheet Excel)
│
└── out/                         # Output directory (git-ignored)
    ├── run-YYYYMMDD-HHMM.json   #   Raw assessment data
    ├── report.html               #   Executive HTML report
    ├── CSA_Workbook_v1.xlsx      #   CSA deliverable workbook
    └── target_architecture.json  #   AI-generated target architecture
```

---

## Prerequisites

| Requirement | Details |
|---|---|
| **Python** | 3.12 or later |
| **Azure CLI** | Installed and authenticated (`az login`) |
| **Azure Permissions** | Reader role (minimum) on target subscriptions. Management Group Reader for full hierarchy visibility. |
| **Azure OpenAI** | Required for AI features. Needs a `gpt-4.1` deployment (or any chat-completion model). Set env vars (see [Configuration](#configuration)). |
| **Git** | For cloning the repository |

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
2. Fetch the latest ALZ checklist from GitHub
3. Run all evaluators against your environment
4. Score every control with weighted domain scoring
5. Generate a 7-pass AI advisory pipeline (if OpenAI is configured)
6. Ground recommendations in Microsoft Learn documentation
7. Output all artifacts to the `out/` directory

---

## Configuration

### Environment Variables

| Variable | Required | Description |
|---|---|---|
| `AZURE_OPENAI_ENDPOINT` | For AI features | Your Azure OpenAI resource endpoint URL |
| `AZURE_OPENAI_KEY` | For AI features | API key for the Azure OpenAI resource |

### Azure OpenAI Model

The tool defaults to the `gpt-4.1` deployment. To use a different model, modify the `AOAIClient` initialization in `ai/engine/aoai_client.py`.

### API Version

Default: `2024-02-15-preview`. Configurable in `AOAIClient.__init__()`.

---

## CLI Reference

```
python scan.py [OPTIONS]
```

| Flag | Description |
|---|---|
| *(no flags)* | Full assessment: evaluate all controls + AI advisory + all reports |
| `--tenant-wide` | Scan all visible subscriptions across the tenant (default: Resource Graph subscriptions only) |
| `--pretty` | Pretty-print the final JSON to stdout after the run |
| `--preflight` | Run preflight access probes and exit — validates permissions without a full assessment |

### Examples

```bash
# Full assessment with AI
python scan.py

# Scan entire tenant
python scan.py --tenant-wide

# Check permissions first
python scan.py --preflight

# Full run, print JSON to console
python scan.py --pretty
```

---

## Output Artifacts

All outputs are written to the `out/` directory:

| File | Description |
|---|---|
| `run-YYYYMMDD-HHMM.json` | Complete assessment data — controls, scores, AI output, delta, execution context |
| `report.html` | Interactive executive HTML report with score breakdowns and gap analysis |
| `CSA_Workbook_v1.xlsx` | 3-sheet CSA deliverable workbook (see [CSA Workbook Deep Dive](#csa-workbook-deep-dive)) |
| `target_architecture.json` | AI-generated target architecture with component recommendations and Learn references |
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

When AI is enabled, a **7-pass pipeline** runs against Azure OpenAI:

| Pass | Prompt | Output | max_tokens |
|---|---|---|---|
| 1 | `roadmap.txt` | 30-60-90 transformation roadmap + named initiatives | 8000 |
| 2 | `exec.txt` | Executive briefing with business risk narrative | 4000 |
| 3 | `readiness.txt` | Enterprise-scale readiness assessment | 4000 |
| 4 | `smart_questions.txt` | Customer discovery questions per domain | 4000 |
| 5 | `implementation.txt` × N | Implementation backlog (one item per initiative) | 4000 |
| 6 | *(MCP grounding)* | Learn doc refs, code samples, full-page enrichment | — |
| 7 | `target_architecture.txt` | Target architecture + `grounding.txt` enrichment | 8000 |

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
- Executive summary with overall health score
- Domain score breakdown with visual indicators
- Risk heatmap
- Gap analysis table
- Delta changes from previous runs

**CSA Workbook** (`CSA_Workbook_v1.xlsx`):
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
- **Action** and **Initiative ID**
- **CAF Discipline** alignment
- **Owner** and **Success Criteria**
- **Dependencies**
- **Related Controls** — mapped from `initiative_id` → initiative controls (GUIDs) → checklist IDs
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
| Q: Related Initiatives | Initiative IDs related to this control |
| R: Category | ALZ category |
| S: Questions to Ask | Customer discovery questions mapped by control (224/243 populated) |

---

## On-Demand Evaluation Mode

For targeted workshop assessments, use `--on-demand`:

```bash
python scan.py --on-demand enterprise_readiness
```

This runs the **IntentOrchestrator** which:
1. Loads the ALZ control pack
2. Routes the intent to relevant evaluators
3. Runs the assessment runtime against the targeted scope
4. Optionally generates an AI explanation of the results
5. Saves output to `out/run-*-on-demand.json`

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
| `AZURE_OPENAI_KEY / AZURE_OPENAI_ENDPOINT not set` | Create a `.env` file with your Azure OpenAI credentials, or run with `--no-ai` |
| `No subscriptions found` | Ensure `az login` succeeded and your identity has Reader on at least one subscription |
| `Management group hierarchy not visible` | Your identity needs Management Group Reader — the tool still works, but MG-related controls will be `Manual` |
| `Unterminated string` / JSON parse errors in AI output | The tool auto-repairs truncated JSON. If it persists, check your Azure OpenAI quota and model deployment |
| `MCP connection failed` | The tool falls back to the public Learn search API automatically. No action needed. |
| `ModuleNotFoundError` | Ensure your virtual environment is activated and `pip install -r requirements.txt` completed successfully |
| `az: command not found` | Install the [Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli) |
| Slow execution | Large tenants take longer. Use `--tenant-wide` only when needed. AI passes add ~60-90s. |

---

## License

Copyright (c) 2026 Rebekah Midkiff