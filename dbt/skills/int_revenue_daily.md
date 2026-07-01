# int_revenue_daily — Skill Reference

## Business Context
Daily revenue at account + model + region grain, intended to be "enriched
with customer, model, and region dimensions" (per its schema.yml
description). Feeds `customer_revenue_monthly`, `customer_revenue_weekly`,
`customer_revenue_ytd`, and `model_revenue_*`.

## Current SQL vs schema.yml -- KNOWN GAP
`int_revenue_daily.sql` selects `r.*` from `{{ ref('stg_revenue_account_daily') }}`
ONLY (model + region dims). It does NOT join `stg_customer_details`, even
though `int_schema.yml` documents AND tests four customer-dimension columns
on this model:
- `company_name` (from `stg_customer_details.company_name`)
- `segment` (from `stg_customer_details.segment`)
- `vertical` (from `stg_customer_details.vertical`)
- `account_size` (from `stg_customer_details.account_size`)

All four have `not_null` tests with `severity: warn`.

## Common Failure Pattern -- THIS IS THE ROOT CAUSE, NOT A SEVERITY ISSUE
Because none of `company_name`/`segment`/`vertical`/`account_size` exist in
`int_revenue_daily`'s actual output, every one of their `not_null` tests fails
at QUERY TIME with `column "company_name"/"segment"/"vertical"/"account_size"
does not exist` -- a "Database Error in test ..." block in dbt.log. This is a
hard `[error]` and fails the build REGARDLESS of the `severity: warn`
configured on these tests (severity:warn only governs the "Got N results"
row-count case, not a query that errors before it can run).

## The Fix
In `models/intermediate/int_revenue_daily.sql`, add a join to the customer
dimension and select the missing columns:
```sql
from {{ ref('stg_revenue_account_daily') }} r
left join {{ ref('stg_customer_details') }} c
    on r.account_id = c.account_id
```
and add `c.company_name, c.segment, c.vertical, c.account_size` to the SELECT
list. Do NOT "fix" this by changing the severity of these tests or removing
them from `int_schema.yml` -- the schema.yml description explicitly promises
these customer-dimension columns, and downstream marts
(`customer_revenue_monthly`/`weekly`/`ytd`) rely on them.

## Downstream Dependencies
`int_revenue_daily` -> `customer_revenue_monthly`, `customer_revenue_weekly`,
`customer_revenue_ytd`, `model_revenue_monthly`, `model_revenue_weekly`,
`model_revenue_ytd`.
