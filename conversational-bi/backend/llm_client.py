"""
Provider-agnostic LLM client for metric selection.

Returns a structured ``{metrics, dimensions, time_range, domain}`` dict
or ``None`` on provider failure.  Supported providers:

* ``ollama`` (default) — calls the local Ollama API
* ``openai`` — OpenAI-compatible chat completions endpoint (BYOK)
* ``anthropic`` — Anthropic Messages API (BYOK)

Provider is selected via the ``provider`` keyword argument or the
``LLM_PROVIDER`` environment variable.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# ── defaults ──────────────────────────────────────────────────────────────

DEFAULT_PROVIDER = os.environ.get("LLM_PROVIDER", "ollama")
DEFAULT_OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2")
DEFAULT_OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
DEFAULT_ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
ANTHROPIC_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")

# ── system prompt (build the question once per catalog) ───────────────────


def _build_system_prompt(catalog: dict[str, Any]) -> str:
    """Build a system prompt that embeds the compact catalog inline."""
    domain_list = ", ".join(catalog.get("domains", []))
    metric_lines = []
    for m in catalog.get("metrics", []):
        dims = ", ".join(m.get("valid_dimensions", [])[:8])  # cap for token economy
        metric_lines.append(
            f"- {m['name']}  ({m['label']})  [{m['domain']}]  -- {m.get('description', '')[:120]}"
        )
        if dims:
            metric_lines[-1] += f"  dims: {dims}"
    metrics_str = "\n".join(metric_lines)

    return f"""You are a governed-metric router. Map a natural-language question to the governed catalog below, OR decline when no single governed metric answers it. Declining correctly matters as much as answering: NEVER invent a metric, and never stretch an unrelated metric to fit.

Supported domains: {domain_list}

You MUST return a "classification" that is exactly one of:
- "answered": exactly ONE metric in the catalog below clearly measures what is asked.
- "ambiguous": the subject is a supported domain, but TWO OR MORE catalog metrics could each plausibly answer it and you cannot choose one without more detail.
- "unknown_metric": the subject is a supported domain, but NO catalog metric measures the requested concept (e.g. a rate, cost, ratio, growth %, cache-hit, or "remaining" figure the catalog does not contain).
- "unsupported_domain": the question is about a subject area NOT in the supported domains above (e.g. HR/headcount, customer-support tickets, marketing spend).

Rules:
1. answered → put exactly one catalog metric name in "metrics". Pick the SINGLE best match; do not decline just because the wording is loose or informal.
1b. Canonical defaults apply ONLY when the question NAMES a catalog measure family. bare "revenue"/"total revenue" -> the NET revenue metric; "total tokens"/"token usage" -> the aggregate total-tokens metric — do NOT call these ambiguous. But NEVER impose a default on a VAGUE proxy word that is not itself a named catalog measure: "value", "worth", "amount we got", "benefit", "how much did we get out of" with no named measure -> you cannot verify which metric is meant -> classification "unknown_metric" (do NOT guess revenue). Reserve "ambiguous" for two genuinely different NAMED measures (e.g. a rate vs a count, or two distinct utilization measures).
1c. A BREAKDOWN is NOT a SCOPE FILTER — separate them, because they carry different risk.
   - BREAKDOWN = group/segment the result ("by product line", "per model", "by region"). Put breakdowns in "dimensions". An unsupported breakdown is dropped by the server and the metric's TOTAL is still a correct answer, so a breakdown NEVER makes a question unknown — still return the metric.
   - SCOPE FILTER = restrict WHICH rows are counted ("from marketplace", "for the US", "billed to the Customer Success team", "on the Pro plan"). A scope filter CHANGES the number, so it must NEVER be silently ignored. Put EVERY scope filter in "filters" as {{"field": <catalog dimension name or null>, "value": <the entity/value>, "phrase": <verbatim span>}}. Name "field" ONLY when you are confident a catalog dimension of the CHOSEN metric expresses it AND the entity type matches (an internal team/department is NOT a customer account); otherwise set "field" to null. Set classification by the MEASURE alone (answered if a metric measures it) — the server verifies filter coverage and will DECLINE if a scope filter cannot be governed. Do NOT fold an unexpressible scope filter into an "answered" total yourself.
   - Decline as unknown_metric when the core MEASURE itself is absent from the catalog (e.g. "refund rate", "cache hit rate", "profit margin").
