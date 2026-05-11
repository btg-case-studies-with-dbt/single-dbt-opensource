{{
    config(
        materialized='table'
    )
}}

-- Find the absolute earliest week a customer interacted with a model + region,
-- looking at both actual usage AND quota requests. A customer who submitted a
-- request before ever using the model should still get a spine starting that week.

with usage_anchor as (

    select
        account_id,
        model_variant,
        inference_scope,
        source_region,
        (date_trunc('week', minute_timestamp) - interval '1 day')::date as first_week

    from {{ ref('int_token_usage_minute') }}

),

request_anchor as (

    select
        account_id,
        model_variant,
        inference_scope,
        source_region,
        (date_trunc('week', request_created_at) - interval '1 day')::date as first_week

    from {{ ref('stg_quota_customer_rate_limit_requests') }}

),

combined as (

    select * from usage_anchor
    union all
    select * from request_anchor

)

select
    account_id,
    model_variant,
    inference_scope,
    source_region,
    min(first_week)                                         as first_week_start_date

from combined
group by
    account_id,
    model_variant,
    inference_scope,
    source_region
