{{
    config(
        materialized='incremental',
        unique_key=['model_variant', 'model_type', 'source_region', 'inference_region', 'month_start_date'],
        incremental_strategy='delete+insert',
        on_schema_change='append_new_columns'
    )
}}

with raw as (

    select
        model_variant,
        model_type,
        source_region,
        inference_region,
        inference_scope,
        date_trunc('month', minute_timestamp)::date          as month_start_date,
        (date_trunc('month', minute_timestamp)
            + interval '1 month' - interval '1 day')::date  as month_end_date,
        request_count, total_tokens, input_tokens, output_tokens, error_count

    from {{ ref('int_token_usage_minute') }}

    {% if is_incremental() %}
        where event_date >= (select max(month_start_date) from {{ this }}) - interval '1 month'
    {% endif %}

),

dim_model as (

    select
        model_variant,
        model_family,
        model_publisher

    from {{ ref('dim_model') }}

),

dim_region as (

    select
        source_region,
        territory,
        govcloud

    from {{ ref('dim_region') }}

),

enriched as (

    select
        r.model_variant,
        dm.model_family,
        dm.model_publisher,
        r.model_type,
        r.source_region,
        r.inference_region,
        r.inference_scope,
        dre.territory,
        dre.govcloud,
        r.month_start_date,
        r.month_end_date,
        r.request_count,
        r.total_tokens,
        r.input_tokens,
        r.output_tokens,
        r.error_count

    from raw r
    left join dim_model  dm  on r.model_variant = dm.model_variant
    left join dim_region dre on r.source_region  = dre.source_region

),

aggregated as (

    select
        model_variant, model_type, model_family, model_publisher,
        source_region, inference_region, inference_scope,
        territory, govcloud,
        month_start_date, month_end_date,

        round(avg(request_count), 2)                        as mean_rpm,
        max(request_count)                                  as peak_rpm,
        round(max(request_count)::numeric
            / nullif(avg(request_count), 0), 2)             as peak_to_mean_rpm,

        round(avg(total_tokens), 2)                         as mean_tpm,
        max(total_tokens)                                   as peak_tpm,
        round(max(total_tokens)::numeric
            / nullif(avg(total_tokens), 0), 2)              as peak_to_mean_tpm,

        sum(total_tokens)                                   as total_tokens,
        sum(input_tokens)                                   as total_input_tokens,
        sum(output_tokens)                                  as total_output_tokens,
        sum(request_count)                                  as total_requests,
        sum(error_count)                                    as total_errors,
        round(sum(error_count)::numeric
            / nullif(sum(request_count), 0) * 100, 2)       as error_rate_pct

    from enriched
    group by
        model_variant, model_type, model_family, model_publisher,
        source_region, inference_region, inference_scope,
        territory, govcloud,
        month_start_date, month_end_date

),

with_mom as (

    select
        a.*,

        a.mean_rpm - lag(a.mean_rpm) over (
            partition by a.model_variant, a.model_type, a.source_region, a.inference_region
            order by a.month_start_date
        )                                                   as mom_mean_rpm,

        a.mean_tpm - lag(a.mean_tpm) over (
            partition by a.model_variant, a.model_type, a.source_region, a.inference_region
            order by a.month_start_date
        )                                                   as mom_mean_tpm,

        a.total_tokens - lag(a.total_tokens) over (
            partition by a.model_variant, a.model_type, a.source_region, a.inference_region
            order by a.month_start_date
        )                                                   as mom_total_tokens,

        a.total_requests - lag(a.total_requests) over (
            partition by a.model_variant, a.model_type, a.source_region, a.inference_region
            order by a.month_start_date
        )                                                   as mom_total_requests

    from aggregated a

)

select * from with_mom
