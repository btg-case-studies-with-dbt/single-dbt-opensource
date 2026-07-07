{{
    config(
        materialized='table',
        post_hook=(
            [
                "do $$ declare r regclass; begin select conrelid into r from pg_constraint where conname = 'dim_region_pk'; if r is not null then execute format('alter table %s drop constraint dim_region_pk', r); end if; end $$;",
                "alter table {{ this }} add constraint dim_region_pk primary key (source_region)"
            ] if target.name not in ['prod', 'ci'] else []
        )
    )
}}

select
    source_region,
    airport_code,
    territory,
    govcloud,
    description

from {{ ref('region_mapping') }}
