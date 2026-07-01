# stg_revenue_account_daily — Skill Reference

## Business Context
Cleaned daily revenue at account + model + region grain. Core revenue fact
table -- feeds `int_revenue_daily`, which in turn feeds
`customer_revenue_monthly`/`customer_revenue_weekly`/`customer_revenue_ytd`
and `model_revenue_*`. Source is `raw_bronze.revenue_account_daily`.

## Entity Grain
One row per account_id + product_sku + model_variant + inference_scope +
source_region + billing_type + currency_code + revenue_date.

## Standard Hygiene Filter
`where revenue_date >= current_date - interval '999 days'` (applied in the
source CTE -- this model only ever sees the trailing ~999 days of bronze data).

## Key Columns
- `total_gross_revenue` = `gross_rev_input_tokens + gross_rev_output_tokens
  + gross_rev_cache_read_tokens + gross_rev_cache_write_tokens`. This is
  COMPUTED in this model, not present as-is in raw_bronze.
- `source_region`: renamed from raw `region`.
- `savings_plan_amount`: renamed from raw `savings_plan`.

## Gotchas
- `total_gross_revenue` is a sum of 4 token-revenue columns. If ANY of those
  4 source columns is missing or renamed in `raw_bronze.revenue_account_daily`,
  every downstream revenue mart breaks -- the error will surface here even
  though the root cause is the bronze loader.
- The `relationships` tests on `account_id` (-> stg_customer_details) and
  `model_variant` (-> stg_config_model_dimensions) are `severity: warn`, not
  error. An orphaned account_id/model_variant will NOT fail the build -- it
  silently drops out of downstream inner joins instead.

## Common Failure Patterns
- `column "gross_rev_*" does not exist` / `column "region" does not exist` /
  `column "savings_plan" does not exist` on `raw_bronze.revenue_account_daily`
  -> the bronze loader's schema changed. Root cause is upstream (the
  load_config_bronze* Airflow DAG / loader script), not this model's SQL.
  Do not propose fixing this by editing this model.
- `null value in column "total_gross_revenue"` -> one or more of the 4
  gross_rev_* source columns is null for some rows (none of them have a
  not_null test).

## Downstream Dependencies
`int_revenue_daily` -> `customer_revenue_monthly`, `customer_revenue_weekly`,
`customer_revenue_ytd`, `model_revenue_monthly`, `model_revenue_weekly`,
`model_revenue_ytd`.
