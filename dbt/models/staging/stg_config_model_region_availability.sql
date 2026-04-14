{{
    config(
        materialized='view'
    )
}}

with source as (

    select * from {{ source('raw_bronze', 'config_model_region_availability') }}

),

renamed as (

    select
        -- Model Reference
        model_variant,

        -- Region
        source_region,

        -- Availability
        is_active                                           as is_region_active,
        deployed_at                                         as region_deployed_at,

        -- Metadata
        snapshot_date,
        loaded_at,
        source_file

    from source

)

select * from renamed
