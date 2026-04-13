# 3b — dbt Advanced Patterns

## Before you start
- Completed Runbook 3a — full pipeline running, all tests passing in personal schema

---

## Section 1 — Advanced Tests

### Singular tests — custom SQL for specific business rules

A singular test is a `.sql` file in `dbt/tests/`. Zero rows = pass. Any rows = fail.

```sql
-- dbt/tests/test_revenue_always_positive.sql
select
    account_id,
    revenue_date,
    net_revenue,
    'Negative revenue detected' as issue
from {{ ref('int_revenue_daily') }}
where total_gross_revenue < 0
   or net_revenue < 0
```

Run by test type:

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource/dbt
dbt test --select test_type:singular   # files in dbt/tests/
dbt test --select test_type:generic    # macros named test_<name> in dbt/macros/ + YAML
dbt test --select test_type:unit       # unit_tests: blocks in schema.yml
dbt test                               # runs ALL three types

dbt test --select test_type:singular --no-partial-parse
# force full reparse if schema changes are not picked up — dbt caches parsed state
```

dbt infers test type purely from location and structure — no explicit declaration needed:
- `dbt/tests/*.sql` → singular
- `dbt/macros/test_<name>.sql` + YAML → generic
- `unit_tests:` block in `schema.yml` → unit

To run a specific singular test by name:
```bash
dbt test --select test_revenue_always_positive   # filename without .sql
```

### Custom generic tests — reusable test logic

Write once in `dbt/macros/`, apply to any column in any model:

```sql
-- dbt/macros/test_is_positive.sql
{% test is_positive(model, column_name) %}
select {{ column_name }}
from {{ model }}
where {{ column_name }} is not null
  and {{ column_name }} <= 0
{% endtest %}
```

Apply in `schema.yml`:

```yaml
models:
  - name: int_revenue_daily
    columns:
      - name: net_revenue
        tests:
          - not_null
          - is_positive    # custom generic test
```

### expression_is_true — cross-column validation

```yaml
models:
  - name: int_token_usage_minute
    tests:
      - dbt_utils.expression_is_true:
          arguments:
            expression: "total_tokens >= input_tokens + output_tokens + cache_read_tokens + cache_write_tokens"
          config:
            severity: warn    # warn not error — rounding differences are possible
      - dbt_utils.expression_is_true:
          arguments:
            expression: "net_revenue <= gross_revenue"
```

`is_positive` as a custom generic test is redundant if `dbt_utils` is installed — `expression_is_true` covers it and handles cross-column conditions:

```yaml
# single column — replaces is_positive
- dbt_utils.expression_is_true:
    arguments:
      expression: "net_revenue >= 0"

# cross-column — is_positive cannot do this
- dbt_utils.expression_is_true:
    arguments:
      expression: "net_revenue <= gross_revenue and gross_revenue >= 0"
```

### Test severity — default and override

```sql
-- macros/test_is_positive.sql
{% test is_positive(model, column_name) %}
    {{ config(severity='warn') }}    -- default warn, overridable
    select {{ column_name }}
    from {{ model }}
    where {{ column_name }} is not null and {{ column_name }} <= 0
{% endtest %}
```

```yaml
columns:
  - name: net_revenue
    tests:
      - is_positive             # uses default warn
  - name: gross_revenue
    tests:
      - is_positive:
          config:
            severity: error     # override to error
```

### Tag inheritance — which resources pass tags to tests

| Resource type | Tags inherited by tests? |
|---|---|
| Columns | ✅ Yes |
| Sources | ✅ Yes |
| Source tables | ✅ Yes |
| Models | ❌ No |
| Seeds | ❌ No |
| Snapshots | ❌ No |

```yaml
# Tag at column level so tests inherit it
models:
  - name: stg_customer_details
    columns:
      - name: account_id
        tags: ['pii', 'critical']    # tests on this column inherit these tags
        tests:
          - not_null                 # inherits pii and critical
          - unique                   # inherits pii and critical
```

### Choosing the right test type

| | Generic test | Unit test | Singular test |
|---|---|---|---|
| Validates | Column-level constraints | Transformation logic | Business rules across dataset |
| Input | Real data | Mock data in YAML | Real data |
| Scope | One column | One model's logic | Can span multiple models/columns |
| Written in | Macro + YAML | YAML | Pure SQL |
| Example | `not_null`, `is_positive` | net_revenue = gross − discount | Revenue exists without matching customer |
| Requires DB | Yes | No | Yes |

**Ask before writing:**
- Will this logic ever apply to another column or model? → generic test
- Is this checking that a calculation is correct? → unit test
- Is this a dataset-level business rule requiring domain knowledge? → singular test

A good singular test almost always involves a join, a temporal relationship, or a cross-model constraint specific enough that parameterizing it adds no value. Before writing a custom generic test, check if `dbt_utils` or `dbt_expectations` already covers it.

### Data tests vs unit tests

| | Data tests | Unit tests |
|---|---|---|
| Validates | Dataset correctness — real data | Transformation logic — mock data |
| Input | Real rows in database | Mock rows defined in `schema.yml` |
| Catches | Bad production data | Bugs in transformation logic |
| Requires DB | Yes | No |

Unit tests are the only test type that is logic-focused and data-independent. Given the same mock input, the output must always be identical — if transformation logic breaks, the number changes and the test catches it before touching real data.

---

## Section 2 — Macros

### Macro pattern

```sql
-- dbt/macros/add_prior_period_metrics.sql
{% macro add_prior_period_metrics(metrics, partition_cols, date_col, period_type='day') %}
{% for metric in metrics %}
    {{ safe_prior_period(metric, partition_cols, date_col, period_type) }}
        as prior_{{ period_type }}_{{ metric.split('.')[-1] }}
    {{ "," if not loop.last else "" }}
{% endfor %}
{% endmacro %}
```

### Exposures — declare downstream consumers

```yaml
# models/exposures.yml
version: 2
exposures:
  - name: revenue_dashboard
    type: dashboard
    maturity: high
    url: http://localhost:3000/dashboard/1
    description: "Monthly and YTD revenue by model and customer segment"
    depends_on:
      - ref('model_revenue_monthly')
      - ref('customer_revenue_monthly')
    owner:
      name: Data Team
      email: data@company.com
```

Generate and view docs with lineage — as introduced in 3a, run from inside the `dbt/` folder:

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource/dbt
dbt docs generate && dbt docs serve
```

> Exposures appear in the lineage graph as orange nodes downstream of your mart models. This is the main reason to define them — without an exposure, Metabase dashboards are invisible in the dbt docs lineage.

### doc() — descriptions in .md files

Store shared descriptions in `.md` files under `models/` — dbt scans the entire `models/` directory for `{% docs %}` blocks:

```markdown
<!-- dbt/models/_docs.md -->
{% docs model_variant %}
The specific Claude model version handling the request.
Examples: claude-3-opus, claude-3-sonnet, claude-3-haiku.

Sourced from the raw API request log and joined to dim_model_limits
for context window and pricing metadata. Null values indicate requests
where model routing failed.
{% enddocs %}
```

Reference in any schema file:

```yaml
- name: model_variant
  description: "{{ doc('model_variant') }}"
```

**Location rules:**
- Any `.md` file anywhere under `models/` is valid — dbt finds them all
- Use a leading underscore by convention: `_docs.md` sorts to the top in VS Code and signals "reference file, not a model"
- One file at `models/_docs.md` is enough for shared column definitions

**When to use `doc()` vs inline description:**

| Use `doc()` | Use inline description |
|---|---|
| Same column in multiple schema files | One-off model or column description |
| Long markdown with bullet points | Short single-line description |
| Non-technical stakeholders edit docs | Description is model-specific |

`model_variant` appears in six schema files in this project — one `doc()` block, update once, propagates everywhere.

**Test after adding:**
```bash
dbt docs generate   # errors immediately if doc('block_name') not found
```

---

## Section 3 — Model Design

### Python models

Python models are `.py` files in `models/` — dbt treats them as first-class models in the DAG alongside SQL models. The main use case is calling ML libraries like scikit-learn that SQL cannot express.

**Step 1 — Python model: `models/marts/ml/churn_model_ml.py`**

```python
def model(dbt, session):
    dbt.config(materialized='table')  # must be table or incremental, not view

    import pandas as pd
    from sklearn.linear_model import LogisticRegression

    # pull feature data from upstream dbt model
    df = dbt.ref('mart_customer_features')

    # features and historical ground truth
    X = df[['days_since_last_activity', 'monthly_revenue', 'support_tickets']]
    y = df['is_churned']   # did they actually churn? — learned from data, not rules

    # train — sklearn figures out weights from historical data
    model = LogisticRegression()
    model.fit(X, y)

    # score every account
    df['churn_score'] = model.predict_proba(X)[:, 1]

    return df[['account_id', 'churn_score']]
```

**Step 2 — SQL model: `models/marts/ml/customer_risk_scores.sql`**

```sql
select
    account_id,
    churn_score,
    case when churn_score > 0.7 then 'high' else 'low' end as risk_tier
from {{ ref('churn_model_ml') }}   -- ref() to the Python model above
```

**The full picture:**

```
raw data (source)
      ↓
staging models (SQL) — clean and type cast
      ↓
mart_customer_features (SQL) — build ML features
      ↓
churn_model_ml (Python) — scikit-learn trains + scores
      ↓
customer_risk_scores (SQL) — segments by risk tier
      ↓
Metabase dashboard
```

dbt is the orchestration layer — SQL handles transformation, Python handles ML, `ref()` stitches them into one DAG with full lineage.

**Parameter notes:**
- `dbt` — dbt context object injected at runtime. Gives access to `dbt.ref()`, `dbt.source()`, `dbt.config()` — same as Jinja context in SQL models
- `session` — warehouse session object (Snowpark on Snowflake, Spark on Databricks). Always required in the function signature even if unused

Python models can only be materialized as `table` or `incremental` — not `view`.

> **Not supported on PostgreSQL** — Python models require a warehouse with a Python runtime (Snowflake, BigQuery, Databricks). This will error on the current Docker setup.

### Model contracts — enforce schema

```yaml
models:
  - name: model_revenue_monthly
    config:
      contract:
        enforced: true
    columns:
      - name: model_variant
        data_type: varchar
        constraints:
          - type: not_null
      - name: net_revenue
        data_type: numeric
```

Run with contract enforcement:

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource/dbt
dbt build --select model_revenue_monthly
```

Contract failures surface immediately — the run fails if column names or types don't match `schema.yml`.

Contracts enforce column names and data types only — not data values. Only columns declared in `schema.yml` are checked; undeclared columns are ignored.

**When to use contracts:**

| | No contract | Minimal contract | Full contract |
|---|---|---|---|
| Models | Staging, intermediate | Marts with few consumers | Critical public-facing marts |
| Consumers | Internal dbt models only | Use specific columns only | Many teams, entire schema |
| Rate of change | High — actively developing | Medium | Low — stable |
| Access modifier | private / protected | protected | public |

Contract strictness follows access modifier — `private` models need no contract, `public` models in a Mesh setup almost always need a full contract since other projects depend on them.

### Model versioning

**Required fields — both must exist together:**
- `latest_version` — tells dbt which version `ref('model_name')` resolves to
- `versions:` block with at least one `v:` entry — tells dbt what versions exist

**Optional fields:**
- `deprecation_date` — compile-time warning only after that date, run continues
- `defined_in` — only needed when filename breaks dbt naming convention

#### How dbt resolves versioned files

dbt looks for files following this convention:
```
model_name_v1.sql   ← for v: 1
model_name_v2.sql   ← for v: 2
```

If no `_v<n>.sql` file exists and no `defined_in` is specified, dbt falls back to the **base filename** (`model_name.sql`) for the latest version.

| Files present | dbt resolves to |
|---|---|
| `model_name_v2.sql` exists | that file — convention |
| No `_v2.sql`, no `defined_in` | `model_name.sql` — fallback |
| No `_v2.sql`, no `defined_in`, no base file | ERROR |

#### Naming strategy options

**Option 1 — Follow convention fully (recommended)**
```
customer_revenue_monthly_v1.sql   ← v1
customer_revenue_monthly_v2.sql   ← v2
```
```yaml
versions:
  - v: 1
    deprecation_date: "2026-06-01"
  - v: 2
    # no defined_in needed — dbt finds both files by convention
```

**Option 2 — Keep base name for latest version**
```
customer_revenue_monthly_v1.sql   ← v1, archived
customer_revenue_monthly.sql      ← v2, current — always the clean name
```
```yaml
versions:
  - v: 1
    deprecation_date: "2026-06-01"
    # no defined_in — dbt finds customer_revenue_monthly_v1.sql by convention
  - v: 2
    defined_in: customer_revenue_monthly   # needed — breaks convention
```
Advantage: the file you actively work on always has the clean name. Tradeoff: `defined_in` required on latest version permanently.

**Critical:** `defined_in` controls which file dbt reads — it does NOT control the table name. The default alias for any versioned model is always `<model_name>_v<n>` regardless of `defined_in`. To get a clean table name you must also set `alias` explicitly:

```yaml
versions:
  - v: 2
    defined_in: customer_revenue_monthly
    config:
      alias: customer_revenue_monthly   # without this, table is still named customer_revenue_monthly_v2
    columns:
      - include: all
      - name: revenue_tier
        data_type: varchar
```

`defined_in` and `alias` are independent — dbt does not coordinate them automatically.

#### Adding v2-only columns with include

```yaml
versions:
  - v: 1
    deprecation_date: "2026-06-01"
  - v: 2
    columns:
      - include: all        # inherit all columns, data_types and tests from shared columns: block
      - name: revenue_tier  # v2-only new column
        description: "Revenue tier classification — Platinum, Gold, Silver, Bronze."
        data_type: varchar
```

- `include: all` — inherit everything from model-level `columns:`, add new columns on top
- `include: none` — start fresh, explicitly list only what v2 has (use when removing columns)
- No `include` — defaults to `all`

#### Reference a specific version

```sql
-- resolves to latest_version
{{ ref('customer_revenue_monthly') }}

-- pin to a specific version
{{ ref('customer_revenue_monthly', v=1) }}
```

#### Validate versioning without running

```bash
# list all resolved versions — confirms dbt found the right files
dbt ls --select customer_revenue_monthly
# expected: resource_utilization.marts.revenue.customer_revenue_monthly.v1
#           resource_utilization.marts.revenue.customer_revenue_monthly.v2

# compile a specific version to inspect the SQL
dbt compile --select customer_revenue_monthly.v2

# full project parse — catches missing files, bad defined_in, YAML errors
dbt parse
```

#### Flip to v2 when ready

```yaml
latest_version: 2   # was: latest_version: 1
```

`ref('customer_revenue_monthly')` now resolves to v2 automatically. v1 consumers get a deprecation warning after `deprecation_date` but the run continues.

### Model access & groups

#### Access modifiers

```yaml
models:
  - name: model_revenue_monthly
    config:
      access: public      # other dbt projects can ref() this
      # access: protected # same project only (default)
      # access: private   # same group only
```

| Access | Scope | Use case |
|---|---|---|
| `protected` | Same project only | Staging, intermediate — internal building blocks, may restructure anytime |
| `public` | Any project | Stable marts consumed by other teams or dbt Mesh projects — combine with contracts |
| `private` | Same group only | Sensitive models — PII, finance calculations, compliance data |

Access strictness follows model layer — staging and intermediate should stay `protected`, public-facing marts go `public`, sensitive domain models go `private`.

#### Groups — ownership boundaries within a project

Define groups in a dedicated file:

```yaml
# dbt/models/groups.yml
groups:
  - name: finance
    owner:
      name: Finance Team
      email: finance@company.com

  - name: ml
    owner:
      name: Data Science Team
      email: ml@company.com
```

Assign a model to a group:

```yaml
models:
  - name: customer_revenue_monthly
    config:
      group: finance
      access: private    # only finance group models can ref() this
```

**When to create groups:**
- Multiple teams working in the same dbt project
- You need to enforce ownership — Finance owns revenue models, ML owns scoring models
- Sensitive models that should only be accessible within a domain
- dbt Mesh — groups map naturally to project boundaries in Runbook 7

**When NOT to create groups:**
- Single team project — unnecessary overhead
- All models are `protected` — groups only matter when `private` access is involved

#### Access for this project

| Model | Access | Group | Reason |
|---|---|---|---|
| `stg_*` | protected | none | internal, may restructure |
| `int_*` | protected | none | internal, may restructure |
| `customer_revenue_monthly` | public | finance | consumed by other projects in Mesh |
| `model_revenue_monthly` | public | finance | same |
| `churn_model_ml` | private | ml | sensitive scoring logic |

---



## Troubleshooting

**Deprecation warnings from installed packages**
dbt 1.9+ requires `arguments:` wrapper and `severity` inside `config:`. Older packages may not be updated yet.

Find all instances:
```bash
dbt test --no-partial-parse --show-all-deprecations
```

Try upgrading packages first:
```bash
dbt deps --upgrade
```

If warnings persist, fix manually in `dbt_packages/<package_name>/models/...`. Note: manual edits get overwritten on next `dbt deps`.

Correct YAML structure for any generic test:
```yaml
- dbt_utils.accepted_range:
    arguments:
      min_value: 0
      max_value: 100
    config:
      severity: warn
```

- `arguments:` — parameters the test macro needs to do its job
- `config:` — how dbt executes the test (severity, limit, where)
- Simple tests with no parameters (`not_null`, `unique`) need neither

**Generating schema YAML for an existing model**
Use `dbt-codegen` to generate a schema entry from the database — useful when a model exists but has no `schema.yml` entry yet.

Add to `packages.yml`:
```yaml
packages:
  - package: dbt-labs/codegen
    version: 0.12.1
```

```bash
dbt deps
```

Generate schema for a single model:
```bash
dbt run-operation generate_model_yaml --args '{"model_names": ["model_revenue_monthly"]}' > /tmp/model_revenue_monthly.yml
```

Generate schema for multiple models in one go:
```bash
dbt run-operation generate_model_yaml --args '{"model_names": ["model_revenue_monthly", "model_revenue_weekly", "model_revenue_ytd", "customer_revenue_weekly", "customer_revenue_ytd"]}' > /tmp/revenue_models.yml
code /tmp/revenue_models.yml
```

Copy the output and paste into the appropriate `schema.yml`. `codegen` infers column names and data types from the database — add descriptions, tests, contracts, and group config manually after pasting.

**Error message doesn't name the failing model**
Run with debug logging — prints every step dbt takes internally including which model it was processing when the error occurred:
```bash
dbt compile --select model_name --no-partial-parse --log-level debug
```
The model name appears just before the error in the output. Useful for any cryptic parse or config error where the standard output doesn't tell you which model triggered it.

**Contract enforcement fails**
Check that all columns listed in `schema.yml` with `data_type` match exactly what the model SQL produces. Run `dbt compile --select model_name` to see the compiled SQL.

**Macro compiled SQL is hard to read**
Use `dbt compile --select model_name` (introduced in 3a) to generate the compiled SQL, then open `target/compiled/` in VS Code to inspect it. Paste it into pgAdmin to run directly.

---

## Final run sequence

Create `selectors.yml` in the `dbt/` folder for reusable selection logic:

```yaml
# dbt/selectors.yml
selectors:
  - name: personal_build
    description: "Full build in personal schema"
    definition:
      method: path
      value: models

  - name: revenue_only
    description: "All revenue mart models"
    definition:
      method: tag
      value: revenue

  - name: finance_group
    description: "All models owned by finance group"
    definition:
      method: group
      value: finance

  - name: ci_modified
    description: "Modified models + downstream — standard CI selector"
    definition:
      union:
        - method: state
          value: modified
          children: true
        - method: state
          value: new

  - name: failed_retry
    description: "Retry errored and failed models from last run"
    definition:
      union:
        - method: result
          value: error
          children: true
        - method: result
          value: fail
          children: true
```

Usage:

```bash
dbt build --selector personal_build
dbt build --selector revenue_only --target prod
dbt build --selector finance_group
dbt build --selector ci_modified --defer --state ./prod-state/
dbt build --selector failed_retry --state ./prod-state/
```

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource/dbt

# 1. Validate everything parses and resolves
dbt compile --no-partial-parse

# 2. Build local
dbt build --target personal

# 3. Build prod
dbt build --target prod

# 4. Commit and push
cd ~/Documents/btg-case-studies-with-dbt
git add .
git commit -m "feat: add groups, access modifiers, model versioning, singular tests"
git push origin dev
```

---


Continue to **3c — dbt Internals**.
