# 3a — dbt Commands

## Before you start
- Completed Runbook 2 — stack running, all bronze data loaded, `dbt debug` shows `All checks passed`, `dbt deps` completed
- All containers showing `Up` in `docker compose ps`
- `(.dbt-venv)` showing in your terminal prompt

---

## Pre-flight check — run before every dbt session

```bash
# Check 1 — correct venv is active
# Your prompt must show (.dbt-venv) — not any other venv name.
# If you see a different venv e.g. (dbt-case-studies) — you activated the wrong one.
# Fix: deactivate && source ~/.dbt-venv/bin/activate
echo $VIRTUAL_ENV
# Must show /Users/yourname/.dbt-venv

# Check 2 — stack is running
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource
docker compose ps
# All 5 containers must show Up

# Check 3 — dbt works
cd dbt
dbt --version
# Must show Core: 1.x.x

# Check 4 — env vars loaded
echo $DBT_SCHEMA
# Must return your personal schema name e.g. dbt_kanja
# If empty — run: source ~/.zshrc
```

---

## Step 1 — Create sources.yml

`sources.yml` tells dbt about the 12 bronze tables it didn't create — so it can track lineage, validate they exist at compile time, and run freshness checks.

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource
code dbt/models/staging/sources.yml
```

Type this exactly, then save with `⌘ + S`:

```yaml
version: 2

