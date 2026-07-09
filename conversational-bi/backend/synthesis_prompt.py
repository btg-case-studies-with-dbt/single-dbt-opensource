"""Synthesis prompt builder and parser for evidence-grounded narratives.

Provides three public functions:

- ``build_synthesis_prompt`` — constructs an LLM prompt from metric
  results and evidence, instructing the model to produce a narrative
  with inline ``[Measured]`` / ``[Evidence]`` tier labels.
- ``call_synthesis_llm`` — sends the prompt to a configured LLM
  (Ollama by default, overridable via environment variables).
- ``parse_synthesis_output`` — parses the LLM response (or a
  programmatic fallback) into a ``SynthesisOutput``-compatible dict.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ── configuration (env-var overridable) ────────────────────────────────────

SYNTHESIS_MODEL: str = os.environ.get("SYNTHESIS_MODEL", "llama3.2")
SYNTHESIS_OLLAMA_URL: str = os.environ.get(
    "SYNTHESIS_OLLAMA_URL", "http://localhost:11434"
)
SYNTHESIS_MAX_TOKENS: int = int(os.environ.get("SYNTHESIS_MAX_TOKENS", "512"))

# ── prompt builder ──────────────────────────────────────────────────────────


def build_synthesis_prompt(metric_result: dict, evidence: list[dict]) -> str:
    """Build an LLM prompt for evidence-grounded synthesis.

    The prompt embeds the metric result and supporting evidence inline,
    then instructs the LLM to produce a narrative with ``[Measured]``
    and ``[Evidence]`` tier labels.  It explicitly forbids implying
    causality between evidence and metric movement.

    Parameters
    ----------
    metric_result : dict
        Outcome dict from ``query_translator.process_question``.
        Expected keys: ``category``, ``metric``, ``value``,
        ``dimensions``, ``time_range``, ``rows``, ``message``, etc.
    evidence : list[dict]
        List of evidence ticket dicts as returned by
        ``EvidenceRetriever``.  Each should at minimum have ``id``,
        ``summary``, ``severity``, and ``topic``.

    Returns
    -------
    str
        Fully-assembled prompt string, ready to send to an LLM.
    """
    category = metric_result.get("category", "unknown")

    # ── metric section ────────────────────────────────────────────────
    metric_name = metric_result.get("metric", "?")
    metric_value = metric_result.get("value", "N/A")
    dims = metric_result.get("dimensions", [])
    time_range = metric_result.get("time_range", "")
    rows = metric_result.get("rows", [])

    metric_lines: list[str] = []
    if category == "answered":
        metric_lines.append(f"- **Metric**: {metric_name}")
        metric_lines.append(f"- **Value**: {metric_value}")
        if dims:
            metric_lines.append(f"- **Dimensions**: {', '.join(dims)}")
        if time_range:
            metric_lines.append(f"- **Time range**: {time_range}")
        if rows:
            metric_lines.append(f"- **Rows returned**: {len(rows)}")
            for r in rows[:3]:
                metric_lines.append(f"  • {r}")
    else:
        message = metric_result.get("message", "No metric answer available.")
        metric_lines.append(f"- **Category**: {category} — {message}")

    # ── evidence section ──────────────────────────────────────────────
    evidence_lines: list[str] = []
    if evidence:
        evidence_lines.append("## Supporting Evidence (support tickets)")
        for t in evidence:
            tid = t.get("id", "?")
            summary = t.get("summary", "")[:200]
            severity = t.get("severity", "?")
            topic = t.get("topic", "")
            evidence_lines.append(f"- **{tid}** ({severity}, {topic}): {summary}")
    else:
        evidence_lines.append("## Supporting Evidence\nNone available.")

    # ── assemble ──────────────────────────────────────────────────────
    metric_section = "\n".join(metric_lines)
    evidence_section = "\n".join(evidence_lines)

    prompt = f"""You are a governed-analytics assistant. Your job is to synthesize a clear, evidence-grounded answer for a business user. You will be given a metric result and optional supporting evidence (support tickets).

