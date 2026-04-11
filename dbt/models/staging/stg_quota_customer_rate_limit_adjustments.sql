{{
    config(
        materialized='view'
    )
}}

with source as (

    select * from {{ source('raw_bronze', 'quota_customer_rate_limit_adjustments') }}

),

renamed as (

    select
        -- Customer Reference
        account_id,

        -- Dimensions
        model_variant,
        inference_scope,
        source_region,

        -- Adjusted Rate Limits
        requests_per_minute                                 as adjusted_rpm,
        tokens_per_minute                                   as adjusted_tpm,
        tokens_per_day                                      as adjusted_tpd,

        -- Adjustment Context
        adjustment_reason,
        ticket_link,
        approved_by,
        effective_date                                      as adjustment_effective_date,
        expiry_date                                         as adjustment_expiry_date,

        -- Derived: is this adjustment currently active
        case
            when expiry_date is null then true
            when expiry_date >= current_date then true
            else false
        end                                                 as is_adjustment_active,

        -- Metadata
        snapshot_date,
        loaded_at,
        source_file

    from source

)

select * from renamed
