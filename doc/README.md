# doc/ — Program Doc Chain

This folder follows the Metis/aiNarada numbering convention. Lower numbers are
the Working-Backwards chain (idea → PR/FAQ → PRD → UID → TRD). Mid numbers are
reference/architecture docs. Higher numbers are phase specs and operations docs.

Merged from 45 source files into ~22 files per `MEMORY.md`. No content was
deleted — only concatenated with section headers preserving source attribution.

| # | Doc | Status | Likely owner | Bedrock component |
|---|---|---|---|---|
| 01 | `idea.md` | **Done** | Project grounding | — |
| 02 | `TOOLSTACK.md` | **Done** | Project grounding | — |
| 03 | `METRIC_DICTIONARY.md` | Template | `data-architect-databricks` | Bedrock Knowledge Base (semantic search over metric definitions) |
| 04 | `SYNTHETIC_DEFAULT_DATA.csv` | Template | `data-architect-databricks` / `senior-data-engineer-databricks` | S3 data source → Bedrock Knowledge Base ingestion |
| 4a | `WBR_Agent_AWS_Bedrock.md` | **Done** | Deployment reference | Full stack: Bedrock LLM, Knowledge Base, RDS pgvector, App Runner, S3+CloudFront |
| 05 | `PR_FAQ.md` | **Done** | `pm-agent-amazon` | Prompt engineering (product constraint on LLM behavior) |
| 06 | `PRD.md` | **Done** | `pm-agent-amazon` | Prompt engineering (product requirements constrain prompts) |
| 07 | `DESIGN_MOCK.html` | Template | `design-agent-apple` | Frontend hosting on S3 + CloudFront |
| 08 | `UID.md` | Template | `design-agent-apple` | Frontend UI layer |
| 09 | `TRD.md` | **Done** | `solutions-architect-amazon` | Knowledge Base, Guardrails, Prompt Engineering |
| 10 | `PROGRAM_PLAN.md` | Template | `tpm-agent-amazon` | — |
| 11 | `DETAILED_DESIGN.md` | **Done** | `data-architect-databricks` / `software-architect-amazon` | Guardrails (tool enforcement, hallucination detection) |
| 12 | `PHASE0.md` | Template | Build roles, phase-scoped | App Runner (backend containerization), RDS (data layer) |
| 13 | `PHASE1.md` | Template | Build roles, phase-scoped | Bedrock LLM integration, Knowledge Base setup |
| 14 | `PHASE2.md` | Template | Build roles, phase-scoped | Guardrails, RDS operations, SRE backup |
| 15 | `QA_AND_BASELINES.md` | Template | `qa-automation-gitlab` | Guardrails (eval suite, baselines, CI gates) |
| 16 | `CUSTOMER_SUPPORT.md` | Template | `forward-deployed-engineer-palantir` | — |
| 17 | `IMPLEMENTATION_PLANS.md` | Template | Build roles | — |
| 18 | `PHASE1_ACCEPTANCE_AND_HANDOFF_CHECKLIST.md` | Template | `qa-automation-gitlab` | Guardrails (acceptance gates) |
| 19 | `Launch.md` | Template | `sre-infrastructure-amazon` | Guardrails (production readiness gate) |
| 20 | `Marketing.md` | Template | `marketing-ops-manager-google` | — |
| 21 | `NEXT_STEPS.md` | Template | `tpm-agent-amazon` | — |
| 22 | `HUMAN_SIGNOFF.md` | Template | `tpm-agent-amazon` | — |
| — | `MEMORY.md` | **Done** | TPM context handoff | — |

## Bedrock Component Legend

| Component | Covers |
|---|---|
| **Bedrock LLM** | Model selection, inference, BYOK, provider-agnostic design |
| **Knowledge Base** | RAG pipeline, S3 data source, embedding, chunking, ingestion, semantic search |
| **Guardrails** | Prompt injection, hallucination detection, adversarial review, accuracy eval, CI gates |
| **Prompt Engineering** | System prompt design, output schema, few-shot examples, catalog embedding |
| **App Runner** | Backend container hosting, auto-scaling, environment config |
| **RDS** | PostgreSQL + pgvector for structured metrics and embedding storage |
| **S3 + CloudFront** | Static frontend hosting, data source for Knowledge Base ingestion |

## Fill-in order

Follow the TPM runbook's two-stage gate for every doc, in dependency order:
PM docs (01, 5) → PRD (4) → UID (7) → TRD (8) → Design (10) → Phase specs
(11-13) → Support/Launch/Marketing (15, 18-19) → program bookkeeping (9, 20-21)
as each build phase actually happens. Don't fill a template ahead of the program
reaching that stage.
