{{
    config(
        materialized='view'
    )
}}

with source as (

    select * from {{ source('raw_bronze', 'quota_customer_rate_limit_requests') }}

),

renamed as (

    select
        -- Identity
        account_id,

        -- Request Dimensions
        limit_type                                          as request_limit_type,
        inference_scope,
        model_variant,
        source_region,

        -- Requested Limits
        requests_per_minute                                 as requested_rpm,
        tokens_per_minute                                   as requested_tpm,
        tokens_per_day                                      as requested_tpd,

        -- Request Lifecycle
        status                                              as request_status,
        created_by                                          as request_created_by,
        create_datetime                                     as request_created_at,
        last_updated                                        as request_last_updated_at,

        -- Derived
        case status
            when 'pending'   then true
            else false
        end                                                 as is_pending,

        case status
            when 'approved'  then true
            else false
        end                                                 as is_approved,

        case status
            when 'rejected'  then true
            else false
        end                                                 as is_rejected,

        case status
            when 'cancelled' then true
            else false
        end                                                 as is_cancelled,

        -- SLA tracking
        now() - create_datetime                             as request_age,
        extract(epoch from (now() - create_datetime))/3600  as request_age_hours,

        -- Metadata
        loaded_at,
        source_file

    from source

)

select * from renamed
