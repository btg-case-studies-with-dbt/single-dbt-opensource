{{
    config(
        materialized='incremental',
        unique_key='usage_id',
        incremental_strategy='delete+insert',
        on_schema_change='append_new_columns',
        post_hook=(
            [
                "alter table {{ this }} drop constraint if exists fct_token_usage_minute_pk",
                "alter table {{ this }} add constraint fct_token_usage_minute_pk primary key (usage_id)",
                "alter table {{ this }} drop constraint if exists fct_token_usage_minute_customer_fk",
                "alter table {{ this }} add constraint fct_token_usage_minute_customer_fk foreign key (account_id) references {{ ref('dim_customer') }} (account_id)",
                "alter table {{ this }} drop constraint if exists fct_token_usage_minute_model_fk",
                "alter table {{ this }} add constraint fct_token_usage_minute_model_fk foreign key (model_variant) references {{ ref('dim_model') }} (model_variant)",
                "alter table {{ this }} drop constraint if exists fct_token_usage_minute_region_fk",
                "alter table {{ this }} add constraint fct_token_usage_minute_region_fk foreign key (source_region) references {{ ref('dim_region') }} (source_region)"
            ] if target.name not in ['prod', 'ci'] else []
        )
    )
}}

-- Grain: one row per account × model_variant × inference_scope × source_region
--        × inference_region × traffic_type × minute (TASK1_DESIGN §1.1/§1.2).
-- MINUTE grain preserved: peak_rpm, p95_rpm/tpm, active_minute_pct are
-- destroyed by daily pre-aggregation. model_type is a degenerate dim
-- (functionally dependent on model_variant), excluded from the PK.

select
    -- Surrogate PK (hash of full grain)
    {{ dbt_utils.generate_surrogate_key([
        'account_id',
        'model_variant',
        'inference_scope',
        'source_region',
        'inference_region',
        'traffic_type',
        'minute_timestamp'
    ]) }} as usage_id,

    -- Foreign keys to conformed dims
    account_id,
    model_variant,
    source_region,

    -- Degenerate dimensions
    model_type,
    inference_scope,
    inference_region,
    traffic_type,

    -- Time
    minute_timestamp,
    event_date,

    -- Measures
    request_count,
    input_tokens,
    output_tokens,
    cache_read_tokens,
    cache_write_tokens,
    total_tokens,
    error_count,

    -- Audit
    loaded_at

from {{ ref('int_token_usage_minute') }}

{% if is_incremental() %}
where minute_timestamp > (select max(minute_timestamp) from {{ this }})
{% endif %}