sources:
  - name: raw_bronze
    schema: raw_bronze
    description: "Raw bronze layer — data exactly as it arrived. Never modified."
    tags: ['bronze', 'raw']
    meta:
      owner: "Data Engineering"
      data_classification: "internal"

    # Default freshness applied to all tables unless overridden
    loaded_at_field: loaded_at
    freshness:
      warn_after:  {count: 24, period: hour}
      error_after: {count: 48, period: hour}

    tables:

      # ── Config tables — loaded by Airflow DAG ─────────────────────────────
      - name: config_model_dimensions
        description: "AI model technical specifications — publisher, accelerator type, replica count, performance metrics. Loaded once by the load_config_bronze DAG."
        tags: ['config', 'one-time']
        meta:
          freshness_sla: "manual load"
        freshness: null    # manually loaded — disable freshness check
        columns:
          - name: model_variant
            description: "Unique model identifier e.g. claude-3-5-sonnet-20241022. Primary key."
            tests:
              - not_null
          - name: snapshot_date
            description: "Date this config snapshot was taken."
            tests:
              - not_null

      - name: config_model_region_availability
        description: "Which AI models are deployed in which AWS regions. Loaded once by the load_config_bronze DAG."
        tags: ['config', 'one-time']
        freshness: null    # manually loaded — disable freshness check
        columns:
          - name: model_variant
            description: "Model identifier — foreign key to config_model_dimensions."
            tests:
              - not_null
          - name: source_region
            description: "AWS region code e.g. us-east-1."
            tests:
              - not_null
          - name: is_active
            description: "Whether the model is currently deployed in this region."
            tests:
              - not_null

      # ── Customer data ─────────────────────────────────────────────────────
      - name: customer_details
        description: "Customer account master data — segment, vertical, account size. Append-only."
        tags: ['customer', 'pii']
        meta:
          data_classification: "confidential"
        freshness:
          warn_after:  {count: 30, period: day}
          error_after: {count: 60, period: day}
        columns:
          - name: account_id
            description: "Unique customer account identifier. Primary key."
            tags: ['primary_key', 'pii']
            tests:
              - not_null
              - unique
          - name: loaded_at
            description: "Timestamp when this row was inserted into the bronze layer."
            tests:
              - not_null

      # ── Token usage — core fact tables ───────────────────────────────────
      - name: inference_user_token_usage_open_source
        description: "Per-request token usage events for open source models. High volume — appended on every API request."
        tags: ['token_usage', 'high_volume']
        freshness:
          warn_after:  {count: 6,  period: hour}
          error_after: {count: 12, period: hour}
        columns:
          - name: request_id
            description: "Unique identifier for each API request. Primary key."
            tags: ['primary_key']
            tests:
              - not_null
              - unique
          - name: account_id
            description: "Customer account — foreign key to customer_details."
            tests:
              - not_null
          - name: model_variant
            description: "Model used for this request."
            tests:
              - not_null
          - name: source_region
            description: "AWS region where the request originated."
            tests:
              - not_null

      - name: inference_user_token_usage_proprietary
        description: "Per-request token usage events for proprietary models. High volume — appended on every API request."
        tags: ['token_usage', 'high_volume']
        freshness:
          warn_after:  {count: 6,  period: hour}
          error_after: {count: 12, period: hour}
        columns:
          - name: request_id
            description: "Unique identifier for each API request. Primary key."
            tags: ['primary_key']
            tests:
              - not_null
              - unique
          - name: account_id
            description: "Customer account — foreign key to customer_details."
            tests:
              - not_null
          - name: model_variant
            description: "Model used for this request."
            tests:
              - not_null
          - name: source_region
            description: "AWS region where the request originated."
            tests:
              - not_null

      # ── Resource utilization ──────────────────────────────────────────────
      - name: resource_accelerator_inventory
        description: "GPU/TPU accelerator inventory snapshots by model and region."
        tags: ['resource']
        columns:
          - name: loaded_at
            tests:
              - not_null

      - name: resource_model_utilization
        description: "Model utilization rates — ratio of allocated vs used capacity per model per region."
        tags: ['resource']
        columns:
          - name: model_variant
            tests:
              - not_null
          - name: loaded_at
            tests:
              - not_null

      - name: resource_model_instance_allocation
        description: "Model instance allocation counts — how many instances are allocated vs used."
        tags: ['resource']
        columns:
          - name: model_variant
            tests:
              - not_null
          - name: loaded_at
            tests:
              - not_null

      # ── Revenue ───────────────────────────────────────────────────────────
      - name: revenue_account_daily
        description: "Daily revenue at account + product_sku + model_variant + region grain. Core revenue fact table."
        tags: ['revenue', 'finance']
        freshness:
          warn_after:  {count: 25, period: hour}
          error_after: {count: 49, period: hour}
        columns:
          - name: account_id
            description: "Customer account — foreign key to customer_details."
            tests:
              - not_null
          - name: model_variant
            description: "Model — foreign key to config_model_dimensions."
            tests:
              - not_null
          - name: loaded_at
            tests:
              - not_null

      # ── Quota and rate limits ─────────────────────────────────────────────
      - name: quota_default_rate_limits
        description: "Default rate limits per model per region — tokens per minute, requests per minute."
        tags: ['quota']
        freshness:
          warn_after:  {count: 7, period: day}
          error_after: {count: 14, period: day}
        columns:
          - name: model_variant
            tests:
              - not_null
          - name: source_region
            tests:
              - not_null

      - name: quota_customer_rate_limit_adjustments
        description: "Customer-specific rate limit overrides — increases or decreases from the default limits."
        tags: ['quota', 'customer']
        columns:
          - name: account_id
            tests:
              - not_null
          - name: model_variant
            tests:
              - not_null
          - name: loaded_at
            tests:
              - not_null

      - name: quota_customer_rate_limit_requests
        description: "Customer requests to change their rate limits — upgrade or downgrade requests with approval status."
        tags: ['quota', 'customer']
        columns:
          - name: account_id
            tests:
              - not_null
          - name: model_variant
            tests:
              - not_null
          - name: loaded_at
            tests:
              - not_null
```

Commit:

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource
git add dbt/models/staging/sources.yml
git commit -m "add sources.yml"
```

Verify dbt can see all 12 registered sources:

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource/dbt
dbt ls --resource-type source
```

**Checkpoint:** 12 source names listed — one per bronze table.

---

## Step 2 — Run dbt seed

First copy `region_mapping.csv` from `common/database_scripts/` into `dbt/seeds/`:

```bash
cp ~/Documents/btg-case-studies-with-dbt/common/database_scripts/region_mapping.csv    ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource/dbt/seeds/
```

Before writing `seeds.yml` — inspect the CSV to understand its columns and values:

```bash
python3 -c "
import csv
with open('${HOME}/Documents/btg-case-studies-with-dbt/common/database_scripts/region_mapping.csv') as f:
    reader = csv.DictReader(f)
    print('Columns:', reader.fieldnames)
    for row in list(reader)[:2]:
        print(row)
