# Governed Metric Execution Architecture for Agentic BI — Project Chart

## Face Sheet

- Product: Governed Metric Execution Architecture for Agentic BI (local case study).
- Workspace: `/Users/kanjasaha/Documents/btg-case-studies-with-dbt/single-dbt-opensource`.
- Stack: Postgres, Airflow, dbt Core, MetricFlow, Docker Compose.
- Canonical docs: 14 named docs in `docs/` (01.idea.md–12.Marketing.md + DECISION_LOG.md), 16-row checklist at `docs/00.wb_checklist.csv`.

## Alerts

- Stay inside this project's workspace unless loading explicitly required agent instructions.
- `conversational-bi/` query path is committed (Waves 1+2) but NOT verified green — TR12 eval gate STILL not run. `/health` IS now green (Step 1, 2026-07-09); `/query` + eval still pending.
- Backend boot is now reproducible (Step 1): use **Python 3.11**, fresh venv, `pip install -r conversational-bi/requirements.txt`, then `cd conversational-bi && python -m uvicorn backend.main:app --port 8000`. Full recipe in `conversational-bi/README.md`. System 3.9 and Homebrew 3.14 both lack part of the stack — do not use them.
- The `/query` backend is NOT a docker-compose service. `docker compose up -d` starts Postgres/Airflow/Metabase/pgAdmin only. Start the API by hand per the recipe above, in its own terminal.
- Stray `.cbi-verify-venv/` may sit in repo root (leftover throwaway venv) — do NOT commit it; `rm -rf .cbi-verify-venv/`.
- `git` writes via the device bridge leave stale `.git/*.lock` files it cannot unlink, blocking the next op. Run git from the Mac terminal, not device_bash.

## Open Problems

