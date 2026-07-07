{{
    config(
        materialized='table',
        post_hook=(
            [
                "do $$ declare r regclass; begin select conrelid into r from pg_constraint where conname = 'dim_model_pk'; if r is not null then execute format('alter table %s drop constraint dim_model_pk', r); end if; end $$;",
                "alter table {{ this }} add constraint dim_model_pk primary key (model_variant)"
            ] if target.name not in ['prod', 'ci'] else []
        )
    )
}}

select
    -- Identity
    model_variant,
    model_display_name,
    model_resource_name,
    model_family,
    model_version,
    model_publisher,

    -- Classification
    model_task,
    inference_scope,
    is_open_source,

    -- Capacity
    model_replica_count,
    model_max_concurrency,
    model_ideal_concurrency,
    model_max_requests_per_second,

    -- Infrastructure
    model_accelerator_type,
    model_accelerators_per_replica,
    model_memory_gb_per_replica,

    -- Endpoint
    model_endpoint_url,

    -- Performance
    model_tokens_per_second,
    model_avg_tokens_per_request,
    model_avg_latency_seconds,

    -- Metadata
    snapshot_date,
    loaded_at

from {{ ref('stg_config_model_dimensions') }}
