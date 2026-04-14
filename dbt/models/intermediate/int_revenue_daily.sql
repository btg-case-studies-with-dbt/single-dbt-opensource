{{
    config(
        materialized='incremental',
        unique_key=['account_id', 'model_variant', 'source_region', 'revenue_date'],
        incremental_strategy='delete+insert',
        on_schema_change='append_new_columns'
    )
}}

with revenue as (

    select * from {{ ref('stg_revenue_account_daily') }}

    {% if is_incremental() %}
    where revenue_date >= (select max(revenue_date) from {{ this }}) - interval '7 days'
    {% endif %}

),

customer as (

    select
        account_id,
        company_name,
        segment,
        vertical,
        account_size
    from {{ ref('stg_customer_details') }}

),

model_config as (

    select
        model_variant,
        model_family,
        model_publisher
    from {{ ref('stg_config_model_dimensions') }}

),

region_mapping as (

    select
        source_region,
        territory,
        govcloud
    from {{ ref('region_mapping') }}

),

enriched as (

    select
        -- Customer dimensions
        r.account_id,
        cu.company_name,
        cu.segment,
        cu.vertical,
        cu.account_size,

        -- Model dimensions
        r.model_variant,
        r.product_sku,
        r.inference_scope,
        r.billing_type,
        md.model_family,
        md.model_publisher,
     
        -- Region dimensions
        r.source_region,
        rm.territory,
        rm.govcloud,

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
            - coalesce(r.discount_amount, 0)                as net_revenue,

        -- Dates
        r.revenue_date,
        r.snapshot_date,
        r.currency_code,
        r.loaded_at

    from revenue r
    left join customer      cu on r.account_id    = cu.account_id
    left join model_config  md on r.model_variant = md.model_variant
    left join region_mapping rm on r.source_region = rm.source_region

)

select * from enriched
