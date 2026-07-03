# doc/ — Program Doc Chain

This folder follows the Metis/aiNarada numbering convention. Lower numbers are
the Working-Backwards chain (idea → PR/FAQ → PRD → UID → TRD). Mid numbers are
reference/architecture docs. Higher numbers are phase specs and operations docs.

Merged from 45 source files into ~22 files per `MEMORY.md`. No content was
deleted — only concatenated with section headers preserving source attribution.

| # | Doc | Status | Likely owner |
|---|---|---|---|
| 01 | `idea.md` | **Done** | Project grounding — merged from `0.product.md` + `1.CONTEXT.md` |
| 02 | `TOOLSTACK.md` | **Done** | Project grounding doc |
| 03 | `METRIC_DICTIONARY.md` | Template | `data-architect-databricks` |
| 04 | `SYNTHETIC_DEFAULT_DATA.csv` | Template | `data-architect-databricks` / `senior-data-engineer-databricks` |
| 05 | `PR_FAQ.md` | **Done** | `pm-agent-amazon` |
| 06 | `PRD.md` | **Done** | `pm-agent-amazon` — merged from `6.PRD_CONCISE.md` + `8.PRD_DETAILED.md` |
| 07 | `DESIGN_MOCK.html` | Template | `design-agent-apple` |
| 08 | `UID.md` | Template | `design-agent-apple` |
| 09 | `TRD.md` | **Done** | `solutions-architect-amazon` — merged from `10.TRD_CONCISE.md` + `11.TRD_DETAILED.md` |
| 10 | `PROGRAM_PLAN.md` | Template | `tpm-agent-amazon` |
| 11 | `DETAILED_DESIGN.md` | **Done** | `data-architect-databricks` / `software-architect-amazon` — merged from `13.DATA_ARCHITECTURE.md` + `14.SOFTWARE_ARCHITECTURE.md` |
| 12 | `PHASE0.md` | Template | Build roles, phase-scoped — merged from `17`/`18`/`19` |
| 13 | `PHASE1.md` | Template | Build roles, phase-scoped — merged from `20`/`21`/`22`/`23`/`35`/`36` |
| 14 | `PHASE2.md` | Template | Build roles, phase-scoped — merged from `37`/`38`/`39`/`40`/`41`/`42` |
| 15 | `QA_AND_BASELINES.md` | Template | `qa-automation-gitlab` — merged from `34`/`32`/`33` |
| 16 | `CUSTOMER_SUPPORT.md` | Template | `forward-deployed-engineer-palantir` — merged from `25`/`28` |
| 17 | `IMPLEMENTATION_PLANS.md` | Template | Build roles — merged from `15`/`16` |
| 18 | `PHASE1_ACCEPTANCE_AND_HANDOFF_CHECKLIST.md` | Template | `qa-automation-gitlab` |
| 19 | `Launch.md` | Template | `sre-infrastructure-amazon` |
| 20 | `Marketing.md` | Template | `marketing-ops-manager-google` |
| 21 | `NEXT_STEPS.md` | Template | `tpm-agent-amazon` — merged from `29`/`31` |
| 22 | `HUMAN_SIGNOFF.md` | Template | `tpm-agent-amazon` |
| — | `MEMORY.md` | **Done** | TPM context handoff — unnumbered, not part of the doc chain |

## Fill-in order

Follow the TPM runbook's two-stage gate for every doc, in dependency order:
PM docs (01, 5) → PRD (4) → UID (7) → TRD (8) → Design (10) → Phase specs
(11-13) → Support/Launch/Marketing (15, 18-19) → program bookkeeping (9, 20-21)
as each build phase actually happens. Don't fill a template ahead of the program
reaching that stage.
