"""
Guardrails for the Conversational BI backend.

Two classes:

* ``PIIRedactor`` — wraps Presidio to detect and redact emails, phone numbers,
  and API keys from user input.
* ``ContentFilter`` — regex-based checks that block disallowed LLM prompt
  categories (SQL generation, metric creation) before they reach the model.
"""

from __future__ import annotations

import logging
import re

from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
from presidio_anonymizer import AnonymizerEngine

logger = logging.getLogger(__name__)

# ── custom recognizer: API keys ────────────────────────────────────────────

_API_KEY_PATTERNS: list[Pattern] = [
    # OpenAI / generic sk-... keys
    Pattern(
        name="openai-api-key",
        regex=r"\bsk-\w{20,}\b",
        score=0.85,
    ),
    # AWS Access Key ID
    Pattern(
        name="aws-access-key-id",
        regex=r"\bAKIA[0-9A-Z]{16}\b",
        score=0.85,
    ),
    # Anthropic sk-ant-... keys
    Pattern(
        name="anthropic-api-key",
        regex=r"\bsk-ant-\w{20,}\b",
        score=0.85,
    ),
    # Hugging Face / generic HF tokens
    Pattern(
        name="hf-api-token",
        regex=r"\bhf_\w{20,}\b",
        score=0.80,
    ),
    # Generic bearer tokens in headers
    Pattern(
        name="bearer-token",
        regex=r"\b[Bb]earer\s+\w{20,}\b",
        score=0.75,
    ),
]

_api_key_recognizer = PatternRecognizer(
    supported_entity="API_KEY",
    patterns=_API_KEY_PATTERNS,
)


class PIIRedactor:
    """Detect and redact personally identifiable information from text.

    Uses Presidio's ``AnalyzerEngine`` (with built-in recognizers for
    email, phone, credit-card, etc.) plus a custom recognizer for API key
    patterns.
    """

    def __init__(self) -> None:
        self._analyzer = AnalyzerEngine()
        self._analyzer.registry.add_recognizer(_api_key_recognizer)
        self._anonymizer = AnonymizerEngine()

    def redact(self, text: str) -> str:
        """Return *text* with detected PII replaced by ``[REDACTED]``.

        If analysis raises an unexpected exception the original text is
        returned unmodified and a warning is logged.
        """
        if not text or not text.strip():
            return text

        try:
            results = self._analyzer.analyze(
                text=text,
                entities=[
                    "EMAIL_ADDRESS",
                    "PHONE_NUMBER",
                    "CREDIT_CARD",
                    "API_KEY",
                ],
                language="en",
            )
        except Exception:
            logger.warning("PII analysis failed – returning original text", exc_info=True)
            return text

        if not results:
            return text

        redacted: str = self._anonymizer.anonymize(
            text=text,
            analyzer_results=results,
        ).text

        if redacted != text:
            logger.info("PII redacted %d entity(s) from input", len(results))

        return redacted


# ── content filter patterns ────────────────────────────────────────────────

# SQL-generation prompts
_SQL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bwrite\s+(a\s+)?SQL\b", re.IGNORECASE),
    re.compile(r"\bgenerate\s+(a\s+)?(SQL\s+)?query\b", re.IGNORECASE),
    re.compile(r"\bcreate\s+(a\s+)?SQL\b", re.IGNORECASE),
    re.compile(r"\bcompose\s+(a\s+)?SQL\b", re.IGNORECASE),
    re.compile(r"\bshow\s+me\s+the\s+SQL\b", re.IGNORECASE),
    re.compile(r"\bgive\s+me\s+the\s+(underlying\s+)?query\b", re.IGNORECASE),
    re.compile(r"\braw\s+(SQL\s+)?query\b", re.IGNORECASE),
]

# Metric-creation prompts
_METRIC_CREATION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bcreate\s+(a\s+)?(new\s+)?metric\b", re.IGNORECASE),
    re.compile(r"\badd\s+(a\s+)?(new\s+)?metric\b", re.IGNORECASE),
    re.compile(r"\bdefine\s+(a\s+)?(new\s+)?metric\b", re.IGNORECASE),
    re.compile(r"\bregister\s+(a\s+)?metric\b", re.IGNORECASE),
    re.compile(r"\binsert\s+(a\s+)?metric\b", re.IGNORECASE),
    re.compile(r"\bmake\s+(a\s+)?(new\s+)?metric\b", re.IGNORECASE),
    re.compile(r"\bintroduce\s+(a\s+)?(new\s+)?metric\b", re.IGNORECASE),
]


class ContentFilter:
    """Regex-based content filter for LLM input/output.

    Blocks requests that attempt to generate SQL or create new metrics,
    since those operations must go through the governed semantic layer.
    """

    BLOCK_REASON_SQL = "SQL generation is not allowed — use the governed metric catalog"
    BLOCK_REASON_METRIC = "Metric creation is not allowed — submit a metric request through the governed process"

    def __init__(self) -> None:
        self._sql_patterns = _SQL_PATTERNS
        self._metric_patterns = _METRIC_CREATION_PATTERNS

    def check(self, text: str) -> tuple[bool, str]:
        """Check *text* against blocked categories.

        Returns
        -------
        (blocked, reason)
            ``(True, reason)`` if the text matches a blocked pattern,
            ``(False, "")`` otherwise.
        """
        if not text or not text.strip():
            return False, ""

        for pattern in self._sql_patterns:
            if pattern.search(text):
                logger.info("ContentFilter blocked: SQL pattern matched (%s)", pattern.pattern)
                return True, self.BLOCK_REASON_SQL

        for pattern in self._metric_patterns:
            if pattern.search(text):
                logger.info("ContentFilter blocked: metric-creation pattern matched (%s)", pattern.pattern)
                return True, self.BLOCK_REASON_METRIC

        return False, ""