## Metric Result
{metric_section}

{evidence_section}

## Instructions
1. **State the metric result clearly**: include the metric name, its value, and the time range. If the metric query did not return an answer (e.g. unknown metric, ambiguous question, unsupported domain), explain what happened.
2. **If supporting evidence is available**, cite it as context (e.g. "2 support tickets mention data latency this week"). Do NOT fabricate evidence.
3. **Label every factual claim inline** with a tier marker:
   - ``[Measured]`` for claims that come directly from the metric value.
   - ``[Evidence]`` for claims that reference a support ticket (include the ticket ID).
4. **NEVER imply causality** between evidence and metric movement. Correlation is not causation. Use language like "may be related to" or "context:" rather than "because" or "caused by".
5. **Be concise** — 3 to 6 sentences maximum. Write in plain business English.

## Output format
Write only the narrative with inline tier labels. No extra commentary, no markdown formatting of the output itself (except the inline [Measured]/[Evidence] labels)."""

    return prompt.strip()


# ── LLM caller ──────────────────────────────────────────────────────────────


def call_synthesis_llm(prompt: str) -> str | None:
    """Send a synthesis prompt to the configured LLM.

    Uses the ``SYNTHESIS_MODEL`` and ``SYNTHESIS_OLLAMA_URL`` environment
    variables.  Calls the Ollama ``/api/chat`` endpoint by default.

    Parameters
    ----------
    prompt : str
        The assembled prompt from ``build_synthesis_prompt``.

    Returns
    -------
    str or None
        The LLM's response text, or ``None`` on failure (logged).
    """
    url = f"{SYNTHESIS_OLLAMA_URL.rstrip('/')}/api/chat"

    body: dict[str, Any] = {
        "model": SYNTHESIS_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"num_predict": SYNTHESIS_MAX_TOKENS},
    }

    try:
        resp = httpx.post(url, json=body, timeout=60.0)
        resp.raise_for_status()
        data = resp.json()
        content = data.get("message", {}).get("content", "").strip()
        return content if content else None
    except Exception:
        logger.exception("Synthesis LLM call failed")
        return None


# ── output parser ────────────────────────────────────────────────────────────


def _find_ticket_id(text: str, evidence: list[dict]) -> str | None:
    """Search *text* for a ticket ID present in *evidence*.

    Returns the first matching ``id`` found, or ``None``.
    """
    for t in evidence:
        tid = t.get("id", "")
        if tid and tid in text:
            return tid
    return None


def _parse_claims(
    narrative: str, metric_name: str | None, evidence: list[dict]
) -> list[dict[str, Any]]:
    """Parse ``[Measured]`` and ``[Evidence]`` labels from *narrative*.

    Each returned dict has ``text`` (str), ``tier`` (``"measured"`` or
    ``"evidence"``), and ``source`` (metric name or ticket ID).  If
    no ticket ID can be found in an evidence claim's text, ``source``
    falls back to ``"evidence"``.
    """
    claims: list[dict[str, Any]] = []

    # Match [Measured] or [Evidence] and capture the text that follows
    # until the next label or end-of-string.
    pattern = r'\[(Measured|Evidence)\]\s*(.*?)(?=\s*\[(?:Measured|Evidence)\]|\s*$)'

    for match in re.finditer(pattern, narrative, re.DOTALL):
        tier = match.group(1).lower()
        text = match.group(2).strip()
        if not text:
            continue

        if tier == "measured":
            source: str = metric_name or "metric"
        else:
            source = _find_ticket_id(text, evidence) or "evidence"

        claims.append({"text": text, "tier": tier, "source": source})

    return claims


def _fallback_narrative(metric_result: dict, evidence: list[dict]) -> str:
    """Build a basic narrative without calling the LLM.

    Produces ``[Measured]`` / ``[Evidence]``-labelled text so the same
    parser works for both LLM and fallback paths.
    """
    category = metric_result.get("category", "unknown")
    parts: list[str] = []

    if category == "answered":
        metric = metric_result.get("metric", "?")
        value = metric_result.get("value", "N/A")
        dims = metric_result.get("dimensions", [])
        time_range = metric_result.get("time_range", "")

        line = f"[Measured] {metric}: {value}"
        if dims:
            line += f" (grouped by {', '.join(dims)})"
        if time_range:
            line += f" — {time_range}"
        parts.append(line)

        rows = metric_result.get("rows", [])
        if rows:
            n = min(len(rows), 3)
            parts.append(f"[Measured] Returned {len(rows)} row(s) — showing first {n}:")
            for r in rows[:n]:
                parts.append(f"  • {r}")
    elif category == "unknown_metric":
        parts.append(
            f"[Measured] Metrics not found: "
            f"{metric_result.get('proposed_metrics', [])}"
        )
    elif category == "ambiguous":
        parts.append(
            f"[Measured] Ambiguous question — matched multiple metrics: "
            f"{metric_result.get('proposed_metrics', [])}"
        )
    elif category == "unsupported_domain":
        parts.append(
            f"[Measured] Domain not supported: "
            f"{metric_result.get('domain', '?')}"
        )
    elif category == "system_error":
        parts.append(
            f"[Measured] System error: "
            f"{metric_result.get('message', 'unknown error')}"
        )
    else:
        parts.append(
            f"[Measured] Unexpected category '{category}' — no metric answer."
        )

    if evidence:
        parts.append("")
        parts.append("[Evidence] Related support tickets:")
        for t in evidence:
            parts.append(
                f"  • [{t.get('id', '?')}] {t.get('topic', '')} "
                f"(severity {t.get('severity', '?')}): "
                f"{t.get('summary', '')[:120]}"
            )

    return "\n".join(parts) if parts else "[Measured] No answer could be synthesized."


def parse_synthesis_output(
    llm_text: str | None,
    metric_result: dict,
    evidence: list[dict],
) -> dict[str, Any]:
    """Parse the LLM response and input data into a ``SynthesisOutput``-compatible dict.

    Fields sourced programmatically (``metric_name``, ``metric_value``,
    ``evidence_cited``) come directly from *metric_result* and
    *evidence*, not from the LLM output.  The ``narrative`` and
    ``claims`` fields come from *llm_text* (or a programmatic fallback
    if *llm_text* is ``None``).

    Parameters
    ----------
    llm_text : str or None
        The LLM's response text, or ``None`` if the call failed.
    metric_result : dict
        The outcome dict from ``query_translator.process_question``.
    evidence : list[dict]
        List of evidence ticket dicts.

    Returns
    -------
    dict
        A dict matching the ``SynthesisOutput`` schema:
        ``narrative``, ``metric_name``, ``metric_value``,
        ``evidence_cited``, ``claims``.
    """
    category = metric_result.get("category", "unknown")

    # Metric info — always from the source, never parsed from LLM text.
    metric_name: str | None = (
        str(metric_result["metric"]) if category == "answered" and "metric" in metric_result else None
    )
    metric_value: str | None = (
        str(metric_result["value"]) if category == "answered" and "value" in metric_result else None
    )

    # Evidence cited — programmatic from the input list.
    evidence_cited: list[str] = [t["id"] for t in evidence if t.get("id")]

    # Narrative and claims from LLM (or fallback).
    if llm_text:
        narrative = llm_text
    else:
        narrative = _fallback_narrative(metric_result, evidence)

    claims = _parse_claims(narrative, metric_name, evidence)

    return {
        "narrative": narrative,
        "metric_name": metric_name,
        "metric_value": metric_value,
        "evidence_cited": evidence_cited,
        "claims": claims,
    }
