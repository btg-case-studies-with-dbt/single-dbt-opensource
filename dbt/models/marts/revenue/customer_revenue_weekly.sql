{{
    config(
        materialized='incremental',
        unique_key=['account_id', 'week_start_date'],
        incremental_strategy='delete+insert',
        on_schema_change='append_new_columns'
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

    {% if is_incremental() %}
        where revenue_date >= (select max(week_start_date) from {{ this }}) - interval '2 weeks'
    {% endif %}

),

weekly as (

    select
        account_id,
        company_name,
        segment,
        vertical,
        account_size,
        
        -- Week boundaries (Sunday to Saturday)
        date_trunc('week', revenue_date)::date                      as week_start_date,
        (date_trunc('week', revenue_date) 
            + interval '6 days')::date                              as week_end_date,

        -- Aggregated revenue
        sum(total_gross_revenue)                                    as total_gross_revenue,
        sum(net_revenue)                                            as total_net_revenue,
        
        -- Daily metrics
        count(distinct revenue_date)                                as active_days,
        round(avg(net_revenue), 2)                                  as avg_daily_net_revenue,
        max(net_revenue)                                            as max_daily_net_revenue,
        min(net_revenue)                                            as min_daily_net_revenue

    from daily_revenue
    group by 
        account_id,
        company_name,
        segment,
        vertical,
        account_size,
        week_start_date,
        week_end_date

),

with_prior_week as (

    select
        w.*,

        -- Prior week revenue for WoW comparison
        lag(w.total_gross_revenue) over (
            partition by w.account_id
            order by w.week_start_date
        )                                                           as prior_week_gross_revenue,

        lag(w.total_net_revenue) over (
            partition by w.account_id
            order by w.week_start_date
        )                                                           as prior_week_net_revenue,

        -- WoW absolute change
        w.total_gross_revenue - lag(w.total_gross_revenue) over (
            partition by w.account_id
            order by w.week_start_date
        )                                                           as wow_gross_revenue_change,

        w.total_net_revenue - lag(w.total_net_revenue) over (
            partition by w.account_id
            order by w.week_start_date
        )                                                           as wow_net_revenue_change,

        -- WoW percentage change
        case 
            when lag(w.total_gross_revenue) over (
                partition by w.account_id order by w.week_start_date
            ) > 0 then
                round(
                    (w.total_gross_revenue - lag(w.total_gross_revenue) over (
                        partition by w.account_id order by w.week_start_date
                    )) / lag(w.total_gross_revenue) over (
                        partition by w.account_id order by w.week_start_date
                    ) * 100, 
                    2
                )
            else null
        end                                                         as wow_gross_revenue_pct_change,

        case 
            when lag(w.total_net_revenue) over (
                partition by w.account_id order by w.week_start_date
            ) > 0 then
                round(
                    (w.total_net_revenue - lag(w.total_net_revenue) over (
                        partition by w.account_id order by w.week_start_date
                    )) / lag(w.total_net_revenue) over (
                        partition by w.account_id order by w.week_start_date
                    ) * 100, 
                    2
                )
            else null
        end                                                         as wow_net_revenue_pct_change

    from weekly w

)

select * from with_prior_week
