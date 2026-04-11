{{
    config(
        materialized='incremental',
        unique_key=['account_id', 'model_variant', 'model_type', 'source_region', 'inference_region', 'minute_timestamp'],
        incremental_strategy='delete+insert',
        on_schema_change='append_new_columns'
    )
}}

with proprietary as (

    select
        account_id,
        model_variant,
        model_type,
        source_region,
        inference_region,
        inference_scope,
        traffic_type,
        input_tokens,
        output_tokens,
        cache_read_tokens,
        cache_write_tokens,
        total_tokens,
        is_error,
        minute_timestamp,
        event_date,
        loaded_at
    from {{ ref('stg_token_usage_proprietary') }}

    {% if is_incremental() %}
        where minute_timestamp > (select max(minute_timestamp) from {{ this }})
    {% endif %}

),

open_source as (

    select
        account_id,
        model_variant,
        model_type,
        source_region,
        inference_region,
        inference_scope,
        traffic_type,
        input_tokens,
        output_tokens,
        cache_read_tokens,
        cache_write_tokens,
        total_tokens,
        is_error,
        minute_timestamp,
        event_date,
        loaded_at
    from {{ ref('stg_token_usage_open_source') }}

    {% if is_incremental() %}
        where minute_timestamp > (select max(minute_timestamp) from {{ this }})
    {% endif %}

),

combined as (

    select * from proprietary
    union all
    select * from open_source

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

aggregated as (

    select
        c.account_id,
        coalesce(cu.company_name, 'Unknown')    as company_name,
        coalesce(cu.segment, 'Unknown')         as segment,
        coalesce(cu.vertical, 'Unknown')        as vertical,
        coalesce(cu.account_size, 'Unknown')    as account_size,
        c.model_variant,
        c.model_type,
        md.model_family,
        md.model_publisher,
      
        c.source_region,
        c.inference_region,
        c.inference_scope,
        c.traffic_type,
        rm.territory,
        rm.govcloud,

        c.minute_timestamp,
        c.event_date,

        -- RPM and TPM aggregations
        count(*)                                            as request_count,
        sum(c.input_tokens)                                 as input_tokens,
        sum(c.output_tokens)                                as output_tokens,
        sum(c.cache_read_tokens)                            as cache_read_tokens,
        sum(c.cache_write_tokens)                           as cache_write_tokens,
        sum(c.total_tokens)                                 as total_tokens,
        sum(case when c.is_error then 1 else 0 end)        as error_count,
        round(
            sum(case when c.is_error then 1 else 0 end)::numeric
                / nullif(count(*), 0) * 100,
            2
        )                                                   as error_rate_pct,

        max(c.loaded_at)                                    as loaded_at

    from combined c
    left join customer     cu on c.account_id    = cu.account_id
    left join model_config md on c.model_variant = md.model_variant
    left join region_mapping rm on c.source_region = rm.source_region

    group by
        c.account_id,
        cu.company_name,
        cu.segment,
        cu.vertical,
        cu.account_size,
        c.model_variant,
        c.model_type,
        md.model_family,
        md.model_publisher,
        c.source_region,
        c.inference_region,
        c.inference_scope,
        c.traffic_type,
        rm.territory,
        rm.govcloud,
        c.minute_timestamp,
        c.event_date

)

select * from aggregated
