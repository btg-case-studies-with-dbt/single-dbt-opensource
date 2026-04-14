{{
    config(
        materialized='incremental',
        unique_key=['account_id', 'model_variant', 'model_type', 'source_region', 'inference_region', 'week_start_date'],
        incremental_strategy='delete+insert',
        on_schema_change='append_new_columns'
    )
}}

with weekly as (

    select
        -- Customer dimensions
        account_id, company_name, segment,
        vertical, account_size,

        -- Model dimensions
        model_variant, model_type, model_family, model_publisher, 

        -- Region dimensions
        source_region, inference_region, inference_scope, traffic_type,
        territory,  govcloud,

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
        -- Customer dimensions
        account_id, company_name, segment,
        vertical, account_size,

        -- Model dimensions
        model_variant, model_type, model_family, model_publisher, 

        -- Region dimensions
        source_region, inference_region, inference_scope, traffic_type,
        territory,  govcloud,

        -- Week dimension
        week_start_date,
        week_end_date,

        -- Activity
        count(*)                                            as active_minutes,
        10080                                               as total_possible_minutes,
        round(count(*)::numeric / 10080 * 100, 2)          as active_minute_pct,

        -- RPM during active minutes
        round(avg(request_count), 2)                        as mean_rpm_active,
        round(sum(request_count)::numeric / 10080, 2)       as mean_rpm_all_minutes,
        max(request_count)                                  as peak_rpm,
        round(percentile_cont(0.90) within group
            (order by request_count)::numeric, 2)           as p90_rpm,
        round(percentile_cont(0.95) within group
            (order by request_count)::numeric, 2)           as p95_rpm,
        round(percentile_cont(0.97) within group
            (order by request_count)::numeric, 2)           as p97_rpm,

        -- TPM during active minutes
        round(avg(total_tokens), 2)                         as mean_tpm_active,
        round(sum(total_tokens)::numeric / 10080, 2)        as mean_tpm_all_minutes,
        max(total_tokens)                                   as peak_tpm,
        round(percentile_cont(0.90) within group
            (order by total_tokens)::numeric, 2)            as p90_tpm,
        round(percentile_cont(0.95) within group
            (order by total_tokens)::numeric, 2)            as p95_tpm,
        round(percentile_cont(0.97) within group
            (order by total_tokens)::numeric, 2)            as p97_tpm,

        -- Volume
        sum(request_count)                                  as total_requests,
        sum(total_tokens)                                   as total_tokens,
        sum(input_tokens)                                   as total_input_tokens,
        sum(output_tokens)                                  as total_output_tokens,
        sum(error_count)                                    as total_errors,
        round(sum(error_count)::numeric
            / nullif(sum(request_count), 0) * 100, 2)       as error_rate_pct

    from weekly
    group by
        account_id, company_name, segment,
        vertical, account_size,
        model_variant, model_type, model_family, model_publisher, 
        source_region, inference_region, inference_scope, traffic_type,
        territory,  govcloud,
        week_start_date, week_end_date

),

with_wow as (

    select
        a.*,

        a.mean_rpm_active - lag(a.mean_rpm_active) over (
            partition by a.account_id, a.model_variant, a.model_type,
                         a.source_region, a.inference_region
            order by a.week_start_date
        )                                                   as wow_mean_rpm_active,

        a.mean_tpm_active - lag(a.mean_tpm_active) over (
            partition by a.account_id, a.model_variant, a.model_type,
                         a.source_region, a.inference_region
            order by a.week_start_date
        )                                                   as wow_mean_tpm_active,

        a.total_tokens - lag(a.total_tokens) over (
            partition by a.account_id, a.model_variant, a.model_type,
                         a.source_region, a.inference_region
            order by a.week_start_date
        )                                                   as wow_total_tokens,

        a.total_requests - lag(a.total_requests) over (
            partition by a.account_id, a.model_variant, a.model_type,
                         a.source_region, a.inference_region
            order by a.week_start_date
        )                                                   as wow_total_requests,

        a.active_minutes - lag(a.active_minutes) over (
            partition by a.account_id, a.model_variant, a.model_type,
                         a.source_region, a.inference_region
            order by a.week_start_date
        )                                                   as wow_active_minutes

    from aggregated a

)

select * from with_wow