"
```

This shows all column names and two sample rows — enough to confirm types and expected values before writing `seeds.yml`.

Create `dbt/seeds/seeds.yml`:

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource
code dbt/seeds/seeds.yml
```

Type this exactly, then save with `⌘ + S`:

```yaml
version: 2

seeds:
  - name: region_mapping
    description: "AWS region reference data — maps AWS region codes to territories, airport codes, and GovCloud flags. 29 rows, one per AWS region. Static reference table — changes only when AWS adds new regions."
    tags: ['reference', 'static', 'seeds']
    meta:
      owner: "Data Engineering"
      update_frequency: "on AWS region additions only"

    config:
      schema: seeds
      column_types:
        source_region: varchar
        airport_code:  varchar
        territory:     varchar
        govcloud:      boolean   # critical — must be boolean, not varchar
        description:   varchar

    columns:
      - name: source_region
        description: "AWS region code e.g. us-east-1. Primary key — one row per region."
        tests:
          - unique
          - not_null

      - name: airport_code
        description: "Three-letter IATA airport code for the region's physical location e.g. IAD for us-east-1."
        tests:
          - not_null

      - name: territory
        description: "Geographic territory grouping. Used to aggregate metrics by region in mart models."
        tests:
          - not_null
          - accepted_values:
              values: ['US', 'North America', 'Europe', 'Asia Pacific',
                       'Middle East', 'Africa', 'South America', 'China',
                       'US GovCloud']

      - name: govcloud
        description: "True if this is an AWS GovCloud region requiring special compliance handling. Must be boolean — dbt infers varchar from CSV without explicit column_types declaration."
        tests:
          - not_null

      - name: description
        description: "Human-readable region description e.g. 'US East (N. Virginia) - Primary US region'."
        tests:
          - not_null
```

Commit:

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource
git add dbt/seeds/
git commit -m "add region_mapping seed and seeds.yml"
```

Now run the seed:

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource/dbt
dbt seed
```

**Checkpoint:** `OK loaded seed file seeds.region_mapping`

Verify in pgAdmin: `seeds` schema → Tables → `region_mapping` → 29 rows

---

## Step 3 — Run dbt snapshot

dbt recommends snapshotting raw bronze tables before any transformation. Snapshots capture how records change over time — customer segment changes, model going active/inactive in a region. Running them against bronze ensures you capture the original raw history, not already-transformed data.

### Understanding the snapshot config

Before writing any snapshot SQL, understand the five config parameters:

| Parameter | What it does |
|---|---|
| `target_schema` | Which schema the snapshot table is written to — we use `snapshots` |
| `unique_key` | Column(s) that identify a unique record. When dbt sees the same key across runs it knows it's the same record and can detect changes |
| `strategy` | `timestamp` — compare an `updated_at` column. `check` — hash specific columns and compare |
| `updated_at` | Timestamp column to compare (timestamp strategy only) |
| `check_cols` | Which columns to watch for changes (check strategy only). Use a list or `'all'` |
| `invalidate_hard_deletes` | When `True` — if a row disappears from the source, dbt closes the snapshot record by setting `dbt_valid_to`. Default `False` |

**Two strategies:**
- `timestamp` — recommended. Fast, one column comparison. Use when source has a reliable `updated_at` or `loaded_at` column.
- `check` — hashes specified columns on every run. Use when no reliable timestamp exists but you know which columns to watch.

**`dbt_valid_from` / `dbt_valid_to` — how history is tracked:**

When a change is detected dbt closes the old row by setting `dbt_valid_to` to the current timestamp, then inserts a new row with `dbt_valid_to = NULL` — meaning currently active. Rows with `dbt_valid_to = NULL` are the current state.

### Create the snapshot template

