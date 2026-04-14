# 3d — dbt Advanced Patterns II

## Before you start
- Completed Runbooks 3a, 3b, 3c
- Full pipeline running in personal schema, prod build clean

---

## Section 1 — Unit Tests

Unit tests check transformation logic using mock data — no database needed.

```yaml
# models/staging/staging_schema.yml
unit_tests:
  - name: test_segment_null_handling
    description: "NULL segments coalesced to Unknown"
    model: stg_customer_details
    given:
      - input: source('raw_bronze', 'customer_details')
        rows:
          - {account_id: 'A1', segment: null,       company_name: 'Acme'}
          - {account_id: 'A2', segment: '',          company_name: 'Beta'}
          - {account_id: 'A3', segment: 'Strategic', company_name: 'Gamma'}
    expect:
      rows:
        - {account_id: 'A1', segment: 'Unknown'}
        - {account_id: 'A2', segment: 'Unknown'}
        - {account_id: 'A3', segment: 'Strategic'}
```

Mock `is_incremental()` in unit tests — it always returns `False` by default, which skips the incremental filter. Override it:

```yaml
unit_tests:
  - name: test_incremental_filter_handles_empty_table
    model: int_revenue_daily
    overrides:
      is_incremental: true     # force is_incremental() to return True
    given:
      - input: ref('stg_revenue_account_daily')
        rows:
          - {account_id: 'A1', revenue_date: '2026-03-15', net_revenue: 500}
          - {account_id: 'A2', revenue_date: '2026-03-10', net_revenue: 300}
      - input: this             # mock the existing incremental table
        rows:
          - {revenue_date: '2026-03-14'}   # latest existing row
    expect:
      rows:
        - {account_id: 'A1', revenue_date: '2026-03-15'}
        # A2 (2026-03-10) excluded — before max(revenue_date)
```

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource/dbt

dbt test --select test_type:unit
dbt test --select stg_customer_details,test_type:unit
dbt build --select stg_customer_details   # runs unit + data tests
```

| Can do | Cannot do |
|---|---|
| Test CASE WHEN, null handling, type casting | Test against real data volumes |
| Test JOIN logic with controlled rows | Replace all inputs — only overridden inputs use mock data |
| Run without database writes | Test ephemeral models directly |
| Mock `is_incremental()` via `overrides:` | Test post-hooks or grants |

---

## Section 2 — Advanced Test Config

```yaml
# error_if / warn_if — threshold-based severity
- not_null:
    error_if: ">10"   # error only if more than 10 rows fail
    warn_if: ">0"     # warn if 1–10 rows fail

# limit — cap failing rows returned
- not_null:
    limit: 100        # return first 100 failing rows only

# store_failures — persist failing rows to the database
- not_null:
    store_failures: true
    # Creates: dbt_test__audit.stg_customer_details_not_null_company_name
    # Query it in pgAdmin to inspect which rows failed

# store_failures globally in dbt_project.yml
tests:
  resource_utilization:
    +store_failures: true
    +schema: audit    # write failure tables to audit schema
```

**Test name property — prevent naming collisions:**

When the same test type is applied twice to the same column with different configs, dbt auto-generates identical names — causing a compilation error. Fix with `name`:

```yaml
- name: segment
  tests:
    - accepted_values:
        name: segment_warn_unexpected     # unique identifier
        values: ['Strategic', 'Commercial']
        config:
          severity: warn
    - accepted_values:
        name: segment_error_invalid       # unique identifier
        values: ['Strategic', 'Commercial', 'Unknown']
        config:
          severity: error
```

---

## Section 3 — dbt Mesh & Namespaces

Every dbt project has a unique name in `dbt_project.yml` — that name is the namespace. Cross-project `ref()` is called dbt Mesh.

```yaml
# platform/dbt/dbt_project.yml
name: 'platform'   # namespace

# product_a/dbt/dbt_project.yml
name: 'product_a'  # namespace
```

Cross-project `ref()`:

```sql
-- In product_a, referencing a model from platform
select * from {{ ref('platform', 'model_revenue_monthly') }}
-- resolves to: prod_mart_gold.model_revenue_monthly
```

Three requirements for cross-project `ref()`:

```sql
-- 1. Model must be public in platform project
{{ config(materialized='table', access='public') }}
```

```yaml
# 2. Consuming project declares dependency in dependencies.yml
projects:
  - name: platform

