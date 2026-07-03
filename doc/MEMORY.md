# MEMORY — BTG Doc Reorganization Plan

## Goal
Reorganize `doc/` (45 files) to follow metis/aiNarada numbering convention: merge into ~22 numbered files with Working Backwards chain at low numbers, reference/support docs at mid numbers, phase/ops docs at high numbers.

## Constraints
- **No content deletion** — only merge into fewer files with section headers. Template/placeholder files (`[TO BE COMPLETED]`) are concatenated as-is.
- **Preserve git history** — use `git mv` or `mv` so git tracks renames.
- **No cross-reference updates needed** outside `doc/README.md` — root-level `.md` files (`1_stack_setup_mac.md` through `5_cicd.md`) do not reference `doc/` files.

## Merge Map

| Merge Sources | Destination |
|---|---|
| `0.product.md` + `1.CONTEXT.md` | `01.idea.md` |
| `6.PRD_CONCISE.md` + `8.PRD_DETAILED.md` | `4.PRD.md` |
| `10.TRD_CONCISE.md` + `11.TRD_DETAILED.md` | `6.TRD.md` |
| `17.PHASE0_APP_SCAFFOLD.md` + `18.PHASE0_ANALYTICS_FOUNDATION.md` + `19.PHASE0_DATA_PLATFORM.md` | `15.PHASE0.md` |
| `20.PHASE1_M1_CSV_INGESTION_SPEC.md` + `21.PHASE1_M2_GOVERNED_FACT_AND_METRICS_SPEC.md` + `22.PHASE1_M3_REPORT_ASSEMBLY_AND_RETRIEVAL_SPEC.md` + `23.PHASE1_M4_OPERABILITY_PROOF_SPEC.md` + `35.WP1_IMPLEMENTATION_HANDOFF.md` + `36.WP1_UID_PARITY_CHECKLIST.md` | `16.PHASE1.md` |
| `37.WP2_DATABASE_OPERATIONS_DESIGN.md` + `38.WP2A_IMPLEMENTATION_HANDOFF.md` + `39.WP2B_DURABILITY_HANDOFF.md` + `40.WP2_QA_GATE_REPORT.md` + `41.WP2_SRE_BACKUP_READINESS.md` + `42.WP2C_READINESS_HANDOFF.md` | `17.PHASE2.md` |
| `13.DATA_ARCHITECTURE.md` + `14.SOFTWARE_ARCHITECTURE.md` | `7.DETAILED_DESIGN.md` |
| `15.DATA_IMPLEMENTATION_PLAN.md` + `16.SOFTWARE_IMPLEMENTATION_PLAN.md` | `20.IMPLEMENTATION_PLANS.md` |
| `25.CS_Runbook.md` + `28.CS.md` | `19.CUSTOMER_SUPPORT.md` |
| `34.WP0_WP4_QA_STRATEGY.md` + `32.FREEZE_BASELINE.md` + `33.BASELINE_TO_TARGET_TRACE_MATRIX.md` | `18.QA_AND_BASELINES.md` |
| `29.NEXT_STEPS.md` + `31.PROJECT_MANAGEMENT.html` | `21.NEXT_STEPS.md` |

## Standalone Files (keep as-is)
- `2.TOOLSTACK.md`
- `3.METRIC_DICTIONARY.md`
- `4.SYNTHETIC_DEFAULT_DATA.csv`
- `5.PR_FAQ.md`
- `7.DESIGN_MOCK.html`
- `9.UID.md`
- `12.PROGRAM_PLAN.md`
- `24.PHASE1_ACCEPTANCE_AND_HANDOFF_CHECKLIST.md`
- `26.Launch.md`
- `27.Marketing.md`
- `30.HUMAN_SIGNOFF.md`
- `43.AI_ARCHITECT_NL_TO_METRIC_SELECTOR.md` (if present)

## Key Decisions
- Numbering follows metis convention: WB chain (PR_FAQ, PRD, UID, TRD) at low numbers, metric dictionary/synthetic data at mid numbers, phase/implementation/ops docs at higher numbers, plus `MEMORY.md` (unnumbered).
- `a`/`b` suffixes are not used; concise + detailed are merged into one file with section headers.
- Postgres is the only intended data store (per `2.TOOLSTACK.md`) — no JSON artifact fallback.
- ~60% of source files are templates (`[TO BE COMPLETED]`) — the merge is structural, not content-rich.

## Execution Steps
1. Read source files → create merged destination → `git rm` originals
2. Update `doc/README.md` with new numbering table and descriptions
3. Create `MEMORY.md` (this file)
4. Verify final file count (~22) and content integrity
5. Stage (`git add doc/`) and commit

## Current State (as of 2026-07-03)
Plan is designed and approved by user. No file operations executed yet. The 45 original files are intact in this directory.
