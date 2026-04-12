select
    account_id,
    month_start_date,
    total_net_revenue,
    total_gross_revenue,
    'Negative revenue detected' as issue
from {{ ref('customer_revenue_monthly') }}
where total_gross_revenue < 0
   or total_net_revenue < 0