1d. A SUPERLATIVE / RANKING question ("WHICH/WHAT <entity> used the MOST / FEWEST / HIGHEST / LOWEST / TOP / BOTTOM ...", "rank ... by <entity>", "the biggest/smallest <entity>") asks WHICH MEMBER of a group leads — it is NOT a grand total. Returning the total across all groups is a correct number to a DIFFERENT question, so you must NEVER answer a superlative as a plain total. For EVERY superlative question you MUST emit "rank" as a JSON OBJECT — NEVER a bare string: {{"direction": "max" for most/highest/top/biggest OR "min" for fewest/lowest/bottom/smallest, "by_field": <the catalog dimension OF THE CHOSEN METRIC that names the ranked entity, or null if none matches>, "phrase": <the verbatim superlative span>}}. Identify the ENTITY being ranked and map it to a catalog dimension OF THE CHOSEN METRIC:
   - If a catalog dimension of the chosen metric expresses that entity, classification "answered", put ONLY that ranking dimension in "dimensions", and set "by_field" to that EXACT dimension name. The server groups by it and returns the leading row.
   - If NO catalog dimension of any relevant metric expresses the entity being ranked (e.g. "deployment" when the token metrics only carry account_id / model_variant), you CANNOT govern the ranking → classification "unknown_metric", "metrics": [], and set "by_field": null. Do NOT fall back to the grand total.
   Set "rank" to null (JSON null — NOT a string, NOT the object) for EVERY non-superlative question.
2. ambiguous → put the 2+ candidate catalog metric names in "metrics" and set "ambiguous": true.
3. unknown_metric → "metrics": [] and set "domain" to the supported domain the question belongs to.
4. unsupported_domain → "metrics": [] and set "domain" to the real out-of-catalog subject (e.g. "HR", "Support").
5. Use metric names spelled EXACTLY as in the catalog. Only include dimensions listed for the chosen metric.
6. Preserve time phrases ("last week", "this month", "last quarter") verbatim in "time_range".

Catalog:
{metrics_str}