- Retriever (`evidence_retriever.py`) uses a hardcoded 3-ticket fixture, not a governed dbt seed. Governed-seed→retriever wiring is unbuilt (was C1's purpose; C1 deferred).
- Retrieval-quality eval (Wave 2 open item) not started — owner: ai-architect.
- ✅ FIXED 2026-07-09 (Step 5, DECISION_LOG #8) — eval harness now asserts metric selection, not just category. Postprocess reduction dropped; metric assert real (promptfoo `value:` shape, fails on mismatch); domain assert removed; validated via `promptfoo validate`.
- **NEW blocker for Step 7 (owner: ai-architect, IN FLIGHT).** promptfoo 0.121.18 rejects the flat `eval/domain_questions.jsonl` at the test-loader (wants `vars:` wrapper or `.csv`). Fixture conversion routed to ai-architect; jsonl→csv (same columns) proven to validate. Blocks the Step 7 run until converted.
- **TRD TR12 wording flag (route to solutions-architect).** `docs/04.TRD.md` TR12 describes category routing; the enforced bar is metric selection. One-line reconciliation. Coverage of dimensions/time_range (group-by/filters) DEFERRED — scope-to-increment.

## Decisions

- 2026-07-08: `docs/docs/` (stale prior-product doc chain) deleted. No content loss — prior product unrelated to current project.
- 2026-07-09: Wave2 C1 (governed evidence seed + staging model) removed/deferred (revert `f31b75e`). Trigger was a "dbt build failed" report that proved to be operator error (wrong CWD), not a defect. Reversible via `git revert f31b75e`. Files parked in `_to_delete/`.
- 2026-07-09: Gold-layer constraint defect fixed + verified (`dbt build` green, ERROR=0). Root cause: `dim_region/dim_model/dim_customer` hand-rolled PKs via a `post_hook` drop+add; on `table` rebuild dbt renames the live table to `__dbt_backup` (PK + index travel with it), so the hook's `drop constraint` hit the backup whose PK the fact FKs still reference → Postgres refused. Broke every 2nd+ build; first build passed. Fix (analytics-engineer-dbt, Option b): removed PK post_hooks from the 3 dims + FK post_hooks from the 3 facts (kept rebuild-safe fact self-PKs). RI now enforced by existing dbt `relationships`/`unique`/`not_null` tests (green). Two-way-door governance trade: DB-enforced FKs → dbt-test-enforced RI. Reversible (restore post_hooks) but re-introduces the rebuild break. NOT yet committed.

## Next Actions (for next session)

Read this chart first. NOTE: `git` writes from THIS session worked cleanly with no stale locks (commit `3a67716`) — the old device-bridge lock warning did not bite; TPM can commit directly. The full query path WORKS end-to-end; the truthful TR12 baseline is **44% overall / 52% category / 4-of-6 metric (deepseek-v4-pro)**. The bottleneck is guardrails, not the model.

**Runtime bring-up (every session):** start Docker Desktop → `docker compose up -d postgres` → boot backend in venv from `conversational-bi/`: `DBT_HOST=localhost .venv/bin/python -m uvicorn backend.main:app --port 8000` (the gitignored `.env` supplies the provider: opencode/deepseek-v4-pro). `DBT_HOST=localhost` REQUIRED (mf reaches prod marts on localhost; in-container default stays `postgres`). To use ollama instead, set `LLM_PROVIDER=ollama OLLAMA_MODEL=llama3.1:8b` in the launch env.

- ✅ DONE this session: E2E query path, truthful harness, opencode/deepseek swap, catalog hygiene (69→44) — all committed at `3a67716`.

**Outstanding (priority order):**
1. **ROTATE the opencode key** (user) — it's in gitignored `.env` (unexposed in git) but was shown in a chat transcript. Replace the value in `conversational-bi/.env`.
2. **#1 GUARDRAIL/PROMPT work → ai-architect (THE lever).** deepseek is 6/6 on `answered` but 0/4 `ambiguous`, 0/2 `unsupported_domain`, and over-answers 9 `unknown_metric`/`ambiguous` rows — fabricates a metric instead of declining. Redesign prompt/guardrail to fire the rejection categories; measure via re-run. May need router-code changes (senior-software-engineer). Approved, not yet launched (held at user request).
3. **8-family semantic-layer gap → data-architect (confirm) then analytics-engineer (rebuild).** 8 canonical metric families are named in `docs/10` but only their RETIRED forms were ever built; catalog hygiene now correctly withholds the retired forms, so these families are absent from the served catalog. Needs a scoped dbt rename + `dbt parse`/regenerate — care given prior build-failure history.
4. **Parked 6-file dbt RI fix** (dim/fct models, still uncommitted & modified in tree): decide commit (accept dbt-test-enforced RI) vs restore post_hooks. The prod marts were built WITH this fix present.
5. **Ratify/revert** `dbt-postgres==1.10.2` pin in `conversational-bi/requirements.txt` (additive, needed for mf→postgres).
6. **`int_revenue_daily` column contract → data-architect:** `int_schema.yml` tests 4 columns the model doesn't produce → clean `dbt build --target prod` errors + cascade-SKIPs marts. Interim `--exclude` used; durable green needs yml/model reconciled.
7. **Governance:** restore governed evidence seed (`git revert f31b75e`) vs keep retriever fixtures — log the call.
8. **Retrieval-quality eval** (Wave 2) — ai-architect, not started. **TRD TR12 wording** reconciliation — solutions-architect (flagged).

## Progress Notes

### 2026-07-09/10 (marathon) - tpm-agent-amazon @ cli — query path made to WORK end-to-end; harness false-green caught

**Situation:** Drove Step 3 (TR12) to an actual scoring run. The "committed Waves 1+2" had NEVER run end-to-end, so each layer hid the next defect. Cleared a chain of them; the full `/query` path now returns real `answered` responses (first time in project history).

**Blockers found & fixed this session (each gate-1 verified, gate-2 approved where noted):**
1. Backend couldn't boot — no requirements.txt/venv/recipe. Fix: pinned `requirements.txt` (Py3.11) + `README.md` (senior-software-engineer). `/health` 200, catalog 69. DECISION_LOG #7.
2. Eval harness asserted category only — metric logic under wrong `postprocess`. Fixed (ai-architect). DECISION_LOG #8. Fixture `jsonl`→`csv` (promptfoo loader). 
3. `/query` 500 on every call — OTEL-disabled noop tracer was a function not an object (main.py). Fixed (senior-software-engineer).
4. `.env` never loaded — no `load_dotenv`. Added + pinned python-dotenv (senior-software-engineer). `.env` gitignored.
5. Data platform — Docker daemon had died mid-session; prod marts incomplete + prod target host `postgres` unreachable from host. analytics-engineer env-var'd the host (`DBT_HOST` default `postgres`, `localhost` on host, in-container unchanged) + full `dbt build --target prod` (PASS=519), `prod_mart_gold.fct_revenue_daily`=1820 rows. mf returns real rows from host.
6. `mf --where "metric_time between..."` = invalid MetricFlow syntax → system_error. Fixed to `--start-time/--end-time` flags; also rewrote `parse_mf_output` (mf emits space-aligned table, not CSV); added `time_override` interface (body field + `TIME_OVERRIDE` env, precedence body>env>clock) so eval can pin "now" into the data window (data spans 2025-10-20…2026-01-19). `/query` → `answered`, total_net_revenue=2.06982 (senior-software-engineer).

**THE BIG CATCH — harness false-green:** first full eval reported 25/25 PASS = 100%. VERIFIED it was vacuous: results JSON showed `reason:"No assertions"`, 0 componentResults on every row. Root cause: `assert:` at config ROOT — promptfoo only applies assertions under `defaultTest.assert` for externally-loaded (CSV) tests. Fixed (ai-architect): moved assert block → now discriminates (25/25 rows carry 2 assertions). TRUE ollama baseline: **category 52% (13/25)**; metric floored at 0 — but that's a FIXTURE GROUND-TRUTH bug, not the model: `expected_metric` used friendly names (`revenue`, `total_tokens`, `prompt_tokens`, `quota_utilization_pct`) that don't exist in the 69-metric catalog (real: `total_net_revenue`, `total_tokens_consumed`, `actual_input_tokens`). Confirmed via GET /catalog.

**In flight at note time:** ai-architect reconciling `expected_metric` → real catalog names (docs/10 + GET /catalog), then re-run for a meaningful category+metric ollama baseline. User separately creating an OpenRouter key to swap ollama→better model (pending base URL + model id).

**COE-lite (mechanism fix):** gate-1 accepted `promptfoo validate` + a manual node walkthrough as proof TWICE; neither runs the eval against a known-wrong case. NEW RULE: an eval-harness deliverable is gate-1-green only when a REAL run FAILS a deliberately-wrong row. That rule is how the false-green got caught.

**Uncommitted pile (commit from Mac terminal — see Next Actions #1).** Nothing this session committed yet; the parked 6-file dbt fix still uncommitted too.

### 2026-07-09 (late) - tpm-agent-amazon @ cli

**Situation:** Step 3 attempted; found the real reason the eval gate has never scored — the backend could not boot at all. No single interpreter had the full dep set (Homebrew 3.14 lacks opentelemetry; /usr/bin 3.9 lacks langgraph/langchain/OTLP-http), and C2 shipped with NO requirements.txt, venv, or boot recipe.

**Action:** Human chose "route durable fix first." Routed to senior-software-engineer-amazon → produced pinned `conversational-bi/requirements.txt` (Python 3.11) + `conversational-bi/README.md`. Verified GREEN on a fresh venv (gate 1): `Catalog loaded: 69 metrics`, `/health` HTTP 200 `catalog_loaded:true`. Gate-2 approved (DECISION_LOG #7). Steps 1 (boot fix) + 2 (health scored) DONE. Root cause detail: Presidio `PIIRedactor()` loads spaCy `en_core_web_lg` at import → hard boot dep, pinned via wheel; OTLP exporter imports unconditionally.

**Open / next:** (a) COMMIT the 2 boot files from the Mac terminal (scoped `git add`, NOT the parked 6 dbt files) + delete stray `.cbi-verify-venv/`. (b) Critical path to TR12-green (Step 7) = boot ✅ → provider `.env` pinned + harness defect fixed (Step 5, ai-architect) → run promptfoo. (c) Still parked: 6-file dbt fix commit, f31b75e governance call, harness defect + retrieval-quality eval (ai-architect).

### 2026-07-09 - tpm-agent-amazon @ cli

**Situation:** Waves 1+2 of the conversational-BI build committed to the submodule; the query path the prior note called "not implemented" now exists in git, not just on disk.

**Background:** ~1,500 lines landed as aa3235e (C1 evidence source), 2615ac4 (C2: LiteLLM gateway, LlamaIndex retriever, LangGraph, synthesis contract+prompt, OTEL), e1200a6 (C3 guardrails), b6f79b4 (C4 eval harness). C1 then reverted (f31b75e) after a false "dbt build failed" report (wrong CWD; project root is `dbt/`). Recurring `index.lock` traced to device-bridge git leaving un-unlinkable locks.

**Assessment:** Five-category response contract (TR12) is code-complete and committed (C2) but asserted-not-green — no eval or dbt build evidence captured. Retriever runs on fixtures, bypassing the governed seed, so the single-source-of-truth wiring is still open. Verification is blocked on local runtime (Postgres, Ollama/BYOK, promptfoo), none of which run in the workspace.

**Recommendation:** (1) Clear stale locks + `rm -rf _to_delete/`. (2) From `dbt/`, run `dbt build`; via `npx promptfoo@latest`, run the eval with backend up — move C4/TR12 from asserted to verified. (3) Route retrieval-quality eval to ai-architect. (4) Decide: restore governed evidence seed (revert f31b75e) or keep retriever on fixtures — a data-governance call.

### 2026-07-09 (pm) - tpm-agent-amazon @ cowork

**Situation:** Step 2 (verify dbt build) executed. First run was RED — 3 ERROR / 147 SKIP — but NOT the prior wrong-CWD false alarm: correct CWD, project loaded, 378 tests passed.

**Assessment:** Real latent defect in the gold layer, not dirty state. The dim PK post_hook pattern is structurally incompatible with dbt-postgres `table` rebuild (rename-to-backup + CASCADE-drop) once fact FKs reference the dim PK. Routed to analytics-engineer-dbt, who confirmed root cause, corrected the TPM `--full-refresh` prediction (table swap ignores the flag), and recommended Option b (remove DB-level PK/FK enforcement, keep dbt tests).

**Action:** Applied Option b to 6 files (in-place edits via device bridge, not git). Re-ran `dbt build` → GREEN, ERROR=0, SKIP=0, PASS 378→519. Step-2 gate verified (artifact captured, not asserted).

**Open / next:** (a) COMMIT the 6-file fix from the Mac terminal — uncommitted as of this note. (b) Step 3 eval / TR12 metric-selection gate still not run (needs backend + Ollama/BYOK + promptfoo). (c) Governance decision on f31b75e (restore governed evidence seed vs. keep retriever fixtures) still open. (d) Route retrieval-quality eval to ai-architect. (e) 15 dbt WARNs (dbt_project_evaluator naming/docs, int_revenue_daily not_null) are pre-existing, non-blocking — not triaged.

### 2026-07-09 (eve) - tpm-agent-amazon @ cowork

**Situation:** Step 3 (verify eval / TR12 metric-selection gate) attempted. Gate NOT scored — left RED.

**Assessment (three blockers, caught on paper before the run):**
1. **Prereq gap — backend is not a compose service.** `docker-compose.yml` has postgres/airflow/metabase/pgadmin, no `conversational-bi` service. `docker compose up -d` does NOT put `/query` on :8000; it must be started with `uvicorn backend.main:app --port 8000`. Confirmed live: both `curl -s localhost:8000/health` and `/catalog` returned empty → nothing listening. The `PASS=519` line the operator pasted is the dbt build (step 2), not the eval.
2. **Provider default.** Eval body sends only `{question}`; `main.py` falls back to `LLM_PROVIDER` env (default `ollama`). Whatever the server defaults to is what gets measured — must be pinned in `.env` before boot.
3. **Harness defect (routed to ai-architect).** `eval_config.yaml` postprocess returns only `parsed.category`; the two metric/domain `javascript` assertions then re-`JSON.parse` a bare string and use a non-promptfoo `condition:`/`assert_fail_message:` shape. Metric selection (the whole TR12 point) is never actually asserted. A green run would certify category routing only.

**Action:** No files touched (eval-only session, git-from-Mac-only). Gave the operator the boot + inspection runbook (now captured as Next Action 3). Backend never came up during the session, so the gate stayed unscored — did NOT score green on an absent backend.

**Open / next:** (a) Bring the backend up per Next Action 3, then run the gate. (b) ai-architect to fix the harness metric-assertion defect before TR12 can be called green. (c) Still-open carryovers from the pm note: commit the 6-file dbt fix; governance decision on f31b75e; route retrieval-quality eval to ai-architect.