# 3. Platform manifest must be available to product_a at parse time
```

Three-project architecture for this project (Runbook 7):

| Project | Namespace | Access |
|---|---|---|
| Platform | `platform` | Mart models = `public` |
| Revenue | `revenue` | All models = `protected` |
| Token Usage | `token_usage` | All models = `protected` |

`protected` models cannot be `ref()`'d across project boundaries. Only `public` models cross projects.

---

## Section 4 — packages.yml vs dependencies.yml

| | `packages.yml` | `dependencies.yml` |
|---|---|---|
| Purpose | Install dbt packages | Declare cross-project dbt Mesh dependencies |
| Private packages | ✅ Git URL + token injection | ❌ Not supported |
| Jinja rendering | ✅ Supported | ❌ Static only |
| Run command | `dbt deps` | Resolved at parse time |

```yaml
# packages.yml — supports Jinja for private packages
packages:
  - package: dbt-labs/dbt_utils
    version: [">=1.0.0", "<2.0.0"]
  - git: "https://{{env_var('DBT_GIT_TOKEN')}}@github.com/myorg/private-pkg.git"
    revision: main

# dependencies.yml — static only, no Jinja
projects:
  - name: platform
```

`dependencies.yml` does not support Jinja — private packages requiring token injection must go in `packages.yml`.

---

## Section 5 — packages-install-path

In a monorepo with multiple dbt projects, the default `dbt_packages/` folder causes version conflicts. Each project needs its own install path:

```yaml
# platform/dbt/dbt_project.yml
packages-install-path: dbt_packages_platform

# revenue/dbt/dbt_project.yml
packages-install-path: dbt_packages_revenue
```

Update `.gitignore` to match:

```bash
echo "dbt_packages_platform/" >> .gitignore
echo "dbt_packages_revenue/" >> .gitignore
```

---

## Section 6 — Alias Config

By default dbt uses the filename as the database object name. `alias` overrides this:

```sql
-- models/marts/revenue/model_revenue_monthly.sql
{{ config(
    materialized='table',
    alias='revenue_monthly'    -- database table name
    -- ref() still uses: ref('model_revenue_monthly')
) }}
```

`ref()` always uses the filename — never the alias. Source alias maps a logical name to an actual table name:

```yaml
# sources.yml
sources:
  - name: raw_bronze
    tables:
      - name: customer_data           # logical name in source() calls
        identifier: customer_details  # actual table name in database
```

Database and schema alias:

```sql
{{ config(
    database='analytics',
    schema='finance',
    alias='monthly_revenue'
) }}
-- Result: analytics.finance.monthly_revenue
```

---

## Section 7 — dbt_utils & dispatch

Most useful `dbt_utils` macros:

| Macro | What it does |
|---|---|
| `generate_surrogate_key(['account_id', 'revenue_date'])` | Hashed surrogate key from columns |
| `date_spine()` | Table of dates between two dates |
| `pivot()` | Pivot rows to columns dynamically |
| `get_column_values()` | Distinct values from a column at compile time |
| `star(from=ref('stg_customer_details'), except=['loaded_at'])` | SELECT * except specific columns |

Dispatch makes macros adapter-aware — same call produces different SQL on PostgreSQL vs Snowflake vs BigQuery. Configure in `dbt_project.yml`:

```yaml
dispatch:
  - macro_namespace: dbt_utils
    search_order:
      - resource_utilization   # check project macros first
      - dbt_utils              # fall back to package
```

---

## Section 8 — audit_helper

Compares two versions of a model — your new version vs current production. Standard pre-merge validation tool.

```yaml
# packages.yml
packages:
  - package: dbt-labs/audit_helper
    version: [">=0.9.0", "<1.0.0"]
