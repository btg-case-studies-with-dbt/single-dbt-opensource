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

### ✅ DONE — RANKING/ARGMAX GUARD (committed `d3d5747`, 2026-07-10, gate-2 passed)

The named residual from `3a7dab2` is shipped. See Progress Note below for the full arc.

- **Built:** prompt emits a `rank` object `{direction,by_field,phrase}` (ai-architect); deterministic `check_rank_coverage`+`rank_group_by`+`apply_argmax` guard abstains on ungoverned rank-dim, else forces group-by, sorts, returns true argmax/argmin (SSE, 18/18 unittests). Row 17 relabeled `ambiguous`→`unknown_metric`/abstain.
- **3× seed-pinned result:** 3 argmax rows correct in ALL 3 runs (deployment abstains; model=45810 llama; customer=13653 ACC008). Precision-on-answered ~96% (↑84%), category ~95%, hallucination 0 on governed data, coverage ~25-33%.
- **Scope:** commit d3d5747 = 6 argmax files only; parked 6-file dbt RI fix + `docs/03.PRD.md` deliberately still uncommitted in tree.

### ▶ NEXT INCREMENT — human to pick from the backlog

No single human-mandated next increment queued. Candidates (Outstanding list below): clarify-and-continue multi-turn (FR4, ~10-12 agent-hrs, needs solutions-architect one-way-door on non-terminal `ambiguous`); 8-family semantic-layer rebuild; parked 6-file dbt RI fix commit-vs-revert decision; "default-collision wrong-default" residual; retrieval-quality eval; TR12 wording reconciliation.
- **GUARDRAILS (still live):** parked 6-file dbt RI fix + `docs/03.PRD.md` remain modified in tree — do NOT bundle into an unrelated commit. Present a numbered task plan with estimates and wait for human approval before changing anything. Backend bring-up recipe is below.

Read this chart first. NOTE: `git` writes from THIS session worked cleanly with no stale locks (commit `3a67716`) — the old device-bridge lock warning did not bite; TPM can commit directly. The full query path WORKS end-to-end; the truthful TR12 baseline is **44% overall / 52% category / 4-of-6 metric (deepseek-v4-pro)**. The bottleneck is guardrails, not the model.

**Runtime bring-up (every session):** start Docker Desktop → `docker compose up -d postgres` → boot backend in venv from `conversational-bi/`: `DBT_HOST=localhost .venv/bin/python -m uvicorn backend.main:app --port 8000` (the gitignored `.env` supplies the provider: opencode/deepseek-v4-pro). `DBT_HOST=localhost` REQUIRED (mf reaches prod marts on localhost; in-container default stays `postgres`). To use ollama instead, set `LLM_PROVIDER=ollama OLLAMA_MODEL=llama3.1:8b` in the launch env.

- ✅ DONE this session: E2E query path, truthful harness, opencode/deepseek swap, catalog hygiene (69→44) — all committed at `3a67716`.

**Outstanding (priority order):**
1. **ROTATE the opencode key** (user) — it's in gitignored `.env` (unexposed in git) but was shown in a chat transcript. Replace the value in `conversational-bi/.env`.
2. ✅ DONE + COMMITTED `3a7dab2` 2026-07-10 — never-wrong-on-governed-data increment (prompt split + filter-coverage guard + ruler fixes + temp0/seed42). Gate-2 passed: precision 70%→84%, hallucination 0, coverage ~25%. See Progress Note below. **NEXT INCREMENT: ranking/argmax guard** for "which/most/top" questions (named residual, human-accepted, sequenced next; owner ai-architect ± SSE).
3. **8-family semantic-layer gap → data-architect (confirm) then analytics-engineer (rebuild).** 8 canonical metric families are named in `docs/10` but only their RETIRED forms were ever built; catalog hygiene now correctly withholds the retired forms, so these families are absent from the served catalog. Needs a scoped dbt rename + `dbt parse`/regenerate — care given prior build-failure history.
4. **Parked 6-file dbt RI fix** (dim/fct models, still uncommitted & modified in tree): decide commit (accept dbt-test-enforced RI) vs restore post_hooks. The prod marts were built WITH this fix present.
5. **Ratify/revert** `dbt-postgres==1.10.2` pin in `conversational-bi/requirements.txt` (additive, needed for mf→postgres).
6. **`int_revenue_daily` column contract → data-architect:** `int_schema.yml` tests 4 columns the model doesn't produce → clean `dbt build --target prod` errors + cascade-SKIPs marts. Interim `--exclude` used; durable green needs yml/model reconciled.
7. **Governance:** restore governed evidence seed (`git revert f31b75e`) vs keep retriever fixtures — log the call.
8. **Retrieval-quality eval** (Wave 2) — ai-architect, not started. **TRD TR12 wording** reconciliation — solutions-architect (flagged).

