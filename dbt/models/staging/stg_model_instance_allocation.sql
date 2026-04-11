{{
    config(
        materialized='view'
    )
}}

with source as (

    select * from {{ source('raw_bronze', 'resource_model_instance_allocation') }}
    where event_timestamp >= now() - interval '999 days'

),

renamed as (

    select
        model_variant,
        region,
        instance_type                                       as accelerator_instance_type,
        used_instances,
        warmpool_instances,
        (used_instances + warmpool_instances)               as total_allocated_instances,
        round(
            used_instances::numeric
                / nullif(used_instances + warmpool_instances, 0) * 100,
            2
        )                                                   as used_pct,
        event_timestamp,
        date_trunc('day', event_timestamp)                  as event_date,
        loaded_at

    from source

)

select * from renamed
