# schema_patterns — Common dbt Failure Patterns (single-dbt-opensource)

General patterns across this project's ~25 models. Schema layout:
staging/ and intermediate/ -> `<target>_staging_silver`; marts/ and
marts/dimensions/ -> `<target>_mart_gold`. The only usable target in this
project's local Docker setup is `prod` (see dbt-debug-agent/db.py), so
inspect_postgres_schema should resolve schemas as `prod_staging_silver` /
`prod_mart_gold`.

## "column X does not exist" / "relation X does not exist"
- If X is a column referenced from a `source()` (`raw_bronze.*`): the bronze
  loader's schema changed. Root cause is upstream (the load_config_bronze*
  Airflow DAG / loader script), not the dbt model. Do not propose adding the
  column via COALESCE/default inside the model -- flag it as an upstream data
  issue.
- If X is a column from a `ref()` upstream model: the upstream model's SELECT
  list changed (column renamed/removed) without updating this model's SQL.
  Propose updating this model's SELECT to match the upstream change, or flag
  the upstream change itself if it looks unintentional.

## Contract violations (models with `config(contract={"enforced": true})`)
Currently: `customer_revenue_monthly`. The error mentions "enforced contract"
and a data type mismatch, NOT a normal Postgres error. Root cause is almost
always an upstream column type change. Fix by either updating the contract's
schema.yml column type to match the new type, or casting in this model's
SELECT -- prefer casting if the contract's declared type is the
documented/correct one.

## not_null / accepted_values test failures
- `severity: error` (the default) blocks the build and shows as a "Failure in
  test ..." block in dbt.log.
- `severity: warn` only changes the outcome when the test QUERY RUNS and
  returns N>0 rows ("Got N results, configured to warn if != 0") -- that case
  is logged but does not fail the build.
- IMPORTANT: if the test query itself errors out before it can count rows
  (e.g. "column ... does not exist" / "relation ... does not exist" --
  a "Database Error in test ..." block), that is a hard [error] regardless of
  the test's configured severity, and DOES fail the build / trigger the
  callback. Do not dismiss a "Failure in test ..." block just because
  read_manifest shows that test's severity as "warn" -- check whether the
  raw_block says "Database Error" (severity-independent) vs.
  "Got N results, configured to warn/fail if != 0" (severity-dependent).
- All `relationships` (foreign-key) tests to `stg_customer_details` and
  `stg_config_model_dimensions` in this project are `severity: warn` -- an
  orphaned `account_id`/`model_variant` will never fail a build (these are
  normal row-count checks, not Database Errors).
- `int_revenue_daily`'s schema.yml documents/tests `company_name`, `segment`,
  `vertical`, `account_size` as columns of that model (with not_null
  severity:warn), but if the model's SELECT doesn't actually produce those
  columns (e.g. a missing join to the customer dimension), every one of those
  tests fails with "column ... does not exist" -- a hard error. The fix
  belongs in `int_revenue_daily.sql` (add the missing join/columns), not in
  the schema.yml severity.

## Incremental models
- `customer_revenue_monthly` and similar incremental marts only re-scan a
  short trailing window (e.g. 2 months) via `is_incremental()`. A failure
  caused by late-arriving historical data may require
  `dbt build --full-refresh --select <model>` rather than a code fix.
