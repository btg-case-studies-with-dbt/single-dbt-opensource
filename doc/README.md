# doc/ — Program Doc Chain

This folder follows the Metis/aiNarada numbering convention. Docs `1`, `2`, `5`, `6`, `8`, `10`, `11`, `13` are **done and approved** for this program (Governed Cross-Domain Conversational BI). Everything else is a **blank template**, stripped of Metis's content, waiting to be filled in as this program actually reaches that stage.

Owner mapping below is inferred from filename/purpose and this repo's `.claude/tpm-agent-amazon/registry.md` — confirm against the registry at the time each doc is actually routed, don't take this table as the routing decision itself.

| # | Doc | Status | Likely owner (role-agent skill) |
|---|---|---|---|
| 0 | `product.md` | Template | `pm-agent-amazon` (pre-PR/FAQ product one-pager, optional) |
| 1 | `CONTEXT.md` | **Done** | Project grounding doc |
| 2 | `TOOLSTACK.md` | **Done** | Project grounding doc |
| 3 | `METRIC_DICTIONARY.md` | Template | `data-architect-databricks` — note: this program's metric dictionary is already certified inside `13.DATA_ARCHITECTURE.md`; only split it out here if that grows unwieldy |
| 4 | `SYNTHETIC_DEFAULT_DATA.csv` | Template | `data-architect-databricks` / `senior-data-engineer-databricks` (sample fixture) |
| 5 | `PR_FAQ.md` | **Done** | `pm-agent-amazon` |
| 6 | `PRD_CONCISE.md` | **Done** | `pm-agent-amazon` |
| 7 | `DESIGN_MOCK.html` | Template (stub) | `design-agent-apple` — build fresh from this program's own UID, not adapted from any source mockup |
| 8 | `PRD_DETAILED.md` | **Done** | `pm-agent-amazon` |
| 9 | `UID.md` | Template | `design-agent-apple` |
| 10 | `TRD_CONCISE.md` | **Done** | `solutions-architect-amazon` |
| 11 | `TRD_DETAILED.md` | **Done** | `solutions-architect-amazon` |
| 12 | `PROGRAM_PLAN.md` | Template | `tpm-agent-amazon` |
| 13 | `DATA_ARCHITECTURE.md` | **Done** | `data-architect-databricks` |
| 14 | `SOFTWARE_ARCHITECTURE.md` | Template | `software-architect-amazon` |
| 15 | `DATA_IMPLEMENTATION_PLAN.md` | Template | `analytics-engineer-dbt` / `senior-data-engineer-databricks` |
| 16 | `SOFTWARE_IMPLEMENTATION_PLAN.md` | Template | `senior-software-engineer-amazon` |
| 17-19 | `PHASE0_*` specs | Template | `senior-software-engineer-amazon` / `senior-data-engineer-databricks` / `analytics-engineer-dbt`, phase-scoped |
| 20-23 | `PHASE1_M1-M4_*` specs | Template | Same build roles, milestone-scoped |
| 24 | `PHASE1_ACCEPTANCE_AND_HANDOFF_CHECKLIST.md` | Template | `qa-automation-gitlab` |
| 25 | `CS_Runbook.md` | Template | `forward-deployed-engineer-palantir` |
| 26 | `Launch.md` | Template | `sre-infrastructure-amazon` (launch readiness gate) |
| 27 | `Marketing.md` | Template | `marketing-ops-manager-google` |
| 28 | `CS.md` | Template | `forward-deployed-engineer-palantir` |
| 29 | `NEXT_STEPS.md` | Template | `tpm-agent-amazon` |
| 30 | `HUMAN_SIGNOFF.md` | Template | `tpm-agent-amazon` (decision log of human approvals) |
| 31 | `PROJECT_MANAGEMENT.html` | Template (stub) | `tpm-agent-amazon` — rebuild fresh, don't adapt the source mockup |
| 32 | `FREEZE_BASELINE.md` | Template | `tpm-agent-amazon` (milestone freeze checkpoint) |
| 33 | `BASELINE_TO_TARGET_TRACE_MATRIX.md` | Template | `tpm-agent-amazon` / `solutions-architect-amazon` |
| 34 | `WP0_WP4_QA_STRATEGY.md` | Template | `qa-automation-gitlab` |
| 35-42 | `WP*_*` handoffs/gates | Template | Mix of `senior-software-engineer-amazon`, `senior-data-engineer-databricks`, `dba-oracle`, `sre-infrastructure-amazon`, `qa-automation-gitlab` depending on the work package — confirm per file when reached |
| 43 | `AI_ARCHITECT_NL_TO_METRIC_SELECTOR.md` | New slot (routed) | `ai-architect` — TR4 ambiguity decision rule and the false-rejection-rate eval mechanism, per `10.TRD_CONCISE.md`'s open escalation to AI Architect. No prior slot existed for this artifact type; assigned by TPM per the existing-slot test. |

## Fill-in order

Follow the TPM runbook's two-stage gate (TPM verification, then human approval) for every doc, in dependency order: PM docs (0, 5, 6, 8) → Solutions Architect (10, 11) → Data Architect (3, 4, 13) as the one-way door → Software Architect (14) and Design Agent (7, 9) in parallel → implementation plans (15, 16) → phase specs (17-24) → CS/Launch/Marketing (25-28) → program bookkeeping (12, 29-33) → work-package handoffs (34-42) as each build phase actually happens.

Don't fill a template ahead of the program actually reaching that stage — per the TPM runbook's scope-to-the-increment rule, a blank slot here is a tracked seam, not a prompt to pre-build.
