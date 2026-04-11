{{
    config(
        materialized='view'
    )
}}

with source as (

    select * from {{ source('raw_bronze', 'resource_accelerator_inventory') }}
    where event_timestamp >= now() - interval '999 days'

),

renamed as (

    select
        odcr                                                as capacity_reservation_id,
        instance_type                                       as accelerator_instance_type,
        platform                                            as cloud_platform,
        region                                              as accelerator_region,
        total_instance                                      as total_instances,
        idle_instance                                       as idle_instances,
        warmpool_instance                                   as warmpool_instances,
        used_instance                                       as used_instances,
        (warmpool_instance + used_instance)                 as allocated_instances,
        total_instance - idle_instance
            - warmpool_instance - used_instance             as unaccounted_instances,
        round(
            used_instance::numeric / nullif(total_instance, 0) * 100,
            2
        )                                                   as used_pct,
        round(
            (warmpool_instance + used_instance)::numeric
                / nullif(total_instance, 0) * 100,
            2
        )                                                   as allocated_pct,
        service_account_id,
        consumer_account_id,
        consumer_account_name,
        event_timestamp,
        date_trunc('day', event_timestamp)                  as event_date,
        loaded_at

    from source

)

select * from renamed
