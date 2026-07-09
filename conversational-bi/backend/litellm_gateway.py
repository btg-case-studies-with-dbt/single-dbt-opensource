"""
LiteLLM gateway for provider-agnostic LLM completion with fallback.

Config schema loaded from environment variables:

=======================  =======================================  ============
Env var                  Purpose                                  Default
=======================  =======================================  ============
LITELLM_PRIMARY_PROVIDER Primary provider name (openai/anthropic…) openai
LITELLM_PRIMARY_MODEL    Primary model name                       gpt-4o-mini
LITELLM_PRIMARY_API_KEY  API key for primary provider             *(none)*
LITELLM_FALLBACK_PROVIDER Fallback provider name                  *(none)*
LITELLM_FALLBACK_MODEL   Fallback model name                      *(none)*
LITELLM_FALLBACK_API_KEY API key for fallback provider            *(none)*
LITELLM_TEMPERATURE      Sampling temperature                     0.1
LITELLM_MAX_TOKENS       Max output tokens                        1024
=======================  =======================================  ============

Keeps ``llm_client.py`` as the fallback path — this module is the
LiteLLM-powered alternative selected when ``provider == "litellm"``.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

import litellm

logger = logging.getLogger(__name__)


# ── configuration ──────────────────────────────────────────────────────────


@dataclass
class LiteLLMConfig:
    """Configuration loaded from environment variables.

    Every field can be overridden by passing a value directly to the
    constructor; defaults pull from ``LITELLM_*`` env vars.
    """

    primary_provider: str = field(
        default_factory=lambda: os.environ.get("LITELLM_PRIMARY_PROVIDER", "openai")
    )
    primary_model: str = field(
        default_factory=lambda: os.environ.get("LITELLM_PRIMARY_MODEL", "gpt-4o-mini")
    )
    primary_api_key: str | None = field(
        default_factory=lambda: os.environ.get("LITELLM_PRIMARY_API_KEY")
    )

    fallback_provider: str | None = field(
        default_factory=lambda: os.environ.get("LITELLM_FALLBACK_PROVIDER")
    )
    fallback_model: str | None = field(
        default_factory=lambda: os.environ.get("LITELLM_FALLBACK_MODEL")
    )
    fallback_api_key: str | None = field(
        default_factory=lambda: os.environ.get("LITELLM_FALLBACK_API_KEY")
    )

    temperature: float = field(
        default_factory=lambda: float(os.environ.get("LITELLM_TEMPERATURE", "0.1"))
    )
    max_tokens: int = field(
        default_factory=lambda: int(os.environ.get("LITELLM_MAX_TOKENS", "1024"))
    )


# ── proxy class ────────────────────────────────────────────────────────────


class LiteLLMProxy:
    """Wrapper around ``litellm.completion()`` with primary/fallback logic.

    Usage::

        from conversational_bi.backend.litellm_gateway import LiteLLMProxy

        proxy = LiteLLMProxy()
        result = proxy.select_metrics(
            question="What was net revenue last week?",
            catalog=catalog,
        )

    The returned dict matches the ``llm_client.select_metrics()`` contract:
    ``{metrics, dimensions, time_range, domain, ambiguous}`` or ``None``.
    """

    def __init__(self, config: LiteLLMConfig | None = None) -> None:
        self.config = config or LiteLLMConfig()

    # ── internal helpers ────────────────────────────────────────────────

    @staticmethod
    def _build_messages(
        question: str, catalog: dict[str, Any]
    ) -> list[dict[str, str]]:
        """Build the message list using ``llm_client``'s system prompt."""
        from . import llm_client  # noqa: PLC0415 – same-package, reuse prompt builder

        system_prompt = llm_client._build_system_prompt(catalog)
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ]

    @staticmethod
    def _parse_response(raw: str) -> dict[str, Any] | None:
        """Parse an LLM text response into a structured dict.

        Mirrors ``llm_client._parse_structured_response`` to keep this module
        self-contained at the parsing layer.
        """
        text = raw.strip()

        # direct JSON parse
        if text.startswith("{"):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass

        # markdown-fenced JSON block
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass

        logger.warning("Failed to parse LiteLLM response as JSON: %.200s", text)
        return None

    def _call(
        self,
        provider: str,
        model: str,
        api_key: str | None,
        messages: list[dict[str, str]],
    ) -> dict[str, Any] | None:
        """Make a single ``litellm.completion()`` call.

        Returns a parsed structured dict on success, ``None`` on failure.
        """
        # litellm expects provider/model format: "openai/gpt-4o"
        # unless the model string already contains a "/"
        model_str = f"{provider}/{model}" if "/" not in model else model

        kwargs: dict[str, Any] = {
            "model": model_str,
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }
        if api_key:
            kwargs["api_key"] = api_key

        try:
            resp = litellm.completion(**kwargs)
            raw = resp.choices[0].message.content or ""
            return self._parse_response(raw)
        except Exception:
            logger.exception("LiteLLM call failed for %s/%s", provider, model)
            return None

    # ── public interface (matches llm_client.select_metrics signature) ───

    def select_metrics(
        self,
        question: str,
        catalog: dict[str, Any],
        provider: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any] | None:
        """Route a question through LiteLLM completion with fallback.

        Parameters mirror ``llm_client.select_metrics()`` for drop-in
        replacement.  When *provider* or *model* are passed they override
        the config's primary values for this call.

        Returns a structured dict with ``metrics``, ``dimensions``,
        ``time_range``, ``domain``, ``ambiguous`` or ``None`` on total
        failure (both primary and fallback exhausted).
        """
        # Prefer explicit kwargs over config defaults
        effective_provider = provider or self.config.primary_provider
        effective_model = model or self.config.primary_model
        effective_api_key = (
            api_key
            or self.config.primary_api_key
            or os.environ.get(f"{effective_provider.upper()}_API_KEY")
        )

        messages = self._build_messages(question, catalog)

        # ── primary attempt ─────────────────────────────────────────
        result = self._call(effective_provider, effective_model, effective_api_key, messages)
        if result is not None:
            return result

        # ── fallback attempt ─────────────────────────────────────────
        if self.config.fallback_provider and self.config.fallback_model:
            logger.info(
                "Primary LLM (%s/%s) failed; falling back to %s/%s",
                effective_provider,
                effective_model,
                self.config.fallback_provider,
                self.config.fallback_model,
            )
            fallback_api_key = (
                self.config.fallback_api_key
                or os.environ.get(f"{self.config.fallback_provider.upper()}_API_KEY")
            )
            result = self._call(
                self.config.fallback_provider,
                self.config.fallback_model,
                fallback_api_key,
                messages,
            )
            if result is not None:
                return result

        logger.error("Both primary and fallback LLM providers failed")
        return None
