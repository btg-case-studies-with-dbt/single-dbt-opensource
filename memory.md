# Governed Metric Execution Architecture for Agentic BI — Project Chart

## Face Sheet

- Product: Governed Metric Execution Architecture for Agentic BI (local case study).
- Workspace: `/Users/kanjasaha/Documents/btg-case-studies-with-dbt/single-dbt-opensource`.
- Stack: Postgres, Airflow, dbt Core, MetricFlow, Docker Compose.
- Canonical docs: 14 named docs in `docs/` (01.idea.md–12.Marketing.md + DECISION_LOG.md), 16-row checklist at `docs/00.wb_checklist.csv`.

## Alerts

- Stay inside this project's workspace unless loading explicitly required agent instructions.
- `conversational-bi/` query path is committed (Waves 1+2) but NOT verified green — no eval run yet (promptfoo not installed; backend/provider not up).
- `git` writes via the device bridge leave stale `.git/*.lock` files it cannot unlink, blocking the next op. Run git from the Mac terminal, not device_bash.

## Open Problems

- Retriever (`evidence_retriever.py`) uses a hardcoded 3-ticket fixture, not a governed dbt seed. Governed-seed→retriever wiring is unbuilt (was C1's purpose; C1 deferred).
- Retrieval-quality eval (Wave 2 open item) not started — owner: ai-architect.

## Decisions

- 2026-07-08: `docs/docs/` (stale prior-product doc chain) deleted. No content loss — prior product unrelated to current project.
- 2026-07-09: Wave2 C1 (governed evidence seed + staging model) removed/deferred (revert `f31b75e`). Trigger was a "dbt build failed" report that proved to be operator error (wrong CWD), not a defect. Reversible via `git revert f31b75e`. Files parked in `_to_delete/`.

## Progress Notes

### 2026-07-09 - tpm-agent-amazon @ cli

**Situation:** Waves 1+2 of the conversational-BI build committed to the submodule; the query path the prior note called "not implemented" now exists in git, not just on disk.

**Background:** ~1,500 lines landed as aa3235e (C1 evidence source), 2615ac4 (C2: LiteLLM gateway, LlamaIndex retriever, LangGraph, synthesis contract+prompt, OTEL), e1200a6 (C3 guardrails), b6f79b4 (C4 eval harness). C1 then reverted (f31b75e) after a false "dbt build failed" report (wrong CWD; project root is `dbt/`). Recurring `index.lock` traced to device-bridge git leaving un-unlinkable locks.

**Assessment:** Five-category response contract (TR12) is code-complete and committed (C2) but asserted-not-green — no eval or dbt build evidence captured. Retriever runs on fixtures, bypassing the governed seed, so the single-source-of-truth wiring is still open. Verification is blocked on local runtime (Postgres, Ollama/BYOK, promptfoo), none of which run in the workspace.

**Recommendation:** (1) Clear stale locks + `rm -rf _to_delete/`. (2) From `dbt/`, run `dbt build`; via `npx promptfoo@latest`, run the eval with backend up — move C4/TR12 from asserted to verified. (3) Route retrieval-quality eval to ai-architect. (4) Decide: restore governed evidence seed (revert f31b75e) or keep retriever on fixtures — a data-governance call.
