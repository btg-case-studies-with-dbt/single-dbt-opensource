{% docs model_variant_dec %}
The specific Claude model version handling the request.
Examples: claude-3-opus, claude-3-sonnet, claude-3-haiku.

Sourced from the raw API request log and joined to 
dim_model_limits for context window and pricing metadata.
Null values indicate requests where model routing failed.
{% enddocs %}