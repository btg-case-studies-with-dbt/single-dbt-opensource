# 3c — dbt Internals & Exam Prep

## Before you start
- Completed Runbooks 3a and 3b
- Not required for daily development — covers internals and exam preparation

---

## Section 1 — dbt Internals

### Dry run & Jinja resolution

A dry run executes the dbt parse phase without running any SQL. It validates all Jinja, `ref()`, and `source()` calls are valid and the DAG can be constructed.

```python
# .render() forces full Jinja resolution
compiled_node = context.compile_node(node)
rendered_sql = compiled_node.compiled_code.render()

# Ensures:
# — All ref() calls resolve to actual relation names
# — All source() calls validated against sources.yml
# — Full DAG built with correct dependencies
# — Jinja errors surface without touching the database
```

Simply running models sequentially does not force Jinja resolution — you must call `.render()` explicitly.

```bash
# Compile only — no database writes
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource/dbt
dbt compile --select stg_customer_details

# View compiled SQL
code target/compiled/resource_utilization/models/staging/stg_customer_details.sql
```

### Ephemeral models — CTEs that don't touch the database

```sql
-- models/staging/base_token_usage.sql
{{ config(materialized='ephemeral') }}

select
    request_id,
    account_id,
    model_variant,
    total_tokens
from {{ source('raw_bronze', 'inference_user_token_usage_proprietary') }}
where total_tokens > 0
```

What dbt actually sends to PostgreSQL when another model refs it:

```sql
with base_token_usage as (
    select request_id, account_id, model_variant, total_tokens
    from raw_bronze.inference_user_token_usage_proprietary
    where total_tokens > 0
)
select * from base_token_usage
```

| Use ephemeral when | Do NOT use ephemeral when |
|---|---|
| Logic shared across 2-3 models | More than 3-4 models reference it |
| Simple transformation — filter, rename | Logic is expensive — runs again for every model |
| Hide internal details from schema | You need to test the model directly |

Ephemeral models cannot be tested directly — no relation exists to test against.

Ephemeral + `access: public` is invalid — raises a parsing error:
```
ParseError: Model 'my_model' is ephemeral and cannot have access: public.
```

### dbt artifacts

| File | What it contains | When written |
|---|---|---|
| `manifest.json` | Full project graph — every node, config, SQL, dependencies | Every compile, run, build, test |
| `run_results.json` | Execution metadata — status, timing, rows affected | After every run, build, test |
| `catalog.json` | Database metadata — column names, types, row counts | Only on `dbt docs generate` |
| `sources.json` | Source freshness check results | Only on `dbt source freshness` |

Join key between `manifest.json` and `run_results.json`: **`unique_id`**
Format: `model.project_name.model_name`
Example: `model.resource_utilization.stg_customer_details`

### Materialization precedence — most specific wins

| Level | Where | Precedence |
|---|---|---|
| `config()` in model SQL file | Inside the `.sql` file | 1 — highest, always wins |
| `config:` in `schema.yml` | Model-level YAML | 2 |
| Folder-level in `dbt_project.yml` | Under `models:` section | 3 |
| Project-level in `dbt_project.yml` | Under project name | 4 |
| Package default | Package's own `dbt_project.yml` | 5 |
| dbt built-in default | dbt core | 6 — lowest |

Same precedence applies to all configs — schema, database, tags, grants, on_schema_change.

### Schema naming — generate_schema_name

```bash
# Default: {target.schema}_{custom_schema}
# personal target: schema = dbt_kanja, custom_schema = staging_silver
# result: dbt_kanja_staging_silver

# prod target: schema = prod
# result: prod_staging_silver
```

Override in `dbt/macros/generate_schema_name.sql`:

```sql
{%- macro generate_schema_name(custom_schema_name, node) -%}
    {%- set default_schema = target.schema -%}
    {%- if custom_schema_name is none -%}
        {{ default_schema }}
    {%- elif target.name == 'prod' -%}
        {{ custom_schema_name | trim }}
    {%- else -%}
        {{ default_schema }}_{{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro -%}
```

### CASE WHEN vs Jinja if — the precise distinction

| | CASE WHEN | `{% if %}` |
|---|---|---|
| Runs | In the database, row by row | At compile time on your machine |
| Use when | Decision depends on column values | Decision depends on `target.name`, `is_incremental()`, macro args |
| Access to row data | Yes | No |