```

```sql
-- analyses/compare_revenue_models.sql
{{ audit_helper.compare_relations(
    a_relation=ref('model_revenue_monthly'),         -- new version
    b_relation=api.Relation.create(
        database='btg_resource_utilization',
        schema='prod_mart_gold',
        identifier='model_revenue_monthly'
    ),                                               -- current prod
    primary_key='model_variant || month_start_date::text'
) }}
```

Pre-merge workflow:
1. `dbt run --select model_revenue_monthly` — build new version in personal schema
2. Run `compare_relations` — 100% match → safe to merge, differences → investigate

| Macro | When to use |
|---|---|
| `compare_relations` | Full row-by-row validation before merging a refactor |
| `compare_column_values` | Find which specific columns changed |
| `compare_all_columns` | Quick health check summary |

---

## Section 9 — dbt clone vs defer

Both solve the same problem: running CI without rebuilding every upstream dependency. Different mechanisms:

| | `--defer` | `dbt clone` |
|---|---|---|
| Data movement | None — reads prod directly | None on Snowflake/BQ (zero-copy). Views on Postgres. |
| Upstream models in CI schema | No — stay in prod | Yes — clones appear in CI schema |
| Isolation | Lower | Higher |
| PostgreSQL support | Full | Creates views (not zero-copy) |
| Best for | Simple setups, PostgreSQL | Snowflake/BQ, strict isolation |

This project uses `--defer` — PostgreSQL does not support zero-copy clones.

```bash
# Clone all prod models into CI schema (Snowflake/BQ)
dbt clone --target ci --state ./prod-state/
dbt build --select state:modified+ --target ci

# vs defer (PostgreSQL — this project)
dbt build --select state:modified+ --defer --state ./prod-state/
```

---

## Section 10 — Incremental Models in CI

`is_incremental()` always returns `False` in CI — the CI schema is empty on every PR, so the table never pre-exists. CI only ever tests the full-refresh code path.

**The NULL lookback window problem:**

```sql
-- int_revenue_daily.sql — common bug
{% if is_incremental() %}
where revenue_date >= (select max(revenue_date) from {{ this }})
{% endif %}
-- If table is empty: max(revenue_date) = NULL
-- WHERE revenue_date > NULL → zero rows loaded
```

Fix with COALESCE:

```sql
{% if is_incremental() %}
where revenue_date >= (
    select coalesce(
        max(revenue_date),
        '2020-01-01'::date    -- fallback: load all history if table is empty
    )
    from {{ this }}
)
{% endif %}
```

**Two-run CI — validate the incremental path:**

```yaml
# .github/workflows/dbt_ci.yml — add after existing build step
- name: Run 2 — incremental run (validates is_incremental path)
  run: |
    docker compose -f resource-utilization/docker-compose.yml \
      run --rm airflow-scheduler bash -c \
      "cd /opt/airflow/dbt && /usr/local/airflow/dbt_venv/bin/dbt build \
      --select state:modified+ \
      --target ci \
      --profiles-dir ."
    # Table now exists from Run 1 — is_incremental() returns True
    # The {% if is_incremental() %} block executes for the first time
```

**Detect changed incremental models — auto-add `--full-refresh`:**

```yaml
- name: Check if incremental models changed
  id: check_incremental
  run: |
    CHANGED=$(dbt ls --select state:modified,config.materialized:incremental \
      --state ./prod-state/ --output name 2>/dev/null)
    if [ -n "$CHANGED" ]; then
      echo "full_refresh=true" >> $GITHUB_OUTPUT
    fi

- name: Run CI
  run: |
    ARGS="--select state:modified+ --defer --state ./prod-state/ --target ci"
    if [ "${{ steps.check_incremental.outputs.full_refresh }}" == "true" ]; then
      ARGS="$ARGS --full-refresh"
    fi
    dbt build $ARGS
```

**Limit data volume in CI:**

```sql
-- Pattern 1 — target-based date filter
select * from {{ source('raw_bronze', 'inference_user_token_usage_proprietary') }}
{% if target.name != 'prod' %}
where loaded_at >= current_date - interval '30 days'
{% endif %}
```

---

## Section 11 — Advanced Selectors

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource/dbt

# group: selector — select by group membership
dbt build --select group:finance
dbt build --select group:finance,state:modified   # finance AND modified
dbt build --select group:finance group:revenue    # finance OR revenue

# Set operators
dbt build --select tag:revenue tag:finance        # OR (space)
dbt build --select tag:revenue,state:modified     # AND (comma)
dbt build --select staging --exclude stg_config_model_dimensions

# Graph operators
dbt build --select +model_revenue_monthly          # model + all upstream
dbt build --select model_revenue_monthly+          # model + all downstream
dbt build --select +model_revenue_monthly+         # model + upstream + downstream
dbt build --select 1+model_revenue_monthly+1       # 1 level each direction
dbt build --select @int_revenue_daily              # model + all ancestors + their tests

# Wildcard
dbt build --select "stg_*"
dbt ls --select path:models/marts/revenue/model_*

# Output formats for dbt ls
dbt ls --select staging --output json
dbt ls --select staging --output path
dbt ls --select staging --output name
```

