{{
    config(
        materialized='table'
    )
}}

with daily_revenue as (

    select
        account_id,
        company_name,
        segment,
        vertical,
        account_size,
        revenue_date,
        total_gross_revenue,
        net_revenue

    from {{ ref('int_revenue_daily') }}
    where extract(year from revenue_date) = extract(year from current_date)

),

ytd as (

    select
        account_id,
        company_name,
        segment,
        vertical,
        account_size,
        
        -- YTD date range
        min(revenue_date)                                           as ytd_start_date,
        max(revenue_date)                                           as ytd_end_date,
        extract(year from max(revenue_date))                        as year,

        -- Aggregated revenue
        sum(total_gross_revenue)                                    as ytd_gross_revenue,
        sum(net_revenue)                                            as ytd_net_revenue,
        
        -- Daily metrics
        count(distinct revenue_date)                                as active_days,
        round(avg(net_revenue), 2)                                  as avg_daily_net_revenue,
        max(net_revenue)                                            as max_daily_net_revenue,
        min(net_revenue)                                            as min_daily_net_revenue,

        -- Monthly metrics
        count(distinct date_trunc('month', revenue_date))           as active_months,
        round(
            sum(net_revenue) / 
            count(distinct date_trunc('month', revenue_date)), 
            2
        )                                                           as avg_monthly_net_revenue

    from daily_revenue
    group by 
        account_id,
        company_name,
        segment,
        vertical,
        account_size

),

with_rankings as (

    select
        y.*,

        -- Rankings within segments
        rank() over (
            partition by y.segment
            order by y.ytd_net_revenue desc
        )                                                           as rank_in_segment,

        -- Rankings within verticals
        rank() over (
            partition by y.vertical
            order by y.ytd_net_revenue desc
        )                                                           as rank_in_vertical,

        -- Overall ranking
        rank() over (
            order by y.ytd_net_revenue desc
        )                                                           as rank_overall,

        -- Cumulative percentage of total revenue
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
