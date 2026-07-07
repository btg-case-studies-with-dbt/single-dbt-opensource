{{
    config(
        materialized='view'
    )
}}

-- COMPATIBILITY VIEW — logic moved to fct_quota_weekly (GATE A item 3 rename,
-- 2026-07-06). Kept only so semantic_quota.yml keeps parsing until Task 5
-- re-points semantic models; delete at 5c/7b. Excludes the surrogate PK to
-- preserve the original column contract.

select
    account_id,
    model_variant,
    inference_scope,
    source_region,
    week_start_date,
    week_end_date,
    effective_rpm,
    effective_tpm,
    effective_tpd,
    is_using_default,
    adjusted_rpm,
    adjusted_tpm,
    adjusted_tpd,
    default_rpm,
    default_tpm,
    default_tpd,
    actual_requests,
    actual_total_tokens,
    actual_input_tokens,
    actual_output_tokens,
    actual_peak_rpm,
    actual_peak_tpm,
    peak_rpm_utilization_pct,
    peak_tpm_utilization_pct,
    has_pending_request,
    pending_requested_rpm,
    pending_requested_tpm,
    pending_requested_tpd

from {{ ref('fct_quota_weekly') }}