First create a reusable template that lives in `dbt/snapshots/` but never runs:

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource
code dbt/snapshots/_snapshot_template.sql
```

Type this exactly, then save with `⌘ + S`:

```sql
{% snapshot _snapshot_template %}
{{
    config(
        enabled=false,   -- change to enabled=true (or remove) when ready to run
        target_schema='snapshots',
        unique_key='your_id_column',

        -- Option A: timestamp strategy (recommended)
        -- Use when source has a reliable updated_at or loaded_at column
        strategy='timestamp',
        updated_at='loaded_at',

        -- Option B: check strategy
        -- Use when no reliable timestamp exists
        -- strategy='check',
        -- check_cols=['col1', 'col2'],   -- watch specific columns
        -- check_cols='all',              -- or hash all columns

        -- Optional: close snapshot records when source row is deleted
        -- invalidate_hard_deletes=True
    )
}}

-- SELECT * is fine to start with.
-- Once the snapshot is stable, replace with explicit column names
-- to protect history from upstream schema changes.
-- A new column added to the source will cause a schema error on the next
-- snapshot run — you'd need --full-refresh which wipes all history.
select * from {{ source('raw_bronze', 'your_table') }}

{% endsnapshot %}
```

> `enabled=false` — dbt parses this file but skips it at runtime. Zero overhead. Copy this file, rename it, fill in the 4 values, set `enabled=true` (or remove it) and you have a working snapshot.

### Copy the snapshot files

Copy both snapshot files from the reference implementation into `dbt/snapshots/`:

```
customer_details_snapshot.sql    -- strategy: timestamp, unique_key: account_id
model_availability_snapshot.sql  -- strategy: check, unique_key: availability_key (composite)
```

Open each file and read the config before running — confirm the unique key and strategy match what we discussed.

### Run:

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource/dbt
dbt snapshot
```

**Checkpoint:** Both snapshots show `OK`

Verify in pgAdmin: `snapshots` schema → Tables → `customer_details_snapshot`, `model_availability_snapshot`

Each table has all source columns plus the 4 dbt metadata columns: `dbt_scd_id`, `dbt_updated_at`, `dbt_valid_from`, `dbt_valid_to`.