### Debug flags and log levels

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource/dbt

# Debug output — shows compiled SQL and full error traces
dbt run --select stg_customer_details --log-level debug
dbt --debug run --select stg_customer_details

# Quiet — only warnings and errors
dbt run --log-level warn

# JSON format for log aggregation
dbt run --log-format json

# Check the log file — always written at debug level regardless of --log-level
cat logs/dbt.log | tail -50

# Find compiled SQL for a failing model
cat target/compiled/resource_utilization/models/staging/stg_customer_details.sql

# Find run result for a specific model
cat target/run_results.json | python3 -m json.tool | grep -A 10 "stg_customer_details"
```

Three-step debugging workflow:
1. Read the terminal error — compilation error or database error?
2. Find the compiled SQL in `target/compiled/` — paste into pgAdmin and run directly
3. If still unclear — run with `--debug` for full connection trace

---

## Section 2 — Jinja Reference

### Variables

```jinja
{% set x = value %}          {# assign #}
{{ variable }}               {# output #}
{# comment #}                {# stripped at compile time #}
```

### Control flow

```jinja
{% if target.name == 'prod' %}
    WHERE date >= '2020-01-01'
{% elif target.name == 'dev' %}
    WHERE date >= CURRENT_DATE - 30
{% else %}
    WHERE date >= CURRENT_DATE - 7
{% endif %}

{% for col in ['a', 'b', 'c'] %}
    sum({{ col }}) as total_{{ col }}{{ "," if not loop.last }}
{% endfor %}
```

### Loop special variables

| Variable | What it is |
|---|---|
| `loop.first` | True on first iteration |
| `loop.last` | True on last iteration |
| `loop.index` | Current iteration, starting at 1 |
| `loop.index0` | Current iteration, starting at 0 |

### Filters

| Filter | What it does | Example |
|---|---|---|
| `\| upper` | Uppercase | `{{ 'prod' \| upper }}` → PROD |
| `\| lower` | Lowercase | `{{ target.name \| lower }}` |
| `\| join(', ')` | Join list to string | `{{ ['a','b'] \| join(', ') }}` → a, b |
| `\| default('fallback')` | Fallback if undefined | `{{ var('schema') \| default('dev') }}` |
| `\| length` | Length | `{{ cols \| length }}` |
| `\| replace('a','b')` | Replace | `{{ schema \| replace('prod','dev') }}` |

---

## Section 3 — dbt Functions Reference

### Model references

| Function | What it does | Example |
|---|---|---|
| `ref('model')` | Reference a dbt model, record dependency | `FROM {{ ref('stg_customer_details') }}` |
| `ref('model', version=2)` | Reference a specific version | `FROM {{ ref('model_revenue_monthly', version=1) }}` |
| `source('schema', 'table')` | Reference a raw table | `FROM {{ source('raw_bronze', 'customer_details') }}` |

### Model context

| Variable | What it does | Example |
|---|---|---|
| `this` | Fully qualified name of current model | `SELECT max(loaded_at) FROM {{ this }}` |
| `this.schema` | Schema of current model | `{{ this.schema }}` → `prod_mart_gold` |
| `this.name` | Table name of current model | `{{ this.name }}` → `model_revenue_monthly` |

### Build context

| Variable | What it does | Example |
|---|---|---|
| `is_incremental()` | True on incremental run, false on first/full-refresh | `{% if is_incremental() %}` |
| `execute` | True when dbt is actually running (not parsing) | `{% if execute %} {% set r = run_query(...) %} {% endif %}` |
| `target.name` | Current target name | `{% if target.name == 'prod' %}` |
| `target.schema` | Schema prefix for current target | `{{ target.schema }}` → `dbt_kanja` |
| `target.type` | Database adapter type | `{{ target.type }}` → `postgres` |
| `target.threads` | Thread count | `{{ target.threads }}` |

### Variables and environment

| Function | What it does | Gotcha |
|---|---|---|
| `var('name')` | Reads a project variable | Fails if not set and no default |
| `env_var('NAME')` | Reads an environment variable — exact, case-sensitive | Must match exactly — dbt does not add/strip prefixes |
| `run_query('SQL')` | Executes SQL at compile time | Must be guarded with `{% if execute %}` |

### Documentation and debugging

| Function | What it does | Example |
|---|---|---|
| `doc('block_name')` | References a description block in a `.md` file | `description: "{{ doc('model_revenue_monthly') }}"` |
| `log('msg', info=true)` | Prints to dbt logs during compile | `{{ log("target: " ~ target.name, info=true) }}` |
| `exceptions.raise_compiler_error('msg')` | Fails compilation with custom message | `{{ exceptions.raise_compiler_error("col required") }}` |

### YAML quoting rules

```yaml
# Must quote — contains special characters
- name: net_revenue
  description: "Revenue: net after discounts"         # colon requires quotes

- name: model_revenue_monthly
  description: "{{ doc('model_revenue_monthly') }}"   # curly braces require quotes

# No quotes needed — plain string
- name: account_id
  description: Unique identifier for each customer account
```

### WARN_ERROR_OPTIONS

```yaml
# dbt_project.yml — promote specific warnings to errors
config:
  warn_error_options:
    include:
      - DeprecatedModel
      - DeprecatedMacro

# Or promote ALL warnings to errors
warn_error: true
```

```bash
# CLI equivalent
dbt build --warn-error
dbt build --warn-error-options '{"include": ["DeprecatedModel"]}'
```

---

## Section 4 — Key Exam Topics

| Topic | Correct answer | Common trap |
|---|---|---|
| Join key between `manifest.json` and `run_results.json` | `unique_id` | `relation_name`, `thread_id` |
| Schema naming with `+schema: finance` | `{target.schema}_finance` | Just `finance` |
| Materializations that do NOT support contracts | Ephemeral | Incremental (it does) |
| Indirect selection mode for CI | Buildable | Eager (default — runs tests even with missing deps) |
| Select all generic tests | `--select test_type:generic` | `test_name:generic`, `tag:generic_test` |
| Disable one source table only | `enabled: false` on the table in `sources.yml` | `+enabled: false` at source level (disables all tables) |
| Seed config for specific database | `+database:` scoped under `seeds: project: seed_name:` | Putting it under `models:` or at `seeds:` root |
| Revoking a grant via grants config | Remove grantee from list — dbt issues REVOKE automatically | Writing explicit REVOKE commands |
| `+schema: null` in tests section | Stores failures in the default profile schema | "Dynamically generated schema" |
| Properties vs configurations | Properties = what it is (descriptions, tests). Configs = how dbt builds it. | Using them interchangeably |
| `env_var()` with `DBT_` prefix | Must match exactly — dbt does not add/strip prefix | Thinking dbt maps `MY_VAR` to `DBT_MY_VAR` |
| Docs block naming rules | Alphanumeric + underscore only, cannot start with digit | Using hyphens or spaces |
| Dry run Jinja resolution | Call `.render()` on compiled node | Running models sequentially |
| Path-based selection | `--select 'models/finance'` | `--select tag:finance` |
| `state:modified` includes `state:new` | False — new models must be explicitly selected | Assuming `state:modified` catches new models |
| Ephemeral + `access: public` | Raises a parsing error | Warning only, or silently downgrades |
| `deprecation_date` alone fails the run | False — only emits a warning | Must also set `WARN_ERROR_OPTIONS` |
| Exposures auto-generation | Via supported BI integrations only | Running `dbt build` or SQL scripts |
| `config()` in model SQL | Highest specificity — always wins | Folder-level `dbt_project.yml` wins |
| `dbt debug` runs models | False — tests connection and config only | Using `dbt debug` to see SQL execution |

---

## Troubleshooting

**`env_var()` fails with "is not set"**
```bash
# Check exact name in shell
env | grep DBT
# Must match exactly — case-sensitive
# Wrong: {{ env_var('MY_SECRET') }} when shell has DBT_MY_SECRET=abc
# Right: {{ env_var('DBT_MY_SECRET') }}
```

**`run_query()` fails at parse time**
```jinja
{# Missing {% if execute %} guard #}
{% if execute %}
  {% set results = run_query("SELECT DISTINCT model_variant FROM raw_bronze.config_model_dimensions") %}
{% endif %}
```

**Model contract fails with "type mismatch"**
Fix the SQL or fix the YAML. If using `alias_types: false`, the type string must exactly match what PostgreSQL expects.

---

## Next
Continue to **Runbook 4 — Airflow** to automate the pipeline on a daily schedule.
