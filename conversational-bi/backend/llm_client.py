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

    return f"""You are a governed-metric router.  Your job is to map a natural-language question to exactly one metric from the governed catalog below.

Supported domains: {domain_list}

Rules:
1. Return EXACTLY ONE metric name from the catalog.  If the question matches multiple metrics, return the most relevant one and set "ambiguous": false.
2. If NO metric in the catalog answers the question (e.g. customer-service questions, headcount), return "metrics": [].
3. Valid dimensions are listed per metric.  Only include dimensions that appear in the metric's list.
4. Time phrases like "last week", "this month", "last quarter" should be preserved as-is in time_range.
5. domain must be one of: {domain_list} or "unknown".

Catalog:
{metrics_str}

Return ONLY valid JSON with this exact structure (no markdown, no explanation):
{{
  "metrics": ["metric_name"] or [],
  "dimensions": ["dim_name", ...] or [],
  "time_range": "last week" or "this month" or "last quarter" or "" or a free-form string,
  "domain": "one of the supported domains or unknown",
  "ambiguous": false
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
