{{
    config(
        materialized='view'
    )
}}

with source as (

    select * from {{ source('raw_bronze', 'config_model_dimensions') }}

),

renamed as (

    select
        -- Model Identity
        model_variant,
        model_display_name,
        model_resource_name,
        model_family,
        model_version,
        publisher_name as model_publisher,

        -- Classification
        model_task,
        inference_scope,
        is_open_source,

        -- Capacity
        replicas                                            as model_replica_count,
        max_concurrency                                     as model_max_concurrency,
        ideal_concurrency                                   as model_ideal_concurrency,
        max_rps                                             as model_max_requests_per_second,

        -- Infrastructure
        accelerator_type                                    as model_accelerator_type,
        accelerators_per_replica                            as model_accelerators_per_replica,
        memory_gb                                           as model_memory_gb_per_replica,

        -- Endpoint
        endpoint                                            as model_endpoint_url,

        -- Performance Benchmarks
        tokens_per_second                                   as model_tokens_per_second,
        avg_tokens_per_request                              as model_avg_tokens_per_request,
        avg_latency_seconds                                 as model_avg_latency_seconds,

        -- Metadata
        snapshot_date,
        loaded_at,
        source_file

    from source

)

select * from renamed
