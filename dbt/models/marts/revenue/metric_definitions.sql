{{ config(materialized='table') }}

select
    metric_key,
    display_name,
    business_term,
    grain,
    unit,
    source_table,
    source_column,
    formula_definition,
    owner_team,
    notes
from {{ ref('metric_definitions_seed') }}
