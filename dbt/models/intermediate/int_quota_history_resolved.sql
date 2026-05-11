{{
    config(
        materialized='table'
    )
}}

-- Step 1 — Pin each adjustment to the Sunday of its effective week.
-- If multiple adjustments land in the same week, keep the latest one.
with adjustments as (

    select distinct on (
        account_id, model_variant, inference_scope, source_region,
        (date_trunc('week', adjustment_effective_date) - interval '1 day')::date
    )
        account_id,
        model_variant,
        inference_scope,
        source_region,
        (date_trunc('week', adjustment_effective_date) - interval '1 day')::date
                                                            as adj_week_start,
        adjusted_rpm,
        adjusted_tpm,
        adjusted_tpd

    from {{ ref('stg_quota_customer_rate_limit_adjustments') }}
    order by
        account_id, model_variant, inference_scope, source_region,
        (date_trunc('week', adjustment_effective_date) - interval '1 day')::date,
        adjustment_effective_date desc

),

-- Step 2 — Join the spine to adjustments on exact week match only.
-- Weeks without a new adjustment get NULL — carry-forward fills these in below.
spine_with_point_in_time as (

    select
        s.account_id,
        s.model_variant,
        s.inference_scope,
        s.source_region,
        s.week_start_date,
        s.week_end_date,
        a.adjusted_rpm,
        a.adjusted_tpm,
        a.adjusted_tpd

    from {{ ref('int_quota_weekly_spine') }} s
    left join adjustments a
        on  s.account_id      = a.account_id
        and s.model_variant   = a.model_variant
        and s.inference_scope = a.inference_scope
        and s.source_region   = a.source_region
        and s.week_start_date = a.adj_week_start

),

-- Step 3 — Island counting carry-forward.
-- count(adjusted_tpm) increments only on weeks where a new value appears,
-- creating a "group ID" that stays constant until the next approved change.
adj_groups as (

    select
        *,
        count(adjusted_tpm) over (
            partition by account_id, model_variant, inference_scope, source_region
            order by week_start_date
            rows between unbounded preceding and current row
        )                                                   as adj_group

    from spine_with_point_in_time

),

-- Step 4 — Fill every week in a group with the group's approved value.
-- max() is safe here because all non-null rows in the group share the same value.
limits_carried_forward as (

    select
        account_id,
        model_variant,
        inference_scope,
        source_region,
        week_start_date,
        week_end_date,
        max(adjusted_rpm) over (
            partition by account_id, model_variant, inference_scope, source_region, adj_group
        )                                                   as adjusted_rpm,
        max(adjusted_tpm) over (
            partition by account_id, model_variant, inference_scope, source_region, adj_group
        )                                                   as adjusted_tpm,
        max(adjusted_tpd) over (
            partition by account_id, model_variant, inference_scope, source_region, adj_group
        )                                                   as adjusted_tpd

    from adj_groups

),

-- Step 5 — Pending request visibility per week.
-- A request was pending during week W if:
--   (a) it was submitted on or before the end of week W, AND
--   (b) it was not yet resolved by the end of week W.
-- We use request_last_updated_at as the proxy for resolution date.
-- This correctly marks a 4-week pending request as pending on all 4 rows.
pending_per_week as (

    select
        s.account_id,
        s.model_variant,
        s.inference_scope,
        s.source_region,
        s.week_start_date,

        bool_or(
            r.request_created_at <= s.week_end_date::timestamp
            and (
                r.request_status = 'pending'
                or r.request_last_updated_at > s.week_end_date::timestamp
            )
        )                                                   as has_pending_request,

        max(case
            when r.request_created_at <= s.week_end_date::timestamp
             and (
                r.request_status = 'pending'
                or r.request_last_updated_at > s.week_end_date::timestamp
             )
            then r.requested_rpm
        end)                                                as pending_requested_rpm,

        max(case
            when r.request_created_at <= s.week_end_date::timestamp
             and (
                r.request_status = 'pending'
                or r.request_last_updated_at > s.week_end_date::timestamp
             )
            then r.requested_tpm
        end)                                                as pending_requested_tpm,

        max(case
            when r.request_created_at <= s.week_end_date::timestamp
             and (
                r.request_status = 'pending'
                or r.request_last_updated_at > s.week_end_date::timestamp
             )
            then r.requested_tpd
        end)                                                as pending_requested_tpd

    from {{ ref('int_quota_weekly_spine') }} s
    left join {{ ref('stg_quota_customer_rate_limit_requests') }} r
        on  s.account_id      = r.account_id
        and s.model_variant   = r.model_variant
        and s.inference_scope = r.inference_scope
        and s.source_region   = r.source_region
        and r.request_created_at <= s.week_end_date::timestamp

    group by
        s.account_id, s.model_variant, s.inference_scope, s.source_region, s.week_start_date

)

-- Step 6 — Combine limits with defaults and pending status.
select
    lf.account_id,
    lf.model_variant,
    lf.inference_scope,
    lf.source_region,
    lf.week_start_date,
    lf.week_end_date,

    -- Approved limit carried forward (null when customer is still on default)
    lf.adjusted_rpm,
    lf.adjusted_tpm,
    lf.adjusted_tpd,

    -- System defaults for this model + scope + region
    d.default_rpm,
    d.default_tpm,
    d.default_tpd,

    -- Effective limit: approved if set, default otherwise
    coalesce(lf.adjusted_rpm, d.default_rpm)               as effective_rpm,
    coalesce(lf.adjusted_tpm, d.default_tpm)               as effective_tpm,
    coalesce(lf.adjusted_tpd, d.default_tpd)               as effective_tpd,

    (lf.adjusted_tpm is null)                              as is_using_default,

    -- Pending request state for this specific week
    coalesce(pr.has_pending_request, false)                as has_pending_request,
    pr.pending_requested_rpm,
    pr.pending_requested_tpm,
    pr.pending_requested_tpd

from limits_carried_forward lf
left join {{ ref('stg_quota_default_rate_limits') }} d
    on  lf.model_variant   = d.model_variant
    and lf.inference_scope = d.inference_scope
    and lf.source_region   = d.source_region
left join pending_per_week pr
    on  lf.account_id      = pr.account_id
    and lf.model_variant   = pr.model_variant
    and lf.inference_scope = pr.inference_scope
    and lf.source_region   = pr.source_region
    and lf.week_start_date = pr.week_start_date
