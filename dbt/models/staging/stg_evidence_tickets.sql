{{
    config(
        materialized='view'
    )
}}

with source as (

    select * from {{ ref('seed_evidence_tickets') }}

),

renamed as (

    select
        ticket_id,
        account_id,
        customer_id,
        region,
        model_family,
        date                                                    as event_date,
        severity,
        sentiment,
        topic,
        summary,
        now()                                                   as loaded_at

    from source

)

select * from renamed