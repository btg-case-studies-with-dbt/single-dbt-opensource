{{
    config(
        materialized='table'
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
    where extract(year from revenue_date) = extract(year from current_date)

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

ytd as (

    select
        model_variant,
        model_family,
        model_publisher,
        source_region,
        territory,
        govcloud,
        min(revenue_date)                                           as ytd_start_date,
        max(revenue_date)                                           as ytd_end_date,
        extract(year from max(revenue_date))                        as year,
        sum(total_gross_revenue)                                    as ytd_gross_revenue,
        sum(net_revenue)                                            as ytd_net_revenue,
        count(distinct account_id)                                  as unique_customers_ytd,
        count(distinct revenue_date)                                as active_days,
        round(avg(net_revenue), 2)                                  as avg_daily_net_revenue,
        max(net_revenue)                                            as max_daily_net_revenue,
        min(net_revenue)                                            as min_daily_net_revenue,
        count(distinct date_trunc('month', revenue_date))           as active_months,
        round(
            sum(net_revenue) /
            count(distinct date_trunc('month', revenue_date)),
            2
        )                                                           as avg_monthly_net_revenue

    from enriched
    group by
        model_variant, model_family, model_publisher,
        source_region, territory, govcloud

),

with_rankings as (

    select
        y.*,
        rank() over (
            partition by y.model_family
            order by y.ytd_net_revenue desc
        )                                                           as rank_in_family,
        rank() over (
            partition by y.source_region
            order by y.ytd_net_revenue desc
        )                                                           as rank_in_region,
        rank() over (
            order by y.ytd_net_revenue desc
        )                                                           as rank_overall,
        round(
            y.ytd_net_revenue / nullif(y.unique_customers_ytd, 0),
            2
        )                                                           as revenue_per_customer,
        round(
            sum(y.ytd_net_revenue) over (
                order by y.ytd_net_revenue desc
                rows between unbounded preceding and current row
            ) / sum(y.ytd_net_revenue) over () * 100,
            2
        )                                                           as cumulative_revenue_pct

    from ytd y

)

select * from with_rankings
