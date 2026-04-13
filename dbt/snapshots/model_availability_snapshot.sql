{% snapshot model_availability_snapshot %}
{{
    config(
        unique_key=['model_variant', 'source_region'],
        strategy='check',
        check_cols=['is_active'],
        invalidate_hard_deletes=True
    )
}}

select
    model_variant,
    source_region,
    deployed_at,
    is_active,
    snapshot_date,
    loaded_at,
    source_file
from {{ source('raw_bronze', 'config_model_region_availability') }}

{% endsnapshot %}