{{
    config(
        materialized='table'
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
