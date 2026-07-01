# Launch Gates — MetricFlow Conversational BI

**Program status:** Phase 1 (MetricFlow semantic layer) green. Phase 2 (NL chat interface) built, pending hosted-model eval.

## Phase 1 Gates — MetricFlow Semantic Layer

| # | Gate | Criteria | Status |
|---|------|----------|--------|
| 1 | `dbt parse` succeeds | `target/semantic_manifest.json` has entries for all 3 domains | ✅ |
| 2 | `mf validate-configs` passes | 0 errors across all 5 validation stages | ✅ |
| 3 | Revenue query returns data | `mf query --metrics total_net_revenue --group-by metric_time` | ✅ |
| 4 | Token usage query returns data | `mf query --metrics total_tokens_consumed --group-by metric_time` | ✅ |
| 5 | Quota query returns data | `mf query --metrics effective_requests_per_minute --group-by metric_time` | ✅ |
| 6 | Expression metric works | `mf query --metrics net_revenue_usd` returns correct conversion | ✅ |
| 7 | Ratio metric works | `mf query --metrics revenue_per_customer` returns data | ✅ |
| 8 | Cross-domain queries work | Multi-metric queries across revenue + token_usage return results | ✅ |
| 9 | All 27 metrics defined | 11 revenue + 9 token usage + 7 quota | ✅ |
| 10 | All 7 seed metrics mapped | Seed's governed revenue metrics have MetricFlow equivalents | ✅ |

## Phase 2 Gates — NL Chat Interface

| # | Gate | Criteria | Status |
|---|------|----------|--------|
| 1 | Catalog builder works | `catalog_builder.py` compresses `semantic_manifest.json` to condensed YAML | ✅ |
| 2 | Hallucination defense works | Translator rejects unknown metrics before execution | ✅ |
| 3 | LLM metric selection accuracy | LLM picks correct metric from catalog ≥ 90% on eval set | ⚠️ (100% on local, needs hosted model for full eval) |
| 4 | Eval runner works | 10-fixture suite runs and scores | ✅ |
| 5 | FastAPI serves /query | POST /query returns structured response | ✅ |
| 6 | Time range resolution works | "last week", "Q1 2026" resolve to absolute ISO dates | ✅ |
| 7 | Schema validation works | Invalid LLM output is rejected with retry then fallback | ✅ |
| 8 | Chat UI renders results | Frontend shows query results in table | ✅ |

## Production Launch Gates

These must all be green before the system is used for real business decisions.

| # | Gate | Criteria | Owner | Mechanism |
|---|------|----------|-------|-----------|
| P1 | Hosted model eval passes | Eval suite ≥ 0.90 metric selection, ≥ 0.85 dimension selection, ≤ 0.01 hallucination rate with chosen hosted model (Claude, GPT-4o, etc.) | ai-architect | CI eval gate on every prompt change |
| P2 | Eval suite expanded | Minimum 35 questions across all 7 categories | ai-architect | Merged eval fixture set |
| P3 | Rejection accuracy measured | Unanswerable questions correctly rejected ≥ 95% | ai-architect | Dedicated rejection eval category |
| P4 | Operational runbook exists | How to restart the API, rebuild the catalog, diagnose LLM failures | senior-software-engineer | `RUNBOOK.md` in `conversational-bi/` |
| P5 | No hallucinated metrics in production | Hard check in translator blocks execution of unknown metric names 100% of the time | senior-software-engineer | Manifest membership scan before `mf query` |
| P6 | Query latency acceptable | P95 response time < 10s for hosted model queries | senior-software-engineer | Measured in load test |
| P7 | BYOK path documented | User can configure their own API key for hosted LLM | senior-software-engineer | Documented in README |

## Decision Log

| Decision | Door type | Choice | Trades away |
|----------|-----------|--------|-------------|
| Phase 1 first | Two-way | Build MetricFlow semantic layer before NL interface | Faster chat prototype in exchange for governed foundation |
| Single-shot JSON output | Two-way | System prompt + JSON mode, not function calling | Tool-calling's structured reasoning in exchange for 1-round-trip latency |
| Condensed catalog | Two-way | Pre-process manifest to 5KB YAML | Freshness lag in exchange for prompt token budget |
| Hallucination defense in translator | One-way | Hard manifest check before mf query execution | LLM-only trust in exchange for guaranteed governance |
| Local vs hosted LLM | Two-way | Architecture supports both; eval bar requires hosted | Local-only deployment in exchange for accuracy |

## Status Mechanism

- **Cadence:** Review after each major change (prompt update, model swap, catalog expansion)
- **Green rule:** Green = artifact exists AND gate criteria met. No "almost done."
- **Eval gate:** Every PR that changes the prompt system or catalog must pass the 10-fixture smoke suite
- **Expansion rule:** New metrics or dimensions added to the dbt project must also update the condensed catalog build script — no drift between Phase 1 and Phase 2 allowed

## Architecture Diagram

```
User question
     │
     ▼
┌─────────────────┐
│  Chat UI        │  frontend/index.html
│  (HTML/JS)      │
└────────┬────────┘
         │  POST /query
         ▼
┌─────────────────┐
│  FastAPI         │  backend/main.py
│  /query /catalog │
│  /health         │
└────────┬────────┘
         │  question
         ▼
┌─────────────────┐
│  LLM Client      │  backend/llm_client.py
│  (Ollama/OpenAI/ │
│   Anthropic)     │
└────────┬────────┘
         │  structured JSON spec
         ▼
┌──────────────────────────┐
│  Schema validation        │  backend/query_translator.py
│  + hallucination check    │
│  + time range resolution  │
└────────┬─────────────────┘
         │  validated spec
         ▼
┌──────────────────────────┐
│  mf query execution       │  MetricFlow CLI
│  (governed, no SQL path)  │
└────────┬─────────────────┘
         │  result set
         ▼
┌─────────────────┐
│  Response        │
│  → Chat UI       │
│  (table + text)  │
└─────────────────┘
```

## Capability Gaps

No missing roles identified. The owned workstreams and their owners:

| Work | Owner | Status |
|------|-------|--------|
| MetricFlow semantic layer | analytics-engineer-dbt | ✅ Complete |
| NL-metric selector design | ai-architect | ✅ Complete |
| Execution layer + chat | senior-software-engineer | ✅ Built |
| Production eval + model selection | ai-architect | ⏳ Pending hosted model |
| Operational readiness | senior-software-engineer | ⏳ Pending RUNBOOK.md |
