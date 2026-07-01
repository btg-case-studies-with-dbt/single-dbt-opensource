# customer_revenue_monthly — Skill Reference

## Business Context
Monthly revenue mart per account, with month-over-month deltas. Joins
`int_revenue_daily` (gross/net revenue) with `dim_customer` (segment,
vertical, account_size, company_name).

## Entity Grain
One row per account_id + month_start_date. `unique_key=['account_id',
'month_start_date']`, enforced via incremental delete+insert.

## Materialization
`materialized='incremental'`, `incremental_strategy='delete+insert'`,
`on_schema_change='append_new_columns'`, **`contract={"enforced": true}`**.

The contract means the columns/types declared in this model's schema.yml are
a HARD CONTRACT. If this model's SELECT output drifts from that contract
(column added/removed/retyped -- including via an upstream type change
flowing through `int_revenue_daily` or `dim_customer`), `dbt build` fails at
the **contract-check step**, not at normal SQL execution. The error message
will mention "enforced contract" / "data type mismatch", not a typical
Postgres error.

## Key Columns
- `total_gross_revenue` / `total_net_revenue`: summed from `int_revenue_daily`.
- `mom_*_pct_change`: `lag()` window function vs the prior `month_start_date`
  for the same account.
- `revenue_tier`: hardcoded literal `'test'` -- known placeholder, not a real
  business value yet.
- `revenue_rank`: hardcoded literal `1` -- known placeholder, not a real
  business value yet.

## Gotchas
- The `is_incremental()` filter only looks back 2 months:
  `where revenue_date >= (select max(month_start_date) from {{ this }}) -
  interval '2 months'`. A late-arriving `revenue_date` older than that won't
  be picked up until a full-refresh (`dbt build --full-refresh`).
- Because of `contract={"enforced": true}`, an upstream change to
  `int_revenue_daily` or `dim_customer` (column rename/retype) can break THIS
  model even though this model's own SQL didn't change.

## Common Failure Patterns
- "enforced contract" / "data type mismatch" in the error -> a contract
  violation. Check whether `int_revenue_daily` or `dim_customer` changed a
  column type/name recently; fix by either updating this model's schema.yml
  contract to match the new (correct) type, or casting in the SELECT --
  prefer casting if the contract's declared type is the documented/correct one.
- `relation "int_revenue_daily" does not exist` or
  `relation "dim_customer" does not exist` -> an upstream model didn't build.
  Diagnose that upstream model first, not this one.

## Downstream Dependencies
Leaf mart -- consumed by exposures/dashboards (e.g. Metabase), no further dbt
models depend on it.