Commit:

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource
git add dbt/snapshots/
git commit -m "add snapshot template and snapshot models"
```

---

## Step 4 — Create staging models and run

> ⚠️ **`schema.yml` is the hardest file to debug in dbt.**
>
> YAML is whitespace-sensitive — one wrong indentation and dbt fails with a cryptic error that doesn't tell you the line number. The error message says "test definition dictionary must have exactly one key" or "invalid test config" but gives you no line reference.
>
> **Best practices before you touch `schema.yml`:**
>
> 1. **Install the YAML extension in VS Code** (Red Hat) — it underlines bad indentation in real time
> 2. **Use `yamllint` to find issues** — `yamllint dbt/models/staging/schema.yml`
> 3. **Run `dbt ls` after every save** — it parses the file and catches structural errors before `dbt run`
> 4. **Never mix tabs and spaces** — YAML only accepts spaces. VS Code shows `Spaces: 2` in the bottom right — keep it there
> 5. **Build incrementally** — add one model at a time, run `dbt ls` after each. Don't write the entire file and then debug
> 6. **`config:` must be inside the test block** — not a sibling of it. This is the most common mistake with `not_null`, `relationships`, and `dbt_expectations` tests
> 7. **Package tests need `arguments:`** — in dbt 1.9+, `relationships`, `accepted_values`, and `dbt_expectations` tests require their arguments nested under an `arguments:` key

Copy all 12 staging model SQL files from the reference implementation into `dbt/models/staging/`. Also copy `schema.yml` into `dbt/models/staging/schema.yml`.

The 12 staging models:
```
stg_config_model_dimensions.sql
stg_config_model_region_availability.sql
stg_customer_details.sql
stg_accelerator_inventory.sql
stg_model_instance_allocation.sql
stg_model_utilization.sql
stg_token_usage_open_source.sql
stg_token_usage_proprietary.sql
stg_revenue_account_daily.sql
stg_quota_default_rate_limits.sql
stg_quota_customer_rate_limit_adjustments.sql
stg_quota_customer_rate_limit_requests.sql
```

### Understanding schema.yml

`schema.yml` sits in `dbt/models/staging/` and does two jobs — documentation and testing. Before running any models, open it and read it. Here is what each test type does and why it is there:

| Test | Why we use it |
|---|---|
| `not_null` | Column must always have a value. Used on primary keys, foreign keys, dates, and amounts. A null in these columns breaks downstream models silently. |
| `unique` | No two rows can share the same value. Used on primary keys only — `account_id`, `request_id`. |
| `accepted_values` | Column can only contain values from a fixed list. Used on categorical columns — `segment`, `billing_type`, `request_status`. Catches upstream data quality issues before they reach marts. |
| `relationships` | Foreign key check — every `account_id` in token usage must exist in `stg_customer_details`. Catches orphaned records from accounts deleted in the CRM but still producing usage events. |
| `dbt_utils.expression_is_true` | Validates a SQL expression across columns — e.g. `net_revenue <= total_gross_revenue`. Use for business rules that no single-column test can express. |
| `dbt_utils.not_empty_string` | Column is not null AND not an empty string `''`. `not_null` alone passes an empty string — this catches both. Used on name fields. |
| `dbt_expectations.expect_column_values_to_be_between` | Numeric column must be within a range. Used on ratios (0–1), percentages (0–100), token counts (≥1), revenue (≥0). |

**Severity levels:**
- `error` (default) — test failure stops the run. Use on business-critical columns.
- `warn` — test failure logs a warning but the run continues. Use on fields that should be populated but are not critical to downstream correctness.

> Open `schema.yml` and read the inline comments — every test has a comment explaining the business reason for it, not just what it checks.

---

### Step 4a — Customer and model staging

Before running anything — use `dbt ls` to preview which models a selector will touch without hitting the database:

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource/dbt
dbt ls --select stg_customer_details stg_config_model_dimensions stg_config_model_region_availability
```

**Checkpoint:** Three model names listed. If nothing returns — the files are not in the right folder.

Now open `stg_customer_details.sql` and introduce an intentional mistake — change the source table name to something that doesn't exist:

```sql
-- Change this:
from {{ source('raw_bronze', 'customer_details') }}
-- To this (intentional typo):
from {{ source('raw_bronze', 'customer_detailss') }}
```

Save, then compile before running — this catches errors without touching the database:

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource/dbt
dbt compile --select stg_customer_details
```

dbt fails immediately with:

```
Compilation Error in model stg_customer_details
  'raw_bronze' has no table named 'customer_detailss'
```

Fix the typo — change back to `customer_details`. Save. Now verify the fix compiled correctly:

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource/dbt
dbt compile --select stg_customer_details
```

**Checkpoint:** No errors. Compiled SQL written to `target/compiled/`.

Since only `stg_customer_details` changed, use `state:modified+` to run only what changed and its downstream dependents — not the full staging layer:

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource/dbt
dbt run --select stg_customer_details stg_config_model_dimensions stg_config_model_region_availability
```

**Checkpoint:** All 3 models show `OK created sql view`

---

### Step 4b — Revenue staging

Preview what will run:

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource/dbt
dbt ls --select stg_revenue_account_daily stg_token_usage_open_source stg_token_usage_proprietary
```

Run the revenue group using `model_name+` — this runs each model plus all its downstream dependents:

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource/dbt
dbt run --select stg_revenue_account_daily+ stg_token_usage_open_source+ stg_token_usage_proprietary+
```

> `model_name+` means "this model and everything downstream that depends on it." Useful when you change a model and want to rebuild the full downstream impact in one command.

**Checkpoint:** All 3 models show `OK created sql view`

---

### Step 4c — Resource and quota staging

Preview:

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource/dbt
dbt ls --select stg_accelerator_inventory stg_model_instance_allocation stg_model_utilization stg_quota_default_rate_limits stg_quota_customer_rate_limit_adjustments stg_quota_customer_rate_limit_requests
```

