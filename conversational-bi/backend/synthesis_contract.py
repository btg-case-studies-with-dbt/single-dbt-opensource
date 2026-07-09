"""Pydantic contract for the synthesis output.

``SynthesisOutput`` defines the structured schema returned by the
synthesis node.  Every field is accessible as a dict-key for LangGraph
compatibility; the model is used for validation at the node boundary.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SynthesisOutput(BaseModel):
    """Structured output from the evidence-grounded synthesis step.

    The ``narrative`` is the final answer text delivered to the user,
    with inline ``[Measured]`` / ``[Evidence]`` tier labels for
    provenance transparency.  The structured fields (``metric_name``,
    ``metric_value``, ``evidence_cited``, ``claims``) give downstream
    consumers a machine-parseable view of the same information.

    Attributes
    ----------
    narrative : str
        The final answer text, including inline ``[Measured]`` and
        ``[Evidence]`` labels.
    metric_name : str | None
        Name of the primary metric (``None`` when the category is not
        ``answered``).
    metric_value : str | None
        String representation of the metric's value (``None`` when the
        category is not ``answered``).
    evidence_cited : list[str]
        Ticket IDs referenced in the narrative, drawn from the evidence
        input (not parsed from the LLM output).
    claims : list[dict]
        Individual claims extracted from the narrative.  Each entry has
        ``text`` (str), ``tier`` (``"measured"`` or ``"evidence"``),
        and ``source`` (metric name or ticket ID).
    """

    narrative: str
    metric_name: str | None = None
    metric_value: str | None = None
    evidence_cited: list[str] = Field(default_factory=list)
    claims: list[dict] = Field(default_factory=list)
