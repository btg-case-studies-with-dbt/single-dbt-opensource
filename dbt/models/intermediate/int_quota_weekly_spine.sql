{{
    config(
        materialized='table'
    )
}}

with spine as (

    select
        f.account_id,
        f.model_variant,
        f.inference_scope,
        f.source_region,
        generate_series(
            f.first_week_start_date::timestamp,
            (date_trunc('week', current_date) - interval '1 day')::timestamp,
            interval '1 week'
        )::date                                             as week_start_date

    from {{ ref('int_quota_first_activity') }} f

)

select
    account_id,
    model_variant,
    inference_scope,
    source_region,
    week_start_date,
    (week_start_date + interval '6 days')::date             as week_end_date

from spine
