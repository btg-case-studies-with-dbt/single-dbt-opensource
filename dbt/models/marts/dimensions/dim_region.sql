{{
    config(
        materialized='table'
    )
}}

select
    source_region,
    airport_code,
    territory,
    govcloud,
    description

from {{ ref('region_mapping') }}
