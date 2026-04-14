{{
    config(
        materialized='view'
    )
}}

with source as (

    select * from {{ source('raw_bronze', 'revenue_account_daily') }}
    where revenue_date >= current_date - interval '999 days'

),

renamed as (

    select
        account_id,
        product_sku,
        model_variant,
        inference_scope,
        region                                              as source_region,
        gross_rev_input_tokens,
        gross_rev_output_tokens,
        gross_rev_cache_read_tokens,
        gross_rev_cache_write_tokens,
        gross_rev_input_tokens
            + gross_rev_output_tokens
            + gross_rev_cache_read_tokens
            + gross_rev_cache_write_tokens              as total_gross_revenue,
        savings_plan                                        as savings_plan_amount,
        discount_amount,
        currency_code,
        billing_type,
        revenue_date,
        snapshot_date,
        loaded_at,
        source_file

    from source

)

select * from renamed
