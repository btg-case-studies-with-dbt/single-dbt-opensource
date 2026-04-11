{% docs customer_revenue_monthly_overview %}
Monthly revenue aggregated at the customer account level. One row per account per calendar month.

This is the primary revenue mart used by:
- Executive revenue dashboards in Metabase
- Customer portal API for account-level billing summaries
- Finance team for monthly revenue reporting and segment analysis

**Grain:** one row per `account_id` + `month_start_date`

**Key metrics:** `total_gross_revenue`, `total_net_revenue`, MoM comparisons

**Upstream:** `int_revenue_daily` → `stg_revenue_account_daily` + `stg_customer_details`
{% enddocs %}

{% docs net_revenue_definition %}
Net revenue is calculated as:

```
net_revenue = total_gross_revenue
            - coalesce(savings_plan_amount, 0)
            - coalesce(discount_amount, 0)
```

Net revenue should always be less than or equal to gross revenue.
A value greater than gross revenue indicates a calculation error.
{% enddocs %}

{% docs segment_definition %}
Customer account segment assigned by the sales team in the CRM.

Valid values:
- `Strategic` — top-tier accounts with dedicated account management
- `Commercial` — mid-tier accounts on standard plans
- `Unknown` — segment not yet assigned or missing from source data

Segment is captured at the time of revenue recognition using the customer snapshot,
ensuring historical accuracy even if the segment changes over time.
{% enddocs %}

{% docs mom_change_definition %}
Month-over-month absolute change calculated as:

```
mom_change = current_month_value - prior_month_value
```

NULL for the first month of a customer's history — no prior month exists to compare against.
Positive values indicate growth, negative values indicate decline.
{% enddocs %}

{% docs error_rate_pct_definition %}
Percentage of API requests in the period that resulted in an error response.

```
error_rate_pct = (error_count / total_requests) * 100
```

Valid range: 0 to 100. Values outside this range indicate a data quality issue.
A sustained error rate above 5% should trigger an alert.
{% enddocs %}

{% docs govcloud_definition %}
Boolean flag indicating whether the AWS region is a GovCloud region.

GovCloud regions (`us-gov-west-1`, `us-gov-east-1`) are subject to additional
compliance requirements and are only available to US government entities and
their contractors. Revenue and usage from GovCloud regions is reported separately
for compliance purposes.
{% enddocs %}