Examples (question -> JSON):
"What was total net revenue last quarter?" -> {{"classification":"answered","metrics":["total_net_revenue"],"dimensions":[],"time_range":"last quarter","domain":"Revenue","ambiguous":false}}
"Show me prompt tokens used this week by model" -> {{"classification":"answered","metrics":["total_input_tokens"],"dimensions":["model_variant"],"time_range":"this week","domain":"Token usage","ambiguous":false}}
"What was total token usage yesterday?" -> {{"classification":"answered","metrics":["total_tokens_consumed"],"dimensions":[],"time_range":"yesterday","domain":"Token usage","ambiguous":false}}
"What is our recurring revenue this month?" -> {{"classification":"unknown_metric","metrics":[],"dimensions":[],"time_range":"this month","domain":"Revenue","ambiguous":false}}
"What is the cache hit rate for tokens this month?" -> {{"classification":"unknown_metric","metrics":[],"dimensions":[],"time_range":"this month","domain":"Token usage","ambiguous":false}}
"What is our quota utilization percentage by model?" -> {{"classification":"ambiguous","metrics":["peak_rpm_utilization","peak_tpm_utilization"],"dimensions":["model_variant"],"time_range":"","domain":"Quota","ambiguous":true}}
"What is the employee headcount by department?" -> {{"classification":"unsupported_domain","metrics":[],"dimensions":[],"time_range":"","domain":"HR","ambiguous":false}}
"How many customer support tickets were opened yesterday?" -> {{"classification":"unsupported_domain","metrics":[],"dimensions":[],"time_range":"yesterday","domain":"Support","ambiguous":false,"filters":[]}}
"Show me net revenue by product line for this year" -> {{"classification":"answered","metrics":["total_net_revenue"],"dimensions":[],"time_range":"this year","domain":"Revenue","ambiguous":false,"filters":[]}}  (a BREAKDOWN the catalog lacks -> dropped, total still answers)
"How much value did we get from marketplace last year?" -> {{"classification":"unknown_metric","metrics":[],"dimensions":[],"time_range":"last year","domain":"Revenue","ambiguous":false,"filters":[]}}  (vague measure "value" -> do not guess revenue)
"How many tokens did we bill to the Customer Success team?" -> {{"classification":"answered","metrics":["total_tokens_consumed"],"dimensions":[],"time_range":"","domain":"Token usage","ambiguous":false,"filters":[{{"field":null,"value":"Customer Success team","phrase":"billed to the Customer Success team"}}]}}  (scope filter on an internal team, not a customer account -> field null; server declines)
"Which model used the most tokens last week?" -> {{"classification":"answered","metrics":["total_tokens_consumed"],"dimensions":["model_variant"],"time_range":"last week","domain":"Token usage","ambiguous":false,"filters":[],"rank":{{"direction":"max","by_field":"model_variant","phrase":"Which model used the most"}}}}  (superlative "which/most" -> rank OBJECT by the governed dimension, NOT a grand total)
"Which customer used the fewest tokens last month?" -> {{"classification":"answered","metrics":["total_tokens_consumed"],"dimensions":["account_id"],"time_range":"last month","domain":"Token usage","ambiguous":false,"filters":[],"rank":{{"direction":"min","by_field":"account_id","phrase":"Which customer used the fewest"}}}}  (superlative "which/fewest" -> rank OBJECT, by_field=account_id, direction=min)
"Which deployment used the most tokens last week?" -> {{"classification":"unknown_metric","metrics":[],"dimensions":[],"time_range":"last week","domain":"Token usage","ambiguous":false,"filters":[],"rank":{{"direction":"max","by_field":null,"phrase":"Which deployment used the most"}}}}  ("deployment" is NOT a governed dimension of any token metric -> by_field null -> guard abstains; do NOT return the grand total)