Run the remaining 6 models. You can also use a tag selector if your models are tagged — for example `tag:resource` runs all resource-tagged models at once without listing them individually:

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource/dbt
dbt run --select stg_accelerator_inventory stg_model_instance_allocation stg_model_utilization stg_quota_default_rate_limits stg_quota_customer_rate_limit_adjustments stg_quota_customer_rate_limit_requests
```

> If you tagged your models with `tags: ['resource']` and `tags: ['quota']` in `schema.yml`, you could run `dbt run --select tag:resource tag:quota` instead — much cleaner for large groups of models.

**Checkpoint:** All 6 models show `OK created sql view`

---

### Verify all 12 staging models

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource/dbt
dbt ls --select staging
```

**Checkpoint:** All 12 model names listed.

Verify in pgAdmin: `staging_silver` schema → Views → 12 views

Run tests on all staging models:

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource/dbt
dbt test --select staging
```

**Checkpoint:** All tests show `PASS`

Commit:

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource
git add dbt/models/staging/
git commit -m "add staging models and schema.yml"
```

---

## Step 5 — Run intermediate models

Before running, check what intermediate models depend on upstream:

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource/dbt
dbt ls --select +int_token_usage_minute
```

This shows `int_token_usage_minute` and all its upstream staging models. Useful to confirm the full dependency chain before running.

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource/dbt
dbt run --select intermediate
```

**Checkpoint:** Both models show `OK created incremental model` (first run) or `OK inserted X rows` (subsequent runs)

> **What is an incremental model?** On the first run dbt builds the full table. On every subsequent run it only processes new rows — rows that arrived since the last run. This is much faster for large tables.
>
> Both intermediate models use `delete+insert` strategy — on each run dbt deletes the last 7 days and reinserts fresh. This handles late-arriving data correctly.

If you change the SQL logic of an incremental model, the existing rows need to be recalculated. Use `--full-refresh` to drop and rebuild from scratch:

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource/dbt
# Full refresh one incremental model
dbt build --select int_token_usage_minute --full-refresh

# Full refresh all incremental models
dbt build --full-refresh
```

> Use `--no-compile` when you've already compiled and want to re-execute without recompiling — faster for data refreshes when no code has changed:
> ```bash
> dbt run --no-compile --select intermediate
> ```

Commit:

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource
git add dbt/models/intermediate/
git commit -m "add intermediate models"
```

---

## Step 6 — Run mart models

Check what downstream models depend on the intermediate layer before running:

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource/dbt
dbt ls --select int_revenue_daily+
```

This shows `int_revenue_daily` and all the mart models that depend on it downstream.

Also useful to see file paths if you need to find a specific model:

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource/dbt
dbt ls --select marts --output path
```

**Graph operator reference** — use these with `dbt ls` or `dbt run` to precisely control what runs:

| Syntax | Selects |
|---|---|
| `+model_name` | Model + all upstream ancestors |
| `model_name+` | Model + all downstream dependents |
| `+model_name+` | Model + all upstream + all downstream |
| `1+model_name+1` | Model + 1 level up + 1 level down |
| `@model_name` | Model + all descendants + all ancestors of descendants |

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource/dbt
dbt run --select marts
```

**Checkpoint:** All 10 models show `OK`. Verify in pgAdmin: `mart_gold` → Tables → 10 tables

Commit:

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource
git add dbt/models/marts/
git commit -m "add mart models"
```

---

## Step 7 — First prod run

This is the moment everything you have built moves from your personal schema into production. Up to now all runs have used `--target personal` (your default). This step runs against `--target prod` for the first time.

### What prod means

When you run `dbt build --target prod`, dbt reads the `prod` target from your `~/.dbt/profiles.yml`:

- Writes staging models to `prod_staging_silver`
- Writes mart models to `prod_mart_gold`
- Writes snapshots to `prod_snapshots`
- Writes seeds to `seeds` (shared, already there)

These are the schemas your Airflow DAG reads from and your Metabase dashboards will connect to.

