{{
    config(
        materialized='incremental',
        unique_key=['model_variant', 'source_region', 'week_start_date'],
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
        where revenue_date >= (select max(week_start_date) from {{ this }}) - interval '2 weeks'
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

weekly as (

    select
        model_variant,
        model_family,
        model_publisher,
        source_region,
        territory,
        govcloud,
        date_trunc('week', revenue_date)::date                      as week_start_date,
        (date_trunc('week', revenue_date)
            + interval '6 days')::date                              as week_end_date,
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
        week_start_date, week_end_date

),

with_prior_week as (

    select
        w.*,
        lag(w.total_gross_revenue) over (
            partition by w.model_variant, w.source_region
            order by w.week_start_date
        )                                                           as prior_week_gross_revenue,
        lag(w.total_net_revenue) over (
            partition by w.model_variant, w.source_region
            order by w.week_start_date
        )                                                           as prior_week_net_revenue,
        lag(w.unique_customers) over (
            partition by w.model_variant, w.source_region
            order by w.week_start_date
        )                                                           as prior_week_unique_customers,
        w.total_gross_revenue - lag(w.total_gross_revenue) over (
            partition by w.model_variant, w.source_region
            order by w.week_start_date
        )                                                           as wow_gross_revenue_change,
        w.total_net_revenue - lag(w.total_net_revenue) over (
            partition by w.model_variant, w.source_region
            order by w.week_start_date
        )                                                           as wow_net_revenue_change,
        w.unique_customers - lag(w.unique_customers) over (
            partition by w.model_variant, w.source_region
            order by w.week_start_date
        )                                                           as wow_customer_change,
        case
            when lag(w.total_gross_revenue) over (
                partition by w.model_variant, w.source_region
                order by w.week_start_date
            ) > 0 then
                round(
                    (w.total_gross_revenue - lag(w.total_gross_revenue) over (
                        partition by w.model_variant, w.source_region
                        order by w.week_start_date
                    )) / lag(w.total_gross_revenue) over (
                        partition by w.model_variant, w.source_region
                        order by w.week_start_date
                    ) * 100, 2
                )
            else null
        end                                                         as wow_gross_revenue_pct_change,
        case
            when lag(w.total_net_revenue) over (
                partition by w.model_variant, w.source_region
                order by w.week_start_date
            ) > 0 then
                round(
                    (w.total_net_revenue - lag(w.total_net_revenue) over (
                        partition by w.model_variant, w.source_region
                        order by w.week_start_date
                    )) / lag(w.total_net_revenue) over (
                        partition by w.model_variant, w.source_region
                        order by w.week_start_date
                    ) * 100, 2
                )
            else null
        end                                                         as wow_net_revenue_pct_change

    from weekly w

)

select * from with_prior_week
