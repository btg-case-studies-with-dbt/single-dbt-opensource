{% snapshot customer_details_snapshot %}

{{
    config(
      target_schema='snapshots',
      unique_key='account_id',
      strategy='timestamp',
      updated_at='date_updated',
      invalidate_hard_deletes=True
    )
}}

select
    account_id,
    company_id,
    company_name,
    segment,
    vertical,
    account_size,
    is_active,
    date_updated
from {{ source('raw_bronze', 'customer_details') }}

{% endsnapshot %}
