"""LangGraph agent loop for conversational-BI metric selection to synthesis.

Nodes: route_to_metric → retrieve_evidence → synthesize.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from langgraph.graph import END, START, StateGraph

from . import catalog_builder, llm_client, query_translator
from .evidence_retriever import EvidenceRetriever
from .synthesis_contract import SynthesisOutput
from .synthesis_prompt import (
    build_synthesis_prompt,
    call_synthesis_llm,
    parse_synthesis_output,
)

logger = logging.getLogger(__name__)


# ── reusable catalog singleton (built once per process) ─────────────────────


def _load_catalog() -> dict[str, Any]:
    """Return a compact catalog (domains, metrics, dimensions).

    Uses ``catalog_builder.build_catalog()`` under the hood.  Raises
    ``FileNotFoundError`` if the dbt manifest has not been parsed.
    """
    return catalog_builder.build_catalog()


# ── Python-accessible state type ────────────────────────────────────────────


class AgentState(dict):
    """State flowing through the agent graph.

    Access fields as dict keys (``state["question"]``) for LangGraph
    compatibility.  The typed properties below serve as documentation
    and convenience getters.

    Attributes:
        question:           Raw natural-language question from the user.
        selected_metrics:   List of metric names the router picked.
        metric_results:     Raw metric values (outcome dict from process_question).
        evidence:           Supporting evidence retrieved for each metric.
        synthesis:          Final natural-language answer.
        category:           Classification of the question (answered / unknown_metric / …).
    """

    question: str
    selected_metrics: list[str]
    metric_results: dict[str, Any]
    evidence: list[dict[str, Any]]
    synthesis: dict[str, Any]  # SynthesisOutput fields
    category: str


# ── nodes ───────────────────────────────────────────────────────────────────


def route_to_metric_node(state: AgentState) -> dict[str, Any]:
    """Route: classify question, select metric, execute MetricFlow query.

    Reads ``question`` from state.  Uses ``llm_client.select_metrics``
    for NL→metric selection, then ``query_translator.process_question``
    to validate, build the MetricFlow command, and execute it.

    Returns ``selected_metrics``, ``metric_results`` (the full five-category
    outcome dict), and ``category``.
    """
    question: str = state.get("question", "").strip()
    if not question:
        logger.warning("route_to_metric_node called with empty question")
        return {
            "selected_metrics": [],
            "metric_results": {"category": "system_error", "message": "Empty question"},
            "category": "system_error",
        }

    # 1. Load catalog
    try:
        catalog = _load_catalog()
    except FileNotFoundError:
        logger.exception("Catalog not available – run ``dbt parse`` first")
        return {
            "selected_metrics": [],
            "metric_results": {
                "category": "system_error",
                "message": "Metric catalog not available. Run ``dbt parse`` first.",
            },
            "category": "system_error",
        }

    # 2. LLM metric selection
    try:
        llm_result = llm_client.select_metrics(question=question, catalog=catalog)
    except Exception:
        logger.exception("LLM metric selection failed")
        return {
            "selected_metrics": [],
            "metric_results": {
                "category": "system_error",
                "message": "LLM metric selection failed",
            },
            "category": "system_error",
        }

    if llm_result is None:
        return {
            "selected_metrics": [],
            "metric_results": {
                "category": "system_error",
                "message": "LLM provider returned no result",
            },
            "category": "system_error",
        }

    # 3. Route through the five-category query translator
    try:
        outcome = query_translator.process_question(
            question=question,
            catalog=catalog,
            llm_result=llm_result,
        )
    except Exception:
        logger.exception("query_translator.process_question raised unexpectedly")
        return {
            "selected_metrics": [],
            "metric_results": {
                "category": "system_error",
                "message": "Internal error during metric query execution",
            },
            "category": "system_error",
        }

    selected = llm_result.get("metrics", [])

    logger.info(
        "route_to_metric: category=%s metrics=%s",
        outcome.get("category"),
        selected,
    )

    return {
        "selected_metrics": selected,
        "metric_results": outcome,
        "category": outcome.get("category", "system_error"),
    }


def retrieve_evidence_node(state: AgentState) -> dict[str, Any]:
    """Evidence: pull supporting tickets for the question.

    Reads ``question`` from state.  Uses ``EvidenceRetriever``
    (keyword index over synthetic support tickets) to find relevant
    evidence.

    Returns ``evidence`` — a list of ticket dicts.
    """
    question: str = state.get("question", "").strip()
    if not question:
        return {"evidence": []}

    try:
        retriever = EvidenceRetriever(top_k=2)
        results = retriever.retrieve(question)
    except Exception:
        logger.exception("Evidence retrieval failed")
        return {"evidence": []}

    logger.info("retrieve_evidence: %d result(s) for question", len(results))
    return {"evidence": results}


def synthesize_node(state: AgentState) -> dict[str, Any]:
    """Synthesis: evidence-grounded narrative with structured output.

    Reads ``metric_results`` and ``evidence`` from state.  Builds a
    synthesis prompt with ``build_synthesis_prompt``, sends it to the
    configured LLM, parses the result into a ``SynthesisOutput``-compatible
    dict, and validates it against the Pydantic contract before returning.

    Returns ``synthesis`` — a dict with keys ``narrative``,
    ``metric_name``, ``metric_value``, ``evidence_cited``, ``claims``.
    """
    metric_results: dict[str, Any] = state.get("metric_results", {})
    evidence: list[dict[str, Any]] = state.get("evidence", [])

    # 1. Build the evidence-grounded prompt
    prompt = build_synthesis_prompt(metric_results, evidence)
    logger.debug("Synthesis prompt (%d chars): %s", len(prompt), prompt[:200])

    # 2. Call the LLM for synthesis
    llm_text = call_synthesis_llm(prompt)

    # 3. Parse into structured output (falls back to programmatic narrative)
    output = parse_synthesis_output(llm_text, metric_results, evidence)

    # 4. Validate against the Pydantic contract
    SynthesisOutput(**output)  # raises pydantic.ValidationError on mismatch

    logger.info(
        "synthesize: narrative=%d chars, claims=%d, evidence_cited=%d, llm=%s",
        len(output["narrative"]),
        len(output["claims"]),
        len(output["evidence_cited"]),
        llm_text is not None,
    )
    return {"synthesis": output}


def router_node(state: AgentState) -> Literal["__end__"]:
    """Router decision: the graph always terminates at ``synthesize`` (Wave 1).

    Future waves may branch to a refinement loop or human-in-the-loop;
    for now every path ends here.
    """
    return END


# ── build graph ────────────────────────────────────────────────────────────

builder = StateGraph(AgentState)

builder.add_node("route_to_metric", route_to_metric_node)
builder.add_node("retrieve_evidence", retrieve_evidence_node)
builder.add_node("synthesize", synthesize_node)

builder.add_edge(START, "route_to_metric")
builder.add_edge("route_to_metric", "retrieve_evidence")
builder.add_edge("retrieve_evidence", "synthesize")
builder.add_conditional_edges("synthesize", router_node)

agent = builder.compile()