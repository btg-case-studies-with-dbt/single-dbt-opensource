# Conversational-BI backend — boot recipe

FastAPI app: `backend.main:app`. This recipe brings the backend up on a **fresh
venv** and proves `GET /health` returns **200**.

## Requirements

- **Python 3.11** (verified on 3.11.15). Do **not** use the system interpreters:
  `/usr/bin/python3` (3.9) and Homebrew `python3.14` each lack part of the stack.
  On this Mac, Python 3.11 is at `/opt/homebrew/bin/python3.11`.
- **Postgres** up on `:5432` (docker) — the MetricFlow adapter's target.
- **dbt build artifacts present** (the catalog is read from them at startup):
  - `../dbt/target/semantic_manifest.json`
  - `../dbt/target/catalog_for_llm.yaml`
  - `../docs/contracts/1.METRIC_DICTIONARY.csv`
  Regenerate with `dbt parse` from the `dbt/` project if missing.
- No `.env` is required for `/health` (it makes no LLM call).

## Boot

Run from the `conversational-bi/` directory.

```bash
# 1. Create an isolated venv with Python 3.11
/opt/homebrew/bin/python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip

# 2. Install the pinned dependency set
#    (includes the en_core_web_lg spaCy model Presidio loads at import time,
#     and dbt-metricflow so `mf` resolves inside the venv)
pip install -r requirements.txt

# 3. Confirm the MetricFlow CLI resolves from THIS venv (not the system mf)
mf --version          # -> mf, version 0.13.0

# 4. Start the server (must be launched from conversational-bi/ so the
#    catalog_builder relative paths ../dbt/target/... resolve)
python -m uvicorn backend.main:app --port 8000
```

Watch the startup log for the catalog line (metric count > 0):

```
backend.main: Catalog loaded: 4 domains, 69 metrics, 34 dimensions
INFO:     Application startup complete.
```

## Verify /health

In a second terminal:

```bash
curl -s -w '\n%{http_code}\n' localhost:8000/health
```

Expected — **HTTP 200**:

```json
{"status":"healthy","catalog_loaded":true,"catalog_metrics_count":69,"mf_cli_available":true}
```

`/health` returns 200 only when **both** are true:
- `catalog_loaded` — `catalog_builder.build_catalog()` read the semantic manifest
  and found metrics (69 here).
- `mf_cli_available` — `mf --version` succeeded on `PATH` (satisfied by the
  `dbt-metricflow` pin, which puts `mf` in `.venv/bin`).

A `503` with `"catalog_loaded": false` means the dbt artifacts are missing —
regenerate them (`dbt parse`) and confirm you launched uvicorn from
`conversational-bi/`. A `503` with `"mf_cli_available": false` means the venv
is not active (or `dbt-metricflow` did not install).

## Notes

- OpenTelemetry is off by default; set `OTEL_ENABLED=true` to enable tracing.
  The OTLP/HTTP exporter is imported at module load regardless, so it is a
  required dependency even when tracing is disabled.
- `POST /query` needs an LLM provider (`.env` / `.env.example`); `/health` and
  `/catalog` do not.