## Progress Notes

### 2026-07-11 - tpm-agent-amazon @ codex — Decision-2 approved re-run executed; promptfoo blocked by policy

**Situation:** Human approved `approve re-run execution` for the previously deferred Decision-2 semantic re-point. TPM did not pop either Claude quarantine stash; both remain parked as evidence. Re-implemented the switch cleanly: `total_net_revenue` / `total_gross_revenue` now source from `fct_revenue_daily`, token base measures source from `fct_token_usage_minute`, and `semantic_dimensions.yml` exposes conformed `account_size` + `model_family`.

**Receipts:** `dbt parse --target prod` green (existing `customer_revenue_monthly.v1` deprecation warning only); `dbt build --target prod` green (`PASS=519 WARN=11 ERROR=0 SKIP=0 NO-OP=9 TOTAL=539`); `mf validate-configs --semantic-validation-workers 1` green across manifest, semantic models, dimensions, entities, measures, metrics (`ERRORS: 0`). Direct `mf query` parity green for revenue by `revenue_id__source_region` / `revenue_id__billing_type` and tokens by `usage_id__source_region` / `usage_id__traffic_type`.

**Live-switch finding/fix:** The naive backend smoke initially answered "total net revenue by region" without the region breakdown because the LLM did not reliably map plain "region" to MetricFlow's prefixed `revenue_id__source_region`. Added deterministic dimension aliasing before validation plus known metric-gap overrides so "profit margin" stays `unknown_metric`. Unit suite now `76 tests OK`; patched backend smoke on `8001` returned region rows with `dimensions:["revenue_id__source_region"]`; deterministic local receipt returns `unknown_metric` for profit margin. The served catalog has 44 metrics / 28 dimensions; inspected base metrics expose 6 valid dimensions each, so the prior "4-per-metric" claim is false for this re-run.

**Blocked gate:** promptfoo eval not run. Running it would POST the governed catalog/questions through `/query` to the configured external OpenAI-compatible LLM; policy reviewer rejected the final `/query` rerun without explicit approval for that export. Human later approved proceeding with promptfoo, but policy reviewer still rejected `npx --yes promptfoo@0.121.18 eval --config eval/eval_config.yaml` because it would download/run a third-party tool and export saved eval questions plus the governed catalog externally. Treat full LLM-router regression as still blocked/not run.

### 2026-07-11 - tpm-agent-amazon @ codex — Claude Decision-2 rescue audit complete; re-run plan prepared, not executed

**Situation:** Human asked Codex TPM to rescue a Claude session that re-materialized the deferred Decision-2 semantic `fct_` re-point after prior containment. Read-only audit confirmed current tree is contained: only `docs/03.PRD.md` is modified; two quarantine stashes exist (`stash@{0}` repeat re-point, `stash@{1}` first unapproved re-point); current semantic source still points at rollups (`customer_revenue_weekly`, `token_usage_customer_monthly`), and current generated catalog maps base metrics to old rollups.

