# docs/ — Program Documentation

Layout (per-case-study chains from day one; human decision 2026-07-06, DECISION_LOG #4):

- `docs/` — the Working Backwards document chain for this case study, defined by `00.wb_checklist.csv`.
- `docs/` root — program-wide artifacts only: `DECISION_LOG.md` (canonical decision log), `agents-reference/` (vendored role docs), this README.

## Canonical Reading Order (per case-study chain)

| Order | File | Purpose |
|---:|---|---|
| 0 | `00.wb_checklist.csv` | Canonical document map, stage, owner, and source inputs. |
| 1 | `01.idea.md` | One-page idea pitch. |
| 2 | `02.PR_FAQ.md` | Working Backwards PR/FAQ. |
| 3 | `03.PRD.md` | Consolidated product requirements. |
| 4 | `03.UID.md` | Consolidated UI details. |
| 5 | `04.TRD.md` | Consolidated technical requirements. |
| 6 | `05.DETAILED_DESIGN.md` | Consolidated data/software design and agentic BI seams. |
| 7 | `06.PROGRAM_PLAN.md` | Delivery plan and critical path. |
| 8 | `07.ORR.md` | Operational readiness review. |
| 9 | `08.Launch.md` | Launch/go-no-go document. |
| 10 | `09.COE_TEMPLATE.md` | Correction of Error template. |
| 11 | `10.METRIC_DICTIONARY.csv` | Certified governed metric dictionary. |
| 12 | `11.HUMAN_SIGNOFF.md` | Human approval gate. |
| 13 | `12.Marketing.md` | Marketing requirements and claims guardrails. |
| 14 | `13.QA_MERGE_GATES.md` | QA merge-gate policy: what blocks a merge vs warns (Step 5 loop). |

## Consolidation Note

The older source/supporting files were consolidated into the canonical chain and
removed from this folder. Use `00.wb_checklist.csv` as the document map and the
canonical files above as the current program answer.

## Architecture Rule

The project's central trust boundary is:

`MetricFlow/dbt = quantitative truth`

`RAG over customer support tickets and feedback = qualitative evidence`

`LLM/agent = routing, planning, and synthesis inside enforced boundaries`

No document in this folder should imply that RAG executes analytics or that the
LLM generates warehouse SQL.
