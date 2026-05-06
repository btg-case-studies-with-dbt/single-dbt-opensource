{{
    config(
        materialized='incremental',
        unique_key=['model_variant', 'source_region', 'month_start_date'],
        incremental_strategy='delete+insert',
        on_schema_change='append_new_columns'
    )
}}

with daily_revenue as (

    select
        model_variant,
        source_region,
        account_id,
        revenue_date,
        total_gross_revenue,
        net_revenue

    from {{ ref('int_revenue_daily') }}

    {% if is_incremental() %}
        where revenue_date >= (select max(month_start_date) from {{ this }}) - interval '2 months'
    {% endif %}

),

dim_model as (

    select
        model_variant,
        model_family,
        model_publisher

    from {{ ref('dim_model') }}

),

dim_region as (

    select
        source_region,
        territory,
        govcloud

    from {{ ref('dim_region') }}

),

enriched as (

    select
        dr.model_variant,
        dm.model_family,
        dm.model_publisher,
        dr.source_region,
        dre.territory,
        dre.govcloud,
        dr.account_id,
        dr.revenue_date,
        dr.total_gross_revenue,
        dr.net_revenue

    from daily_revenue dr
    left join dim_model  dm  on dr.model_variant = dm.model_variant
    left join dim_region dre on dr.source_region  = dre.source_region

),

monthly as (

    select
        model_variant,
        model_family,
        model_publisher,
        source_region,
        territory,
        govcloud,
        date_trunc('month', revenue_date)::date                     as month_start_date,
        (date_trunc('month', revenue_date)
            + interval '1 month' - interval '1 day')::date          as month_end_date,
        sum(total_gross_revenue)                                    as total_gross_revenue,
        sum(net_revenue)                                            as total_net_revenue,
        count(distinct account_id)                                  as unique_customers,
        count(distinct revenue_date)                                as active_days,
        round(avg(net_revenue), 2)                                  as avg_daily_net_revenue,
        max(net_revenue)                                            as max_daily_net_revenue

    from enriched
    group by
        model_variant, model_family, model_publisher,
        source_region, territory, govcloud,
        month_start_date, month_end_date

),

with_prior_month as (

    select
        m.*,
        lag(m.total_gross_revenue) over (
            partition by m.model_variant, m.source_region
            order by m.month_start_date
        )                                                           as prior_month_gross_revenue,
        lag(m.total_net_revenue) over (
            partition by m.model_variant, m.source_region
            order by m.month_start_date
        )                                                           as prior_month_net_revenue,
        lag(m.unique_customers) over (
            partition by m.model_variant, m.source_region
            order by m.month_start_date
        )                                                           as prior_month_unique_customers,
        m.total_gross_revenue - lag(m.total_gross_revenue) over (
            partition by m.model_variant, m.source_region
            order by m.month_start_date
        )                                                           as mom_gross_revenue_change,
        m.total_net_revenue - lag(m.total_net_revenue) over (
            partition by m.model_variant, m.source_region
            order by m.month_start_date
        )                                                           as mom_net_revenue_change,
        m.unique_customers - lag(m.unique_customers) over (
            partition by m.model_variant, m.source_region
            order by m.month_start_date
        )                                                           as mom_customer_change,
        case
            when lag(m.total_gross_revenue) over (
                partition by m.model_variant, m.source_region
                order by m.month_start_date
            ) > 0 then
                round(
                    (m.total_gross_revenue - lag(m.total_gross_revenue) over (
                        partition by m.model_variant, m.source_region
                        order by m.month_start_date
                    )) / lag(m.total_gross_revenue) over (
                        partition by m.model_variant, m.source_region
                        order by m.month_start_date
                    ) * 100, 2
                )
            else null
        end                                                         as mom_gross_revenue_pct_change,
        case
            when lag(m.total_net_revenue) over (
                partition by m.model_variant, m.source_region
                order by m.month_start_date
            ) > 0 then
                round(
                    (m.total_net_revenue - lag(m.total_net_revenue) over (
                        partition by m.model_variant, m.source_region
                        order by m.month_start_date
                    )) / lag(m.total_net_revenue) over (
                        partition by m.model_variant, m.source_region
                        order by m.month_start_date
                    ) * 100, 2
                )
            else null
        end                                                         as mom_net_revenue_pct_change

    from monthly m

)

select * from with_prior_month