**Predefined selector files:**

```yaml
# selectors.yml
selectors:
  - name: nightly_build
    definition:
      union:
        - method: tag
          value: daily
        - method: state
          value: modified
          children: true

  - name: ci_modified
    definition:
      method: state
      value: modified
      children: true
```

```bash
dbt build --selector nightly_build
dbt build --selector ci_modified
```

---

## Section 12 — Tests on Sources

Run tests directly on raw bronze tables before any transformation:

```yaml
# models/staging/sources.yml
sources:
  - name: raw_bronze
    tables:
      - name: customer_details
        columns:
          - name: account_id
            tests:
              - not_null
              - unique           # catches duplicates before staging
          - name: segment
            tests:
              - accepted_values:
                  arguments:
                    values: ['Strategic', 'Commercial', 'SMB']
                  # new segment appears → fails before silently creating new groups in marts

      - name: inference_user_token_usage_proprietary
        columns:
          - name: request_id
            tests:
              - not_null
              - unique           # each API request exactly once in source
```

```bash
dbt test --select source:raw_bronze
dbt test --select source:raw_bronze.customer_details

# Fail-fast pattern — test sources before building models
dbt test --select source:raw_bronze && dbt build
```

---

## Section 13 — Grants

**Grant + prefix — merge vs replace:**

Without `+` prefix, resource-level grants **replace** project-level grants entirely:

```yaml
# dbt_project.yml — project-level
models:
  resource_utilization:
    marts:
      +grants:
        select: ['analytics_engineer', 'business_user']

# schema.yml — WITHOUT + prefix (replaces project-level)
- name: model_revenue_monthly
  config:
    grants:
      select: ['finance_team']   # analytics_engineer and business_user lose access
```

With `+` prefix, grants **merge**:

```yaml
# schema.yml — WITH + prefix (merges with project-level)
- name: model_revenue_monthly
  config:
    grants:
      "+select": ['finance_team']   # all three roles have access
```

**Snowflake vs PostgreSQL grant differences:**

| | PostgreSQL | Snowflake |
|---|---|---|
| Grant target | Roles or users | Roles only |
| Future grants | Not supported | Supported |
| Schema-level | `GRANT USAGE ON SCHEMA` | `GRANT USAGE ON DATABASE` + `GRANT USAGE ON SCHEMA` |

`copy_grants: true` is Snowflake-only — silently ignored on PostgreSQL.

---

## Section 14 — Contracts: Subtleties

**All output columns must be declared** — if a model produces 15 columns and `schema.yml` declares 14, the contract fails.

**Numeric precision** — contracts validate type but not precision by default:

```yaml
# Without precision — accepts any numeric
- name: net_revenue
  data_type: numeric

# With precision — enforces exact type
- name: net_revenue
  data_type: numeric(18, 4)    # 18 digits, 4 decimal places
```

**Platform constraint enforcement:**

| Platform | `not_null` enforced? | `primary_key` enforced? |
|---|---|---|
| PostgreSQL | ✅ DDL level | ✅ DDL level |
| Snowflake | ✅ Yes | ⚠ Informational only |
| BigQuery | ⚠ Informational only | ⚠ Informational only |

---

## Section 15 — Parallel-safe Commands

| Command | Safe to run in parallel? |
|---|---|
| `dbt docs generate` | ✅ Yes |
| `dbt docs serve` | ✅ Yes |
| `dbt clean` | ✅ Yes |
| `dbt ls` | ✅ Yes |
| `dbt run` | ❌ No |
| `dbt build` | ❌ No |
| `dbt test` | ❌ No |
| `dbt snapshot` | ❌ No |

`dbt docs generate` + `dbt clean` is the most commonly parallel-safe combination.

---

## Section 16 — Insert Overwrite Strategy

Replaces entire partitions — more efficient than `delete+insert` for date-partitioned data with frequent corrections. Not supported on PostgreSQL — use `delete+insert` with a lookback window instead.

