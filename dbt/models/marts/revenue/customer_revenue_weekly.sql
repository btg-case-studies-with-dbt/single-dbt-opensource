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
        revenue_date,
        total_gross_revenue,
        net_revenue

    from {{ ref('int_revenue_daily') }}

    {% if is_incremental() %}
        where revenue_date >= (select max(week_start_date) from {{ this }}) - interval '2 weeks'
    {% endif %}

),

dim_customer as (

    select
        account_id,
        company_name,
        segment,
        vertical,
        account_size

    from {{ ref('dim_customer') }}

),

enriched as (

    select
        dr.account_id,
        dc.company_name,
        dc.segment,
        dc.vertical,
        dc.account_size,
        dr.revenue_date,
        dr.total_gross_revenue,
        dr.net_revenue

    from daily_revenue dr
    left join dim_customer dc on dr.account_id = dc.account_id

),

weekly as (

    select
        account_id,
        company_name,
        segment,
        vertical,
        account_size,
        date_trunc('week', revenue_date)::date                      as week_start_date,
        (date_trunc('week', revenue_date)
            + interval '6 days')::date                              as week_end_date,
        sum(total_gross_revenue)                                    as total_gross_revenue,
        sum(net_revenue)                                            as total_net_revenue,
        count(distinct revenue_date)                                as active_days,
        round(avg(net_revenue), 2)                                  as avg_daily_net_revenue,
        max(net_revenue)                                            as max_daily_net_revenue,
        min(net_revenue)                                            as min_daily_net_revenue

    from enriched
    group by
        account_id, company_name, segment, vertical, account_size,
        week_start_date, week_end_date

),

with_prior_week as (

    select
        w.*,
        lag(w.total_gross_revenue) over (
            partition by w.account_id order by w.week_start_date
        )                                                           as prior_week_gross_revenue,
        lag(w.total_net_revenue) over (
            partition by w.account_id order by w.week_start_date
        )                                                           as prior_week_net_revenue,
        w.total_gross_revenue - lag(w.total_gross_revenue) over (
            partition by w.account_id order by w.week_start_date
        )                                                           as wow_gross_revenue_change,
        w.total_net_revenue - lag(w.total_net_revenue) over (
            partition by w.account_id order by w.week_start_date
        )                                                           as wow_net_revenue_change,
        case
            when lag(w.total_gross_revenue) over (
                partition by w.account_id order by w.week_start_date
            ) > 0 then
                round(
                    (w.total_gross_revenue - lag(w.total_gross_revenue) over (
                        partition by w.account_id order by w.week_start_date
                    )) / lag(w.total_gross_revenue) over (
                        partition by w.account_id order by w.week_start_date
                    ) * 100, 2
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
                    ) * 100, 2
                )
            else null
        end                                                         as wow_net_revenue_pct_change

    from weekly w

)

select * from with_prior_week
