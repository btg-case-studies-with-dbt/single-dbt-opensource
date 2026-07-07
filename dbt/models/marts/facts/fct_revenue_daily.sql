{{
    config(
        materialized='incremental',
        unique_key='revenue_id',
        incremental_strategy='delete+insert',
        on_schema_change='append_new_columns'
    )
}}

-- Grain: one row per account × model_variant × product_sku × billing_type
--        × inference_scope × source_region × day (TASK1_DESIGN §1.1/§1.2).
-- Dim attributes intentionally excluded — join dim_customer / dim_model /
-- dim_region via entities at query time.

select
    -- Surrogate PK (hash of full grain)
    {{ dbt_utils.generate_surrogate_key([
        'r.account_id',
        'r.model_variant',
        'r.product_sku',
        'r.billing_type',
        'r.inference_scope',
        'r.source_region',
        'r.revenue_date'
    ]) }} as revenue_id,

    -- Foreign keys to conformed dims
    r.account_id,
    r.model_variant,
    r.source_region,

    -- Degenerate dimensions
    r.product_sku,
    r.billing_type,
    r.inference_scope,
    r.currency_code,

    -- Time
    r.revenue_date,

    -- Measures
    r.gross_rev_input_tokens,
    r.gross_rev_output_tokens,
    r.gross_rev_cache_read_tokens,
    r.gross_rev_cache_write_tokens,
    r.total_gross_revenue,
    r.savings_plan_amount,
    r.discount_amount,
    r.net_revenue,

    -- Audit
    r.loaded_at

from {{ ref('int_revenue_daily') }} r

{% if is_incremental() %}
where r.revenue_date >= (select max(revenue_date) from {{ this }}) - interval '7 days'
{% endif %}