```sql
-- BigQuery / Databricks only
{{ config(
    materialized='incremental',
    incremental_strategy='insert_overwrite',
    partition_by={
        'field': 'event_date',
        'data_type': 'date',
        'granularity': 'day'
    }
) }}

select
    account_id,
    event_date,
    sum(total_tokens) as total_tokens
from {{ ref('stg_token_usage_proprietary') }}
{% if is_incremental() %}
where event_date >= date_sub(current_date, interval 3 day)
{% endif %}
```

| Strategy | Unit of replacement | Best for |
|---|---|---|
| `delete+insert` | Rows matching `unique_key` | Late-arriving row corrections |
| `merge` | Rows matching `unique_key` (upsert) | Targeted upserts |
| `append` | No replacement | Immutable append-only streams |
| `insert_overwrite` | Entire partition | Daily partitioned data |

---

## Section 17 — Performant SQL & Clean DAG Design

**CTEs over subqueries — always:**

```sql
-- Every dbt model is a CTE chain. Each model in the DAG = one named CTE in compiled SQL.
with recent_usage as (
    select account_id, sum(total_tokens) as total_tokens
    from raw_bronze.inference_user_token_usage_proprietary
    where loaded_at >= current_date - 30
    group by account_id
),
heavy_users as (
    select account_id, total_tokens
    from recent_usage
    where total_tokens > 10000
)
select * from heavy_users
```

**Push filters early — before joins:**

```sql
with recent_usage as (
    select account_id, total_tokens
    from raw_bronze.inference_user_token_usage_proprietary
    where loaded_at >= current_date - 30   -- filter BEFORE join
),
active_customers as (
    select account_id, segment
    from raw_bronze.customer_details
    where is_active = true
)
select c.account_id, c.segment, u.total_tokens
from recent_usage u
join active_customers c on u.account_id = c.account_id
```

**Clean DAG rules:**

| Rule | Violation |
|---|---|
| Staging models are 1:1 with source tables | Staging model joining two bronze tables |
| No `source()` calls in marts | `FROM {{ source('raw_bronze', ...) }}` in a mart model |
| Shared logic goes in intermediate | Same GROUP BY duplicated in two mart models |
| No forward references | Staging model `ref()`-ing a mart |

```bash
# dbt_project_evaluator — already in packages.yml — flags violations automatically
dbt build --select package:dbt_project_evaluator
```

---

## Section 18 — Exposures: +enabled

```yaml
# dbt_project.yml — disable all exposures project-wide
exposures:
  +enabled: false

# Individual exposure YAML — disable one exposure only
exposures:
  - name: revenue_dashboard
    enabled: false   # no + prefix for individual exposures
```

```bash
# Select models feeding a specific exposure
dbt build --select +exposure:revenue_dashboard

# Check source freshness for sources feeding an exposure
dbt source freshness --select +exposure:revenue_dashboard
```

`maturity` (low/medium/high) is metadata only — has no effect on whether an exposure is enabled.

---

## Troubleshooting

**Unit test fails but data test passes:**
Unit tests validate transformation logic with mock data. Data tests validate real data. Both can be correct simultaneously — a logic bug may only manifest with specific input combinations not present in production data yet.

**Two-run CI — second run still shows `is_incremental() = False`:**
The incremental model's table was not created in Run 1 — likely because it was excluded from `state:modified+` selection. Add the model explicitly: `dbt build --select int_revenue_daily --target ci`.

**`audit_helper.compare_relations` shows differences:**
Inspect which rows differ:
```bash
dbt run-operation audit_helper.compare_column_values \
  --args '{"a_relation": "ref(\"model_revenue_monthly\")", "b_relation": "...", "primary_key": "..."}'
```

---

## Final run sequence

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource/dbt

# 1. Validate
dbt compile --no-partial-parse

# 2. Build local
dbt build --target personal

# 3. Build prod
dbt build --target prod

# 4. Commit and push
cd ~/Documents/btg-case-studies-with-dbt
git add .
git commit -m "feat: unit tests, dbt Mesh prep, incremental CI fixes"
git push origin dev
```

---

## Next
Continue to **Runbook 4 — Airflow** to automate the pipeline on a daily schedule.
