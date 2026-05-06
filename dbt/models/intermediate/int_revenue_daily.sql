{{
    config(
        materialized='incremental',
        unique_key=['account_id', 'model_variant', 'source_region', 'revenue_date'],
        incremental_strategy='delete+insert',
        on_schema_change='append_new_columns'
    )
}}



    select
        -- Customer foreign key
        r.account_id,

        -- Model dimensions
        r.model_variant,
        r.product_sku,
        r.inference_scope,
        r.billing_type,

        -- Region foreign key
        r.source_region,

        -- Revenue metrics
        r.gross_rev_input_tokens,
        r.gross_rev_output_tokens,
        r.gross_rev_cache_read_tokens,
        r.gross_rev_cache_write_tokens,
        r.total_gross_revenue,
        r.savings_plan_amount,
        r.discount_amount,
        r.total_gross_revenue
            - coalesce(r.savings_plan_amount, 0)
            - coalesce(r.discount_amount, 0)    as net_revenue,

        -- Dates
        r.revenue_date,
        r.snapshot_date,
        r.currency_code,
        r.loaded_at

    from {{ ref('stg_revenue_account_daily') }} r

    {% if is_incremental() %}
    where revenue_date >= (select max(revenue_date) from {{ this }}) - interval '7 days'
    {% endif %}