### Run the full pipeline against prod

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource/dbt
dbt build --target prod
```

`dbt build` runs seed + snapshot + run + test in dependency order. Everything in one command.

**Checkpoint:** All models show `OK`. All tests show `PASS`.

### Simulate a test failure and retry

Before saving the prod manifest, let's intentionally break a test to see how `dbt retry` works. Open `seeds/seeds.yml` and add an invalid value to the `territory` accepted_values list:

```yaml
# Add 'INVALID_TERRITORY' to the values list temporarily
- accepted_values:
    arguments:
      values: ['US', 'North America', 'Europe', 'Asia Pacific',
               'Middle East', 'Africa', 'South America', 'China',
               'US GovCloud', 'INVALID_TERRITORY']
```

Wait — that won't cause a failure because we're adding a value, not removing one. Instead, remove one legitimate value:

```yaml
# Temporarily remove 'US GovCloud' from the list
- accepted_values:
    arguments:
      values: ['US', 'North America', 'Europe', 'Asia Pacific',
               'Middle East', 'Africa', 'South America', 'China']
               # 'US GovCloud' removed intentionally
```

The full `dbt build --target prod` will fail on the `accepted_values_region_mapping_territory` test and skip all downstream intermediates and marts. Fix it — restore `'US GovCloud'` to the accepted values. Then retry only what failed:

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource/dbt
dbt retry --target prod
```

`dbt retry` reads `target/run_results.json` from the last run, finds what failed and what was skipped, and reruns only those. The `--target prod` is required — without it dbt retries against your personal schema instead of prod. The 302 models that already passed are untouched.

**Checkpoint:** All models show `OK`. All tests show `PASS`.

### Verify prod data landed

