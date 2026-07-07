{{
    config(
        materialized='table',
        post_hook=(
            [
                "do $$ declare r regclass; begin select conrelid into r from pg_constraint where conname = 'dim_customer_pk'; if r is not null then execute format('alter table %s drop constraint dim_customer_pk', r); end if; end $$;",
                "alter table {{ this }} add constraint dim_customer_pk primary key (account_id)"
            ] if target.name not in ['prod', 'ci'] else []
        )
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
