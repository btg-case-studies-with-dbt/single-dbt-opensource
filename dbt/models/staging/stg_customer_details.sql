{{
    config(
        materialized='view'
    )
}}

select
    -- Identity
    account_id,
    company_id,
    company_name,
    account_name,

    -- Segmentation — coalesce nulls/blanks to 'Unknown', keep original column names
    case
        when nullif(trim(account_size), '') is null then 'Unknown'
        else account_size
    end                                                 as account_size,

    case
        when nullif(trim(segment), '') is null then 'Unknown'
        else segment
    end                                                 as segment,

    case
        when nullif(trim(vertical), '') is null then 'Unknown'
        else vertical
    end                                                 as vertical,

    -- Ownership
    account_owner,
    account_email                                       as email,

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

from {{ source('raw_bronze', 'customer_details') }}
-- test change
-- test ci trigger
