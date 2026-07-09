# Governed Metric Execution Architecture for Agentic BI — Project Chart

## Face Sheet

- Product: Governed Metric Execution Architecture for Agentic BI (local case study).
- Workspace: `/Users/kanjasaha/Documents/btg-case-studies-with-dbt/single-dbt-opensource`.
- Stack: Postgres, Airflow, dbt Core, MetricFlow, Docker Compose.
- Canonical docs: 14 named docs in `docs/` (01.idea.md–12.Marketing.md + DECISION_LOG.md), 16-row checklist at `docs/00.wb_checklist.csv`.

## Alerts

- Stay inside this project's workspace unless loading explicitly required agent instructions.
- `conversational-bi/` FastAPI app does not exist in code — documented as prototype but not yet implemented.

## Open Problems

- (none yet)

## Progress Notes

### 2026-07-08 - tpm-agent-amazon @ cli

**Situation:** Existing dbt medallion project with 52 governed MetricFlow metrics (3 domains: Revenue, Token usage, Quota). Doc chain consolidated and populated. No conversational query path implemented yet.

**Background:** Existing code at commit 9dd8c28 — dbt models, Airflow DAGs, seeds, semantic models. Scaffold initialized (AGENTS.md, CLAUDE.md, memory.md, .claude/skills/). 14 canonical docs filled with real content.

**Assessment:** Project is past the doc-writing phase and at the first implementation increment. The five-category response contract (TRD TR12) is the gating item that must ship before eval, domain tagging, and health-check workstreams can complete.

**Recommendation:** Commit scaffold + doc state (Milestone 0), then route five-category response contract implementation to senior-software-engineer-amazon.
