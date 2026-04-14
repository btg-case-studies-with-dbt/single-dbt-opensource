{{
    config(
        materialized='incremental',
        unique_key=['account_id', 'month_start_date'],
        incremental_strategy='delete+insert',
        on_schema_change='append_new_columns',
        contract={"enforced": true}
    )
}}

-- v1: original model — kept for backwards compatibility
-- deprecated: consumers should migrate to v2 which adds revenue_tier
-- see schema.yml for deprecation_date

with daily_revenue as (

    select
        account_id,
        company_name,
        segment,
        vertical,
        account_size,
        revenue_date,
        total_gross_revenue,
        1 as revenue_rank,
        'test' as revenue_tier, -- placeholder for v2 column
        net_revenue

    from {{ ref('int_revenue_daily') }}

    {% if is_incremental() %}
        where revenue_date >= (select max(month_start_date) from {{ this }}) - interval '2 months'
    {% endif %}

),

monthly as (

    select
        account_id,
        company_name,
        segment,
        vertical,
        account_size,revenue_tier,revenue_rank,
        date_trunc('month', revenue_date)::date                     as month_start_date,
        (date_trunc('month', revenue_date) 
            + interval '1 month' - interval '1 day')::date          as month_end_date,
        sum(total_gross_revenue)                                    as total_gross_revenue,
        sum(net_revenue)                                            as total_net_revenue,
        count(distinct revenue_date)                                as active_days,
        round(avg(net_revenue), 2)                                  as avg_daily_net_revenue,
        max(net_revenue)                                            as max_daily_net_revenue,
        min(net_revenue)                                            as min_daily_net_revenue

    from daily_revenue
    group by 
        account_id, company_name, segment, vertical, account_size,revenue_tier,revenue_rank,
        month_start_date, month_end_date

),

with_prior_month as (

    select
        m.*,
        lag(m.total_gross_revenue) over (
            partition by m.account_id order by m.month_start_date
        )                                                           as prior_month_gross_revenue,
        lag(m.total_net_revenue) over (
            partition by m.account_id order by m.month_start_date
        )                                                           as prior_month_net_revenue,
        m.total_gross_revenue - lag(m.total_gross_revenue) over (
            partition by m.account_id order by m.month_start_date
        )                                                           as mom_gross_revenue_change,
        m.total_net_revenue - lag(m.total_net_revenue) over (
            partition by m.account_id order by m.month_start_date
        )                                                           as mom_net_revenue_change,
        case 
            when lag(m.total_gross_revenue) over (
                partition by m.account_id order by m.month_start_date
            ) > 0 then
                round(
                    (m.total_gross_revenue - lag(m.total_gross_revenue) over (
                        partition by m.account_id order by m.month_start_date
                    )) / lag(m.total_gross_revenue) over (
                        partition by m.account_id order by m.month_start_date
                    ) * 100, 2
                )
            else null
        end                                                         as mom_gross_revenue_pct_change,
        case 
            when lag(m.total_net_revenue) over (
                partition by m.account_id order by m.month_start_date
            ) > 0 then
                round(
                    (m.total_net_revenue - lag(m.total_net_revenue) over (
                        partition by m.account_id order by m.month_start_date
                    )) / lag(m.total_net_revenue) over (
                        partition by m.account_id order by m.month_start_date
                    ) * 100, 2
                )
            else null
        end                                                         as mom_net_revenue_pct_change

    from monthly m

)

select * from with_prior_month
