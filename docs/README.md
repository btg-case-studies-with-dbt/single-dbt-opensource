# docs/ — Program Documentation

Layout (per-case-study chains from day one; original decision in `8.DECISION_LOG.md` #4, current structure approved 2026-07-15):

- `docs/` — the numbered Working Backwards chain defined by `0.checklist.csv`.
- `docs/contracts/` — governed metric and data/API contracts.
- `docs/design/` — product-specific design artifacts.
- `docs/guardrails/` — the aiTechne toolstack and refreshed engineering rules.
- `docs/test_artifacts/` — acceptance policies, test plans, and durable test evidence.
- `docs/work_records/` — supporting analyses and non-canonical delivery records.
- `docs/tpm-reference/` — refreshed TPM runbook and role registry.

## Canonical Reading Order (per case-study chain)

| Order | File | Purpose |
|---:|---|---|
| 0 | `0.checklist.csv` | Canonical document map, stage, owner, and source inputs. |
| 1 | `1.idea.md` | One-page idea pitch. |
| 2 | `2.PR_FAQ.md` | Working Backwards PR/FAQ. |
| 3 | `3.PRD.md` | Consolidated product requirements. |
| 4 | `4.UID.md` | Consolidated UI details. |
| 5 | `5.TRD.md` | Consolidated technical requirements. |
| 6 | `6.DETAILED_DESIGN.md` | Consolidated data/software design and agentic BI seams. |
| 7 | `7.PROGRAM_PLAN.md` | Delivery plan and critical path. |
| 8 | `8.DECISION_LOG.md` | Authoritative decision record. |
| 9 | `9.ORR.md` | Operational readiness review. |
| 10 | `10.PRELAUNCH_SECURITY_CHECKLIST.md` | Reserved template slot; not yet authored in this project. |
| 11 | `11.Launch.md` | Launch/go-no-go document. |
| 12 | `12.HUMAN_SIGNOFF.md` | Human approval gate. |
| 13 | `13.COE_TEMPLATE.md` | Correction of Error template. |

## Supporting Artifacts

| File | Purpose |
|---|---|
| `contracts/1.METRIC_DICTIONARY.csv` | Certified governed metric dictionary. |
| `guardrails/1.TOOLSTACK.md` | Approved aiTechne technology stack; dbt is explicitly allowed. |
| `guardrails/2.ENGINEERING_RULES.md` | Refreshed family engineering rules. |
| `test_artifacts/7.QA_MERGE_GATES.md` | Merge-blocking QA policy and reviewer runbook. |
| `work_records/1.MARKETING_REQUIREMENTS.md` | Marketing requirements and claims guardrails. |
| `work_records/2.BEDROCK_VS_OPENSOURCE.md` | Architecture option comparison. |
| `work_records/3.AGENTIC_BI_BRIEF.md` | Business-leader readiness guide. |
| `tpm-reference/TPM_RUNBOOK.md` | Refreshed TPM operating mechanism. |
| `tpm-reference/registry.md` | Refreshed role-routing registry. |

## Consolidation Note

The older source/supporting files were consolidated into the canonical chain and
removed from this folder. Use `0.checklist.csv` as the document map and the
canonical files above as the current program answer.

## Architecture Rule

The project's central trust boundary is:

`MetricFlow/dbt = quantitative truth`

`RAG over customer support tickets and feedback = qualitative evidence`

`LLM/agent = routing, planning, and synthesis inside enforced boundaries`

No document in this folder should imply that RAG executes analytics or that the
LLM generates warehouse SQL.
