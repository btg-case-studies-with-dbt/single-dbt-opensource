"""GovernedMetricTool — the ONLY data access for the investigation loop.

Every number the loop reports flows through this tool, and the tool routes every
request through the SAME Step-1 guards the single-shot ``/query`` path uses
(``query_translator.process_question``): unknown-metric, ambiguity, filter- and
rank-coverage, dimension validation, then ``mf query`` and nothing else. The loop
nodes cannot touch Postgres, emit SQL, or shell out to ``mf`` directly; they emit
a structured :class:`MetricIntent` and receive one of the five governed outcome
categories back.

Governance the tool enforces so the loop can never fabricate:

* **Off-catalog metric** → ``process_question`` returns ``unknown_metric`` (the
  branch abstains).
* **Off-catalog decomposition dimension** → the tool ABSTAINS *before* calling
  ``process_question`` with ``category:"unsupported_domain"``, because
  ``validate_dimensions`` would otherwise silently DROP the ungoverned dimension
  and answer the metric's *grand total* — a total mislabelled as a decomposition.
  This pre-check is what keeps e.g. a ``source_region`` breakdown of tokens (no
  region dimension on the token models) from becoming a fabricated factor.
* **Additivity gate** (``is_additive``): only ``sum``/``count`` measures may claim
  dimensional *contribution*; ratios/averages/extrema report values but never
  "drove it". The loop reads this before it decides to decompose.

The tool returns the governed outcome verbatim plus a replayable ``signature``
(the visited-signature loop-guard key) and the originating intent, so the loop can
build an auditable ``trace[]`` and provenance-link every evidence factor.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from . import query_translator

logger = logging.getLogger(__name__)

# Aggregations whose per-member deltas SUM to the total delta → contribution is
# meaningful. Everything else (average / count_distinct / min / max / median /
# percentile / None-for-ratio) is non-additive.
_ADDITIVE_AGGS = frozenset({"sum", "count"})


@dataclass(frozen=True)
class MetricIntent:
    """A structured, governed request — the only thing a loop node may emit.

    ``group_by`` holds GOVERNED dimension names only (validated by the tool).
    ``time_window`` is either a relative phrase ("last month") or an absolute
    ``"between YYYY-MM-DD and YYYY-MM-DD"`` string — both understood by
    ``query_translator.resolve_time_range``.
    """

    metric: str
    tool: str  # "T1" | "T2" | "T3" | "T4" — cosmetic trace label
    group_by: tuple[str, ...] = ()
    time_window: str = ""
    rank: dict[str, Any] | None = None
    filters: tuple[dict[str, Any], ...] = ()


@dataclass
class ToolResult:
    """The governed outcome of one :class:`MetricIntent` call."""

    intent: MetricIntent
    outcome: dict[str, Any]
    signature: str

    @property
    def category(self) -> str:
        return str(self.outcome.get("category", "system_error"))

    @property
    def answered(self) -> bool:
        return self.category == "answered"

    @property
    def rows(self) -> list[dict[str, Any]]:
        rows = self.outcome.get("rows")
        return rows if isinstance(rows, list) else []


def build_signature(intent: MetricIntent) -> str:
    """Return the visited-signature loop-guard key ``metric|dims|window|rank``.

    Deterministic and order-independent in ``group_by`` so ``[a,b]`` and ``[b,a]``
    collide (they ARE the same governed query). Two calls with the same signature
    are duplicates the loop must refuse.
    """
    dims = ",".join(sorted(intent.group_by))
    rank = ""
    if isinstance(intent.rank, dict):
        rank = f"{intent.rank.get('direction', 'max')}:{intent.rank.get('by_field', '')}"
    return f"{intent.metric}|{dims}|{intent.time_window}|{rank}"


class GovernedMetricTool:
    """Single governed data-access surface for the investigation loop."""

    def __init__(
        self,
        catalog: dict[str, Any],
        *,
        time_override: str | None = None,
        question: str = "",
    ) -> None:
        self.catalog = catalog
        self.time_override = time_override
        # ``question`` is passed to ``check_rank_coverage``'s lexical backstop;
        # drills never carry a superlative frame, so "" is the safe default.
        self.question = question
        self._metric_index = {m["name"]: m for m in catalog.get("metrics", [])}

    # ── catalog helpers ──────────────────────────────────────────────────

    def metric_entry(self, metric: str) -> dict[str, Any] | None:
        return self._metric_index.get(metric)

    def valid_dimensions(self, metric: str) -> list[str]:
        entry = self.metric_entry(metric)
        return list(entry.get("valid_dimensions", [])) if entry else []

    def is_additive(self, metric: str) -> bool:
        """Return whether ``metric`` may claim dimensional contribution.

        Reads the governed ``agg`` attached to the catalog by ``catalog_builder``.
        Additive iff the aggregation is ``sum``/``count``; anything else (ratio,
        average, extrema, or an unknown metric) is non-additive → the loop reports
        values but never a contribution ranking (design §146).
        """
        entry = self.metric_entry(metric)
        if not entry:
            return False
        agg = entry.get("agg")
        return isinstance(agg, str) and agg.lower() in _ADDITIVE_AGGS

    # ── the single call surface ──────────────────────────────────────────

    def run(self, intent: MetricIntent) -> ToolResult:
        """Execute one governed intent and return its outcome + signature.

        Order of governance:

        1. Metric must exist in the catalog (else ``unknown_metric``).
        2. Every ``group_by`` dimension must be governed for that metric, else
           ABSTAIN with ``unsupported_domain`` *before* touching MetricFlow — never
           let ``validate_dimensions`` silently drop it and answer the total.
        3. Route the rest through ``process_question`` (all Step-1 guards + mf).
        """
        signature = build_signature(intent)

        entry = self.metric_entry(intent.metric)
        if entry is None:
            logger.info("GovernedMetricTool ABSTAIN (off-catalog metric): %s", intent.metric)
            return ToolResult(intent, query_translator._unknown_metric([intent.metric]), signature)

        # Decomposition precondition: an ungoverned breakdown dimension abstains
        # here rather than degrading to a mislabelled grand total downstream.
        ungoverned = [d for d in intent.group_by if d not in set(self.valid_dimensions(intent.metric))]
        if ungoverned:
            logger.info(
                "GovernedMetricTool ABSTAIN (ungoverned dim %s for %s)",
                ungoverned,
                intent.metric,
            )
            return ToolResult(intent, self._ungoverned_dimension(intent.metric, ungoverned), signature)

        llm_result = {
            "classification": "answered",
            "metrics": [intent.metric],
            "dimensions": list(intent.group_by),
            "filters": list(intent.filters),
            "rank": intent.rank,
            "time_range": intent.time_window,
            "domain": entry.get("domain"),
        }
        outcome = query_translator.process_question(
            question=self.question,
            catalog=self.catalog,
            llm_result=llm_result,
            time_override=self.time_override,
        )
        return ToolResult(intent, outcome, signature)

    # ── abstain shapes ───────────────────────────────────────────────────

    @staticmethod
    def _ungoverned_dimension(metric: str, dims: list[str]) -> dict[str, Any]:
        """A decomposition over a non-governed dimension: honest abstention.

        Uses ``unsupported_domain`` (a non-answer category) so the trace records a
        truthful non-``answered`` category and the branch yields no evidence — the
        abstain-terminates-branch guarantee.
        """
        return {
            "category": "unsupported_domain",
            "reason": "ungoverned_decomposition_dimension",
            "message": (
                f"'{metric}' cannot be decomposed by {dims} — not a governed "
                "dimension of this metric; branch abstained."
            ),
            "requested_dimensions": dims,
        }


# ── decomposition tool constructors (T1–T4, design §evidence-semantics) ──────
#
# T1/T2/T4 are single governed calls; T3 (contributors_by_delta) is composed by
# the loop from two T2 calls (current & baseline window) subtracted client-side.


def t1_metric_total(metric: str, time_window: str) -> MetricIntent:
    """T1 — the ungrouped total of ``metric`` over ``time_window``."""
    return MetricIntent(metric=metric, tool="T1", time_window=time_window)


def t2_decompose_by_dimension(metric: str, dimension: str, time_window: str) -> MetricIntent:
    """T2 — ``metric`` grouped by one governed ``dimension`` over ``time_window``."""
    return MetricIntent(metric=metric, tool="T2", group_by=(dimension,), time_window=time_window)


def t4_coincident_signal(other_metric: str, time_window: str) -> MetricIntent:
    """T4 — a DIFFERENT governed metric over the same window (parallel signal).

    Returned in a separate list by the loop; "co-moved" is the only relationship
    ever asserted between it and the base metric (design §144).
    """
    return MetricIntent(metric=other_metric, tool="T4", time_window=time_window)
