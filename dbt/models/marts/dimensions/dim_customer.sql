{{
    config(
        materialized='table'
    )
}}

select
    -- Identity
    account_id,
    company_id,
    company_name,
    account_name,

    -- Segmentation
    account_size,
    segment,
    vertical,

    -- Ownership
    account_owner,
    email,

    -- Location
    city,
    country,

    -- Status
    is_active,
    cs_score,
    is_fraud,

    -- Dates
    date_created,
    date_updated,

    -- Metadata
    data_source,
    loaded_at

from {{ ref('stg_customer_details') }}