Return ONLY valid JSON with this exact structure (no markdown, no explanation):
{{
  "classification": "answered | ambiguous | unknown_metric | unsupported_domain",
  "metrics": ["metric_name"] or [],
  "dimensions": ["dim_name", ...] or [],
  "filters": [{{"field": "dimension_name or null", "value": "restriction value", "phrase": "verbatim span"}}] or [],
  "time_range": "last week" or "this month" or "last quarter" or "" or a free-form string,
  "domain": "a supported domain, or the real out-of-catalog subject",
  "ambiguous": false,
  "rank": {{"direction": "max or min", "by_field": "catalog dimension of the chosen metric, or null", "phrase": "verbatim superlative span"}}  for a SUPERLATIVE question (rule 1d), or null for every non-superlative question
}}"""


# ── provider implementations ──────────────────────────────────────────────


def _call_ollama(
    prompt: str, model: str | None, catalog: dict[str, Any]
) -> dict[str, Any] | None:
    """Call Ollama API and return parsed structured response."""
    import httpx  # noqa: PLC0415

    url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/chat"
    body: dict[str, Any] = {
        "model": model or DEFAULT_OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": _build_system_prompt(catalog)},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0, "seed": int(os.environ.get("LLM_SEED", "42"))},
    }

    try:
        resp = httpx.post(url, json=body, timeout=60.0)
        resp.raise_for_status()
        data = resp.json()
        raw = data.get("message", {}).get("content", "")
        return _parse_structured_response(raw)
    except Exception:
        logger.exception("Ollama call failed")
        return None


def _call_openai(
    prompt: str,
    model: str | None,
    api_key: str | None,
    catalog: dict[str, Any],
) -> dict[str, Any] | None:
    """Call OpenAI-compatible chat completions API."""
    import httpx  # noqa: PLC0415

    key = api_key or os.environ.get("OPENAI_API_KEY")
    if not key:
        logger.error("OPENAI_API_KEY not set")
        return None

    url = f"{OPENAI_BASE_URL.rstrip('/')}/chat/completions"
    body: dict[str, Any] = {
        "model": model or DEFAULT_OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": _build_system_prompt(catalog)},
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
        # Determinism for the governed selector: greedy decoding + fixed seed so
        # metric selection is reproducible run-to-run. A governed metric has one
        # exact definition; the selector must not vary its choice by sampling.
        # (seed is honored by OpenAI-compatible endpoints that support it and
        # ignored by those that don't; temperature 0 is the load-bearing pin.)
        "temperature": 0,
        "seed": int(os.environ.get("LLM_SEED", "42")),
    }

    try:
        resp = httpx.post(
            url,
            json=body,
            headers={"Authorization": f"Bearer {key}"},
            timeout=60.0,
        )
        resp.raise_for_status()
        data = resp.json()
        raw = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        return _parse_structured_response(raw)
    except Exception:
        logger.exception("OpenAI call failed")
        return None


def _call_anthropic(
    prompt: str,
    model: str | None,
    api_key: str | None,
    catalog: dict[str, Any],
) -> dict[str, Any] | None:
    """Call Anthropic Messages API."""
    import httpx  # noqa: PLC0415

    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        logger.error("ANTHROPIC_API_KEY not set")
        return None

    url = f"{ANTHROPIC_BASE_URL.rstrip('/')}/v1/messages"
    body: dict[str, Any] = {
        "model": model or DEFAULT_ANTHROPIC_MODEL,
        "max_tokens": 1024,
        "temperature": 0,  # greedy decoding — deterministic governed selection
        "system": _build_system_prompt(catalog),
        "messages": [{"role": "user", "content": prompt}],
    }

    try:
        resp = httpx.post(
            url,
            json=body,
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            timeout=60.0,
        )
        resp.raise_for_status()
        data = resp.json()
        # Anthropic returns content as a list of blocks
        content_blocks = data.get("content", [])
        raw = " ".join(
            b.get("text", "") for b in content_blocks if b.get("type") == "text"
        )
        return _parse_structured_response(raw)
    except Exception:
        logger.exception("Anthropic call failed")
        return None


# ── response parsing ──────────────────────────────────────────────────────


def _parse_structured_response(raw: str) -> dict[str, Any] | None:
    """Parse an LLM text response into a structured dict.

    Attempts JSON parsing directly; falls back to extracting a JSON block
    from markdown fences.
    """
    text = raw.strip()

    # direct parse
    if text.startswith("{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

    # markdown-fenced JSON block
    import re  # noqa: PLC0415

    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    logger.warning("Failed to parse LLM response as JSON: %.200s", text)
    return None


# ── public API ────────────────────────────────────────────────────────────


def select_metrics(
    question: str,
    catalog: dict[str, Any],
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
) -> dict[str, Any] | None:
    """Route a question to an LLM and return structured metric selection.

    Parameters
    ----------
    question
        The user's natural-language question.
    catalog
        The compact catalog dict from ``catalog_builder.build_catalog()``.
    provider
        One of ``"ollama"``, ``"openai"``, ``"anthropic"``.  Falls back to
        the ``LLM_PROVIDER`` env var, then ``"ollama"``.
    model
        Model name override.  Uses provider-specific env var defaults when
        not set.
    api_key
        API key (BYOK).  Falls back to ``OPENAI_API_KEY`` or
        ``ANTHROPIC_API_KEY`` env vars.
    base_url
        Base URL override for the provider's API.

    Returns
    -------
    dict or None
        ``{"metrics": [...], "dimensions": [...], "time_range": "...", "domain": "..."}``
        or ``None`` on provider failure.
    """
    provider = (provider or DEFAULT_PROVIDER).lower()

    if provider == "openai":
        return _call_openai(question, model, api_key, catalog)
    elif provider == "anthropic":
        return _call_anthropic(question, model, api_key, catalog)
    else:
        # ollama is the default
        return _call_ollama(question, model, catalog)
