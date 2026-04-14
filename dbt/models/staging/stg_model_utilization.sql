{{
    config(
        materialized='view'
    )
}}

with source as (

    select * from {{ source('raw_bronze', 'resource_model_utilization') }}
    where event_timestamp >= now() - interval '999 days'

),

renamed as (

    select
        pod_id,
        pod_name,
        instance_id,
        instance_role                                       as pod_instance_role,
        model_variant,
        pod_max_concurrency,
        actual_concurrency,
        util_ratio                                          as utilisation_ratio,
        round(util_ratio * 100, 2)                         as utilisation_pct,
        case
            when util_ratio >= 0.90 then 'critical'
            when util_ratio >= 0.75 then 'high'
            when util_ratio >= 0.50 then 'medium'
            else 'low'
        end                                                 as utilisation_band,
        region,
        status                                              as pod_status,
        event_timestamp,
        date_trunc('day', event_timestamp)                  as event_date,
        loaded_at

    from source

)

select * from renamed