Open pgAdmin at [localhost:5050](http://localhost:5050) → `btg-local` → `btg_resource_utilization`

| Schema | What to verify |
|---|---|
| `staging_silver` | 12 views |
| `mart_gold` | 10 tables with data |
| `snapshots` | 2 snapshot tables |
| `seeds` | `region_mapping` — 29 rows |

> Prod writes to clean schema names — no prefix. Your personal dev schemas use the `dbt_kanja_` prefix. This is controlled by `macros/generate_schema_name.sql`.

Run a quick row count to confirm:

```bash
docker exec postgres psql -U mds_user -d btg_resource_utilization -c "
SELECT 'staging_silver' AS schema, COUNT(*) FROM staging_silver.stg_customer_details
UNION ALL
SELECT 'mart_gold', COUNT(*) FROM mart_gold.customer_revenue_monthly_v1;"
```

### Save the prod manifest

The manifest is a snapshot of your project at this point in time — every model, every test, their compiled SQL hashes. dbt uses it in future runs to know what changed.

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource/dbt
mkdir -p prod-state
cp target/manifest.json prod-state/manifest.json
echo "prod-state/" >> .gitignore
```

> `prod-state/` goes in `.gitignore` — it is a local reference file, not code. It should never be committed. When you need it in CI, GitHub Actions downloads it from the artifact store (covered in Runbook 5).

### From now on — use state:modified+ for incremental runs

Now that prod exists and you have a manifest, you never need to run `dbt build --target prod` against all 131 models again. Instead:

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource/dbt
# Preview what changed vs prod manifest
dbt ls --select state:modified+ --state ./prod-state/

# Run only what changed and its downstream dependents
dbt build --select state:modified+ --state ./prod-state/ --target prod
```

If you change `stg_revenue_account_daily`, dbt rebuilds that model plus `int_revenue_daily` plus all 6 revenue marts that depend on it. Everything else is untouched.

After every successful prod run — update the manifest so it stays current:

```bash
cp target/manifest.json prod-state/manifest.json
```

---

## Step 8 — Run dbt test

Before running all tests, see what tests are defined across the project:

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource/dbt
dbt ls --resource-type test
```

This lists every test — generic and singular — so you know exactly what will run.

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource/dbt
# Run all tests
dbt test

# Run tests on one model
dbt test --select stg_customer_details

# Run only source tests
dbt test --select source:raw_bronze

# Run only generic tests
dbt test --select test_type:generic
```

**Checkpoint:** All tests show `PASS`

If a test fails — open the test file in `dbt/tests/` and run the SQL in pgAdmin to see which rows violated it.

Commit:

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource
git add dbt/tests/
git commit -m "add singular tests"
```

---

## Step 9 — Verify in pgAdmin

Open [localhost:5050](http://localhost:5050) → `btg-local` → `btg_resource_utilization`

| Schema | What to verify |
|---|---|
| `raw_bronze` | 12 tables with data |
| `seeds` | `region_mapping` — 29 rows |
| `snapshots` | 2 snapshot tables |
| `staging_silver` | 12 views + 2 incremental tables |
| `mart_gold` | 10 tables |

---

## Step 10 — CI simulation

This is what GitHub Actions runs on every Pull Request. Understanding it locally means CI almost always passes on the first try.

### Make a change and introduce an intentional error

> The prod manifest was saved in Step 7. If you skipped Step 7 — go back and run `dbt build --target prod` first before continuing here.

Open `stg_customer_details.sql` and add a comment at the top:

```sql
-- updated: reviewing customer segmentation logic
```

Also open `stg_revenue_account_daily.sql` and introduce a bad `ref()`:

```sql
-- Add this line (intentional bad ref):
left join {{ ref('stg_pricing_tiers') }} using (model_variant)
```

Save both files.

### Preview what changed

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource/dbt
dbt ls --select state:modified+ --state ./prod-state/
```

You see both `stg_customer_details` and `stg_revenue_account_daily` listed — plus any downstream dependents.

Also check for any brand new models that weren't in the prod manifest:

```bash
dbt ls --select state:new --state ./prod-state/
```

### Run the CI simulation — it fails

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource/dbt
dbt build --select state:modified+ state:new \
  --defer \
  --state ./prod-state/
```

> `--defer` — for any model you didn't select, read from prod instead of rebuilding it. Only your changed models get rebuilt.
> `state:modified+` — changed models plus all their downstream dependents.
> `state:new` — brand new models that didn't exist in prod manifest.

dbt fails immediately:

```
Compilation Error in model stg_revenue_account_daily
  'stg_pricing_tiers' was not found
```

`stg_customer_details` is skipped because it depends on the failing model's downstream. All downstream marts that depend on revenue are also skipped.

### Use result selectors to see what failed and what was skipped

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource/dbt
dbt ls --select result:error+ --state ./prod-state/
dbt ls --select result:skipped+ --state ./prod-state/
```

### Fix the error and retry only what failed

Remove the bad `ref()` from `stg_revenue_account_daily.sql`. Then instead of rerunning everything — use result selectors to retry only what errored and what was skipped:

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource/dbt
dbt build --select result:error+ result:skipped+ --state ./prod-state/
```

Or simply:

```bash
dbt retry
```

**Checkpoint:** All models show `OK`. All tests show `PASS`.

### Advanced build flags

Two useful flags when running CI simulations:

```bash
# --fail-fast: stop immediately on first failure instead of continuing
dbt build --select state:modified+ --fail-fast --state ./prod-state/

# --empty: build schema only with zero rows — fastest way to check SQL compiles
dbt build --select state:modified+ --empty --state ./prod-state/
```

### Update the prod manifest for next run

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource/dbt
cp target/manifest.json prod-state/manifest.json
```

---



## Generate and serve documentation

Now that the full pipeline is built, generate the dbt docs to visualize the full lineage — from bronze sources all the way through to mart tables:

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource/dbt
dbt docs generate
dbt docs serve port:8081
```

Open [localhost:8081](http://localhost:8081) in your browser — you will see:
- Full lineage graph from `raw_bronze` → staging → intermediate → marts
- All model descriptions, column descriptions, and tests
- Source freshness status

Press `Ctrl+C` to stop the docs server when done.

---

## Push to GitHub

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource
git push origin dev
```

---

## Next
Continue to **3b — dbt Advanced Patterns**.
