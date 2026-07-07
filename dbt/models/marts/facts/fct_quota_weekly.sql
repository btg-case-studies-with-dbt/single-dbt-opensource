{{
    config(
        materialized='incremental',
        unique_key='quota_week_id',
        incremental_strategy='delete+insert',
        on_schema_change='append_new_columns',
        post_hook=(
            [
                "alter table {{ this }} drop constraint if exists fct_quota_weekly_pk",
                "alter table {{ this }} add constraint fct_quota_weekly_pk primary key (quota_week_id)",
                "alter table {{ this }} drop constraint if exists fct_quota_weekly_customer_fk",
                "alter table {{ this }} add constraint fct_quota_weekly_customer_fk foreign key (account_id) references {{ ref('dim_customer') }} (account_id)",
                "alter table {{ this }} drop constraint if exists fct_quota_weekly_model_fk",
                "alter table {{ this }} add constraint fct_quota_weekly_model_fk foreign key (model_variant) references {{ ref('dim_model') }} (model_variant)",
                "alter table {{ this }} drop constraint if exists fct_quota_weekly_region_fk",
                "alter table {{ this }} add constraint fct_quota_weekly_region_fk foreign key (source_region) references {{ ref('dim_region') }} (source_region)"
            ] if target.name not in ['prod', 'ci'] else []
        )
    )
}}

-- Grain: one row per account × model_variant × inference_scope × source_region
--        × week (TASK1_DESIGN §1.1/§1.2). STAYS WEEKLY: stateful snapshot of
-- limits in effect that week (carried forward), not an aggregation.
-- Renamed from customer_quota_weekly_history per GATE A item 3; that model is
-- now a compatibility view until semantic models re-point at Task 5.

with weekly_usage as (

    -- Aggregate minute-level token usage to the weekly grain.
    -- inference_region, model_type, and traffic_type are collapsed because
    -- quota limits are not tracked at those sub-dimensions.
    select
        account_id,
        model_variant,
        inference_scope,
        source_region,
        (date_trunc('week', minute_timestamp) - interval '1 day')::date as week_start_date,
        sum(request_count)                                  as actual_requests,
        sum(total_tokens)                                   as actual_total_tokens,
        sum(input_tokens)                                   as actual_input_tokens,
        sum(output_tokens)                                  as actual_output_tokens,
        max(request_count)                                  as actual_peak_rpm,
        max(total_tokens)                                   as actual_peak_tpm

    from {{ ref('int_token_usage_minute') }}

    {% if is_incremental() %}
        where event_date >= (select max(week_start_date) from {{ this }}) - interval '2 weeks'
    {% endif %}

    group by
        account_id,
        model_variant,
        inference_scope,
        source_region,
        week_start_date

)

select
    -- Surrogate PK (hash of full grain)
    {{ dbt_utils.generate_surrogate_key([
        'hr.account_id',
        'hr.model_variant',
        'hr.inference_scope',
        'hr.source_region',
        'hr.week_start_date'
    ]) }} as quota_week_id,

    hr.account_id,
    hr.model_variant,
    hr.inference_scope,
    hr.source_region,
    hr.week_start_date,
    hr.week_end_date,

    -- -------------------------------------------------------------------------
    -- Effective limits
    -- -------------------------------------------------------------------------
    hr.effective_rpm,
    hr.effective_tpm,
    hr.effective_tpd,
    hr.is_using_default,

    -- Approved adjustment carried forward for this week (null when on default)
    hr.adjusted_rpm,
    hr.adjusted_tpm,
    hr.adjusted_tpd,

    -- System defaults (always shown for reference)
    hr.default_rpm,
    hr.default_tpm,
    hr.default_tpd,

    -- -------------------------------------------------------------------------
    -- Actual usage (0 for weeks with no activity, null for peak metrics)
    -- -------------------------------------------------------------------------
    coalesce(wu.actual_requests, 0)                        as actual_requests,
    coalesce(wu.actual_total_tokens, 0)                    as actual_total_tokens,
    coalesce(wu.actual_input_tokens, 0)                    as actual_input_tokens,
    coalesce(wu.actual_output_tokens, 0)                   as actual_output_tokens,
    wu.actual_peak_rpm,
    wu.actual_peak_tpm,

    -- -------------------------------------------------------------------------
    -- Utilization: peak usage as % of the effective limit
    -- -------------------------------------------------------------------------
    round(
        wu.actual_peak_rpm::numeric / nullif(hr.effective_rpm, 0) * 100, 2
    )                                                       as peak_rpm_utilization_pct,
    round(
        wu.actual_peak_tpm::numeric / nullif(hr.effective_tpm, 0) * 100, 2
    )                                                       as peak_tpm_utilization_pct,

    -- -------------------------------------------------------------------------
    -- Pending request state for this specific week
    -- True for every week the request was open but not yet resolved
    -- -------------------------------------------------------------------------
    hr.has_pending_request,
    hr.pending_requested_rpm,
    hr.pending_requested_tpm,
    hr.pending_requested_tpd

from {{ ref('int_quota_history_resolved') }} hr

left join weekly_usage wu
    on  hr.account_id      = wu.account_id
    and hr.model_variant   = wu.model_variant
    and hr.inference_scope = wu.inference_scope
    and hr.source_region   = wu.source_region
    and hr.week_start_date = wu.week_start_date

{% if is_incremental() %}
where hr.week_start_date >= (select max(week_start_date) from {{ this }}) - interval '2 weeks'
{% endif %}
