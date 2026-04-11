{%- macro generate_schema_name(custom_schema_name, node) -%}
    {%- if node.resource_type == 'seed' -%}
        {{ custom_schema_name | trim }}
    {%- elif custom_schema_name is none -%}
        {{ target.schema }}
    {%- elif target.name == 'prod' -%}
        {{ custom_schema_name | trim }}
    {%- else -%}
        {{ target.schema }}_{{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro -%}