{{
    config(
        materialized='view'
    )
}}

with source as (

    select * from {{ source('raw_bronze', 'inference_user_token_usage_open_source') }}
    where event_timestamp >= now() - interval '999 days'

),

filtered as (

    select * from source
    where
        request_id           is not null
        and account_id       is not null
        and model_variant    is not null
        and input_token      is not null
        and output_token     is not null
        and source_region    is not null
        and inference_region is not null
        and event_timestamp  is not null
        and loaded_at        is not null

),

renamed as (

    select
        request_id,
        account_id,
        api_name                                            as api_endpoint,
        'open_source'                                       as model_type,
        model_variant,
        input_token                                         as input_tokens,
        output_token                                        as output_tokens,
        coalesce(cache_read_token, 0)                       as cache_read_tokens,
        coalesce(cache_write_token, 0)                      as cache_write_tokens,
        input_token + output_token
            + coalesce(cache_read_token, 0)
            + coalesce(cache_write_token, 0)                as total_tokens,
        source_region,
        inference_region,
        inference_scope,
        traffic_type,
        latency_ms,
        error_code,
        case
            when error_code is not null then true
            else false
        end                                                 as is_error,
        event_timestamp,
        local_timestamp,
        date_trunc('minute', event_timestamp)               as minute_timestamp,
        date_trunc('hour', event_timestamp)                 as hour_timestamp,
        date(event_timestamp)                               as event_date,
        loaded_at

    from filtered

)

select * from renamed
