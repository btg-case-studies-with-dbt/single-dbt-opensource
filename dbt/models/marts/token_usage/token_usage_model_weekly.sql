{{
    config(
        materialized='incremental',
        unique_key=['model_variant', 'model_type', 'source_region', 'inference_region', 'week_start_date'],
        incremental_strategy='delete+insert',
        on_schema_change='append_new_columns'
    )
}}

with weekly as (

    select
        -- Model dimensions
        model_variant,
        model_type,
        model_family,
        model_publisher,
        

        -- Region dimensions
        source_region,
        inference_region,
        inference_scope,
        territory,
        
        govcloud,

        -- Week dimension (Sunday to Saturday)
        date_trunc('week', minute_timestamp) - interval '1 day'   as week_start_date,
        date_trunc('week', minute_timestamp) + interval '5 days'  as week_end_date,

        -- Minute level metrics
        request_count,
        total_tokens,
        input_tokens,
        output_tokens,
        error_count

    from {{ ref('int_token_usage_minute') }}

    {% if is_incremental() %}
        where event_date >= (select max(week_start_date) from {{ this }}) - interval '7 days'
    {% endif %}

),

aggregated as (

    select
        -- Model dimensions
        model_variant,
        model_type,
        model_family,
        model_publisher,
        

        -- Region dimensions
        source_region,
        inference_region,
        inference_scope,
        territory,
        
        govcloud,

        -- Week dimension
        week_start_date,
        week_end_date,

        -- RPM metrics
        round(avg(request_count), 2)                        as mean_rpm,
        max(request_count)                                  as peak_rpm,
        round(
            max(request_count)::numeric
                / nullif(avg(request_count), 0),
            2
        )                                                   as peak_to_mean_rpm,

        -- TPM metrics
        round(avg(total_tokens), 2)                         as mean_tpm,
        max(total_tokens)                                   as peak_tpm,
        round(
            max(total_tokens)::numeric
                / nullif(avg(total_tokens), 0),
            2
        )                                                   as peak_to_mean_tpm,

        -- Volume metrics
        sum(total_tokens)                                   as total_tokens,
        sum(input_tokens)                                   as total_input_tokens,
        sum(output_tokens)                                  as total_output_tokens,
        sum(request_count)                                  as total_requests,
        sum(error_count)                                    as total_errors,
        round(
            sum(error_count)::numeric
                / nullif(sum(request_count), 0) * 100,
            2
        )                                                   as error_rate_pct

    from weekly
    group by
        model_variant, model_type, model_family, model_publisher, 
        source_region, inference_region, inference_scope,
        territory,  govcloud,
        week_start_date, week_end_date

),

with_wow as (

    select
        a.*,

        -- WoW absolute difference
        a.mean_rpm - lag(a.mean_rpm) over (
            partition by a.model_variant, a.model_type, a.source_region, a.inference_region
            order by a.week_start_date
        )                                                   as wow_mean_rpm,

        a.mean_tpm - lag(a.mean_tpm) over (
            partition by a.model_variant, a.model_type, a.source_region, a.inference_region
            order by a.week_start_date
        )                                                   as wow_mean_tpm,

        a.total_tokens - lag(a.total_tokens) over (
            partition by a.model_variant, a.model_type, a.source_region, a.inference_region
            order by a.week_start_date
        )                                                   as wow_total_tokens,

        a.total_requests - lag(a.total_requests) over (
            partition by a.model_variant, a.model_type, a.source_region, a.inference_region
            order by a.week_start_date
        )                                                   as wow_total_requests

    from aggregated a

)

select * from with_wow
