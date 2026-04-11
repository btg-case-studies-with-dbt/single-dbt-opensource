{{
    config(
        materialized='view'
    )
}}

with source as (

    select * from {{ source('raw_bronze', 'quota_default_rate_limits') }}

),

renamed as (

    select
        -- Dimensions
        model_variant,
        inference_scope,
        source_region,

        -- Rate Limits
        requests_per_minute                                 as default_rpm,
        tokens_per_minute                                   as default_tpm,
        tokens_per_day                                      as default_tpd,

        -- Derived
        round(tokens_per_minute::numeric / nullif(requests_per_minute, 0), 0)
                                                            as avg_tokens_per_request_limit,
        round(tokens_per_day::numeric / nullif(tokens_per_minute * 60 * 24, 0), 4)
                                                            as tpd_to_tpm_ratio,

        -- Metadata
        snapshot_date,
        loaded_at,
        source_file

    from source

)

select * from renamed