**Audit finding:** `stash@{0}` is not a clean apply artifact. It changes three semantic YAML files: adds `revenue_daily` on `fct_revenue_daily`, adds `token_usage_minute` on `fct_token_usage_minute`, relocates base additive revenue/token measures, and adds untracked `semantic_dimensions.yml` exposing only `account_size` and `model_family`. `stash@{1}` also included an unapproved `docs/2.TOOLSTACK.md`; per human note, do not chase vendoring/toolstack here.

**Prepared path:** Treat Decision 2 as a fresh approved increment only if the human explicitly approves the next implementation task list. Do not pop either stash. Use the stash as design evidence only, then re-implement under analytics-engineer ownership with real receipts: `dbt parse`, `dbt build --target prod`, `mf validate-configs`, generated catalog inspection, representative `mf query` parity, backend `/health` + `/query` smoke, and both promptfoo eval gates.

### 2026-07-11 (overnight) - tpm-agent-amazon @ cli — Steps 1-5 driven; agentic investigation loop BUILT

**Steps 1-4 CLOSED + signed off** (DECISION_LOG #11/#12): M1 governed-query contract (metric-routing 98.6%, worst-run 95.7%, 0 hallucinations, MetricFlow-only, clarify-continue deferred); M2 reliability (dbt RI fix committed + `int_revenue_daily` stale-yml fixed → `dbt build --target prod` exits 0 clean, no `--exclude` — the real fresh-clone blocker, NOT the RI post_hooks); M3 UI parity (frontend already complete, `/`→`/frontend/` 307 redirect added); M4 ORR (`07.ORR.md`, 13/13 gates green — **exposed key ROTATED + verified, gate #13 closed** `f7c9b44`).

**Step 5 REFRAMED then BUILT overnight** (DECISION_LOG #13/#14): retired the fabricated ticket-RAG (C1 tickets used fake FKs `ACME-1234` absent from dim_customer + wrong-product content — root cause the human caught). Evidence pivoted to **evidence-from-governed-data via a bounded agentic loop** (human pulled LangGraph loop into scope). Human approved overnight autonomous build on `dev`, **Decision 1=A** (investigative-intent trigger), Decisions 2 (semantic `fct_` re-point) & 3 (toolstack) deferred. Built: intent classifier, `GovernedMetricTool` (only data access, Step-1 guards), T1-T4 decomposition + additivity gate, bounded loop (MAX_STEPS=6), EvidenceBundle + **causal-language linter (causation structurally unrepresentable)**, `/query` intent gate + `INVESTIGATION_ENABLED` kill-switch. 70/70 unit tests; never-fabricate eval **13/14, 0 fabrications** (1 miss = fixture over-expected answered on ambiguous "input tokens"). Loop proven E2E on real `mf`. Commits: `c00f9cd`→`0303500`→`054bee2`→`5d3d108` on `dev`.

**OPEN for human (Step 5 not signed off):** final gate-2 acceptance; TRD wording reconcile (`investigated` vs `complete`, add `stopped_reason:"error"`); one-line `input-tokens` fixture relabel; QA CI-gate formalization; Decision 2 semantic re-point (unlocks region/intra-day evidence — coarse-but-honest today); Launch go/no-go + Sign-off. Retired `evidence_retriever.py`/`synthesis_*.py` are dead code (QA cleanup). ai-architect subagent hung in a Monitor wait-loop mid-run (orphaned promptfoo procs); recovered by `pkill` + TPM-owned authoritative eval — watch for that pattern.



### 2026-07-10 - tpm-agent-amazon @ cli — RANKING/ARGMAX GUARD shipped (committed `d3d5747`, gate-2 passed)

**Situation:** Built the named residual from `3a7dab2` — superlative questions ("which/most/top/highest/lowest") returned a grand TOTAL across groups instead of a ranking. Ran THE PLAY end to end; committed as one scoped increment.

**Arc:**
1. **Task 1 (TPM verify):** reproduced the failure live — row 17 "which deployment used the most tokens" → `answered`/`value:374758`/`dimensions:[]` (grand total). Fixture already expected `ambiguous`, so eval already failed it (banked as gate-1 evidence).
2. **ai-architect design (gate-1 pass):** hybrid keyed on rank-dim governance. Prompt emits a `rank` object `{direction,by_field,phrase}`; governed rank-dim → rank & return argmax, ungovernable → abstain. KEY finding via real runs: even the GOVERNED case was confidently wrong — "which model" grouped correctly but reported `rows[0]`=42929 when true argmax=45810 (mf doesn't sort). So a code guard is MANDATORY, not prompt-only.
3. **Parallel build:** ai-architect (prompt `llm_client.py` + eval `domain_questions.csv`/`eval_config.yaml`) ‖ SSE (`check_rank_coverage`+`rank_group_by`+`apply_argmax` in `query_translator.py`, mirrors filter guard, "peak" excluded from lexical backstop, 18/18 unittests). Disjoint files, frozen contract.
4. **Integration caught 2 defects the paper cross-check missed** (this is why "verify as one" exists): (a) model emitted `rank` as a bare STRING not the object → guard fail-safe-abstained → over-abstention on the 2 answerable rows; routed back to ai-architect (owns prompt), fixed to emit the object, guard unchanged. (b) fixture "which customer...last month" hit the empty December window (token-by-account_id data lands in January only) → one-line fixture fix to "last week".
5. **3× seed-pinned re-measure (temp0/seed42):** 3 argmax rows correct in ALL 3 runs — deployment abstains, model=45810/llama, customer=13653/ACC008. Precision-on-answered ~96% (↑from 84%), category ~95%, hallucination 0 on governed data, coverage ~25-33%.

**Mechanism win:** contracts that "agree on paper" still fail at integration — the shared-backend restart + combined re-measure is the gate that caught the string-vs-object mismatch. Kept ownership clean throughout (ai-architect owned prompt+eval, SSE owned code; TPM owned restart+re-measure+commit, absorbed nothing).

**Determinism caveat (unchanged):** non-argmax rows "completion tokens last month" + "quota per deployment this week" JITTER answered↔ambiguous↔unknown across runs (each passes ≥1 of 3), always failing toward SAFE abstention, never a wrong answer. deepseek-v4-pro non-determinism, not an argmax regression. "completion tokens last month" also hits the empty-Dec window.

**Commit `d3d5747` scoped to 6 files:** `llm_client.py`, `query_translator.py`, `eval/domain_questions.csv`, `eval/eval_config.yaml`, `tests/test_check_rank_coverage.py`, `eval/prefix_baseline_20260710-121707.json`. Parked 6-file dbt RI fix + `docs/03.PRD.md` deliberately EXCLUDED (still modified in tree).

### 2026-07-10 - tpm-agent-amazon @ cli — never-wrong-on-governed-data increment built (uncommitted, awaiting final re-measure + gate-2)

**Situation:** Human demanded the bar in their own words: "with structured data you cannot go wrong; you can say 'I don't have the data,' but you cannot afford to be inaccurate." Drove the guardrail lever to deliver it.

**Arc this session:**
1. **First guardrail pass (ai-architect): 44%→84%.** Root cause of the old 44% was that `ambiguous`/`unsupported_domain` were structurally unreachable in code and the prompt forced "always pick a metric." Fix in `backend/llm_client._build_system_prompt` (decline vocab + few-shots) + `backend/query_translator.process_question` (safety-biased classification routing). NOT the model — deepseek was already 6/6 on answerable.
2. **Bar defined & defended (ai-architect, seed-pinned temp0×3):** (a) never-out-of-catalog = provable deterministic 100%, proven (TR3 guard rejects fabricated names). (b) never-wrong-but-valid = NOT guaranteeable by LLM alone — found **3 STABLE (deterministic) wrong answers**: silent-drop of a restrictive filter → unscoped total returned as if scoped. Precision-on-answered was **70%**. Sin is 100% over-answering, 0 under-answering (recall 7/7). Ruler fixed: `revenue_per_customer` IS served (→answered); no margin metric exists (→unknown_metric).
3. **The mechanism = split ownership.** ai-architect prompt split: model now emits a `filters` field distinguishing BREAKDOWN (group-by, droppable, still answer) from restrictive SCOPE filter (`field:null` when ungovernable). SSE deterministic guard `check_filter_coverage()` in `query_translator.py`: keyed off "was scope APPLIED to the mf query" (no `--where` push-down exists → always false → any non-empty `filters` abstains). Phase-2 push-down deferred behind a clean seam (`_filter_is_applied`). Abstain reuses `unknown_metric` + `reason:"unsupported_filter"` (five-category contract intact), message per human: state not-tracked + SHOW available governed dims + NAME the unmatched value.
4. **SSE verified GREEN:** 10/10 stdlib unittest; E2E on live backend — CS-team tokens / subscriptions / "net revenue from marketplace" all abstain with explain-and-show; "revenue by product line" (benign breakdown) still answers. Literal "value from marketplace" abstains via prompt's vague-measure path not the guard — both safe (noted, not a defect).

**Emergent design (human insight, folded into clarify-and-continue follow-on spec, docs/03.PRD.md):** a clarifying question only helps if the user's answer maps to a GOVERNED field; if it names ungoverned data it's a data-model gap → escalate to data-architect, don't fake. Three-way: answer / clarify-to-user / escalate-as-governance-gap.

**Uncommitted on `dev` (commit as ONE increment after gate-2):** `backend/llm_client.py` (prompt split + temp0/seed), `backend/query_translator.py` (guard + routing), `conversational-bi/tests/test_check_filter_coverage.py` + `tests/__init__.py` (new), `eval/domain_questions.csv` (2 ruler fixes). PLUS the still-parked 6-file dbt RI fix (separate, older — do NOT bundle).

**GATE-2 PASSED + COMMITTED `3a7dab2` (2026-07-10).** Final 3× seed-pinned numbers: precision-on-answered **84%** (↑from 70%), category **93%**, deterministic hallucination **0**, coverage **~25%** (↓from ~40%, accepted). All 3 mis-scoped wrong answers now abstain (stable across runs); benign breakdown still answers; gate-1 confirmed non-vacuous (real rows FAIL). Commit scoped to 4 paths (llm_client, query_translator, domain_questions.csv, tests/) — deliberately EXCLUDED the parked 6-file dbt RI fix and docs/03.PRD.md (still modified in tree).

**Named residual → NEXT INCREMENT (ranking/argmax guard):** "which/most/top/highest" questions (e.g. row 17 "which deployment used the most tokens") return a grand TOTAL instead of a ranking — a correct number to a different question. Distinct failure class: not a scope filter, not out-of-catalog, so neither guard nor prompt catches it. Fix = detect superlative → force group-by breakdown or abstain-and-clarify. New increment, owner ai-architect (+ SSE if code guard). Human accepted as named residual, sequenced after.

**Determinism caveat:** deepseek-v4-pro is NOT bit-deterministic at temp 0 — one row jittered answered↔safe-abstain (never wrong). A hard determinism guarantee is a model/provider question → ai-research, not a prompt fix.

**Open follow-ons (deferred, tracked):** clarify-and-continue multi-turn (PM defined FR4/FR4a/FR4b in docs/03.PRD.md; software-architect sized ~10-12 agent-hrs, stateless client-carried continuation, `agent_graph.py` is DEAD CODE not on request path; needs `ambiguous` non-terminal contract change → solutions-architect one-way door); Phase-2 filter push-down; "default-collision wrong-default" residual (bare "revenue"→net silently — bounded, mitigate by echoing metric label, zero-it = PM coverage/safety call); vendoring `docs/agents-reference/` (SSE flagged, human's call).

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
