"""Bounded agentic investigation loop — Evidence-from-Governed-Data.

Design: ``docs/05.DETAILED_DESIGN.md`` §"Agentic Investigation Loop +
Evidence-from-Governed-Data" (APPROVED gate-2), contract ``docs/04.TRD.md``
TR12.1–TR12.8, acceptance target ``eval/investigation_assertions.js``.

**PIVOT (this rewrite):** the prior ticket-RAG nodes (`retrieve_evidence_node`,
ticket synthesis tiers) are deleted at the root — they retrieved a fabricated
support-ticket corpus. Evidence is now a **governed decomposition of the metric
movement itself**: every number is a governed MetricFlow query issued through
:class:`GovernedMetricTool`, and causation is structurally unrepresentable.

Salvage note (implementation structure, not a governed-behavior change): the
LangGraph ``StateGraph`` runtime is replaced by an explicit, deterministic
controller (:class:`InvestigationLoop`). A bounded, dynamically-sized
investigation with a per-step deadline/loop-guard/abstain check is materially
clearer and — critically — directly unit-testable for its termination bounds
(TR12.6) than a cyclic graph with a recursion limit. The node decomposition is
preserved as methods (``_plan`` → ``run`` → ``_attempt``/observe → decide →
``_synthesize``), and ``route_to_metric_node`` is kept as the base-answer node.
This is a two-way door; the loop can be re-wrapped in a StateGraph later.

Non-negotiables enforced here:
* The base answer is the FLOOR and is never regressed by investigation.
* A non-``answered`` base short-circuits — no investigation block emitted.
* Every evidence factor is ``governed:true`` / ``relationship:"correlation"`` and
  provenance-linked to an ``answered`` trace step; abstained branches yield none.
* No causal field exists; a post-synthesis linter scans the narrative and drops
  it toward abstention rather than emit a causal connective.
"""

from __future__ import annotations

import datetime
import logging
import os
import re
import time
from typing import Any, Callable

from . import query_translator
from .governed_metric_tool import (
    GovernedMetricTool,
    MetricIntent,
    build_signature,
    t1_metric_total,
    t2_decompose_by_dimension,
    t4_coincident_signal,
)

logger = logging.getLogger(__name__)

# ── termination bounds (TR12.6, design §loop-bounds) ─────────────────────────
MAX_STEPS = 6  # 1 base + ≤5 drills
MAX_DEPTH = 3
# Cumulative wall-clock ceiling; kept under the TR11 30s p95 budget with margin
# so the loop terminates as ``partial``/``latency`` rather than overrunning.
LATENCY_BUDGET_SECONDS = float(os.environ.get("INVESTIGATION_LATENCY_BUDGET", "28"))

# ── causal-language linter (mirror of eval/investigation_assertions.js §145) ─
# Kept byte-identical to the acceptance gate so a summary this loop emits can
# never pass our linter yet fail the eval's ``noCausalLanguage``.
CAUSAL_VALUE_RE = re.compile(
    r"\b(caused|because\s+of|because|drove|driven\s+by|led\s+to|due\s+to|resulted\s+in|responsible\s+for)\b",
    re.IGNORECASE,
)
BANNED_KEYS = frozenset(
    {"cause", "driver", "drivers", "root_cause", "causal", "causality", "narrative", "why"}
)

# Best-effort coincident-signal siblings (a DIFFERENT governed metric over the
# same window — "co-moved" is the only asserted relationship). Only fired when
# the sibling exists in the catalog and step budget remains.
_COINCIDENT_SIBLING = {
    "total_net_revenue": "total_gross_revenue",
    "total_gross_revenue": "total_net_revenue",
    "total_tokens_consumed": "total_api_requests",
    "total_input_tokens": "total_output_tokens",
    "total_output_tokens": "total_input_tokens",
    "error_rate": "total_api_requests",
}


# ── salvaged base-answer node ────────────────────────────────────────────────


def route_to_metric_node(
    question: str,
    catalog: dict[str, Any],
    llm_result: dict[str, Any] | None = None,
    time_override: str | None = None,
) -> dict[str, Any]:
    """Compute the base (floor) answer — the single-shot five-category outcome.

    Thin wrapper over ``query_translator.process_question`` preserved from the
    prior graph. This is the guaranteed floor: investigation is strictly additive
    on top of whatever this returns and may never corrupt it.
    """
    return query_translator.process_question(
        question=question,
        catalog=catalog,
        llm_result=llm_result,
        time_override=time_override,
    )


# ── linter helpers ───────────────────────────────────────────────────────────


def lint_causal_text(text: str | None) -> list[str]:
    """Return every causal connective found in ``text`` (empty = clean)."""
    if not text:
        return []
    return [m if isinstance(m, str) else m[0] for m in CAUSAL_VALUE_RE.findall(text)]


def _collect_keys(obj: Any, out: list[str]) -> list[str]:
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.append(str(k).lower())
            _collect_keys(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _collect_keys(v, out)
    return out


def _collect_strings(obj: Any, out: list[str]) -> list[str]:
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            _collect_strings(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _collect_strings(v, out)
    return out


def lint_investigation(investigation: dict[str, Any]) -> list[str]:
    """Defensive scan of a whole investigation block for causal leakage.

    Returns a list of violations (banned key names or causal connectives in any
    string value). Used as a belt-and-suspenders gate before the block is
    returned; the loop constructs its own fields so this should be empty, but a
    non-empty result forces the summary to be dropped (downgrade toward
    abstention) rather than shipped.
    """
    violations: list[str] = []
    for k in _collect_keys(investigation, []):
        if k in BANNED_KEYS:
            violations.append(f"banned_key:{k}")
    for s in _collect_strings(investigation, []):
        for hit in lint_causal_text(s):
            violations.append(f"causal_connective:{hit}")
    return violations


# ── window arithmetic ────────────────────────────────────────────────────────


def _parse_window(time_range: str | None) -> tuple[datetime.date | None, datetime.date | None]:
    """Parse ``"YYYY-MM-DD to YYYY-MM-DD"`` (the base outcome's time_range)."""
    if not time_range:
        return (None, None)
    m = re.search(r"(\d{4}-\d{2}-\d{2})\s+to\s+(\d{4}-\d{2}-\d{2})", time_range)
    if not m:
        return (None, None)
    try:
        return (datetime.date.fromisoformat(m.group(1)), datetime.date.fromisoformat(m.group(2)))
    except ValueError:
        return (None, None)


def _prior_window(
    start: datetime.date, end: datetime.date
) -> tuple[datetime.date, datetime.date]:
    """Same-length window immediately preceding ``[start, end]``."""
    length = (end - start).days
    prior_end = start - datetime.timedelta(days=1)
    prior_start = prior_end - datetime.timedelta(days=length)
    return (prior_start, prior_end)


def _window_str(start: datetime.date, end: datetime.date) -> str:
    """Absolute ``between … and …`` form understood by ``resolve_time_range``."""
    return f"between {start.isoformat()} and {end.isoformat()}"


# ── row math ─────────────────────────────────────────────────────────────────


def _sum_metric(rows: list[dict[str, Any]], metric: str) -> float:
    """Sum the metric column across all (period) rows → window total."""
    total = 0.0
    for r in rows:
        n = query_translator._to_number(r.get(metric))
        if n is not None:
            total += n
    return total


def _member_column(rows: list[dict[str, Any]], metric: str, dim: str) -> str | None:
    """Resolve the parsed-row key that carries the decomposition member.

    Prefers an exact ``dim`` header; otherwise the first column that is neither
    the metric nor a ``metric_time*`` grain column.
    """
    if not rows:
        return None
    keys = list(rows[0].keys())
    if dim in keys:
        return dim
    for k in keys:
        if k == metric or k.startswith("metric_time"):
            continue
        return k
    return None


def _member_totals(rows: list[dict[str, Any]], metric: str, dim: str) -> dict[str, float]:
    """``{member: window_total}`` for a decomposition, summed across periods."""
    col = _member_column(rows, metric, dim)
    if col is None:
        return {}
    totals: dict[str, float] = {}
    for r in rows:
        member = str(r.get(col))
        n = query_translator._to_number(r.get(metric))
        if n is not None:
            totals[member] = totals.get(member, 0.0) + n
    return totals


# ── the loop ─────────────────────────────────────────────────────────────────


class _Attempt:
    """Outcome of one guarded drill attempt."""

    __slots__ = ("status", "result", "step")

    def __init__(self, status: str, result: Any = None, step: int | None = None) -> None:
        self.status = status  # "ok" | "bounds" | "latency" | "repeat"
        self.result = result
        self.step = step


class InvestigationLoop:
    """Bounded investigator: plan → run governed metric → observe → decide.

    Inject ``tool`` (a :class:`GovernedMetricTool` or a stub) and ``clock`` for
    deterministic unit tests of the termination bounds.
    """

    def __init__(
        self,
        tool: GovernedMetricTool,
        *,
        clock: Callable[[], float] | None = None,
        latency_budget: float = LATENCY_BUDGET_SECONDS,
    ) -> None:
        self.tool = tool
        self._clock = clock or time.monotonic
        self._latency_budget = latency_budget

    # ── public entry ─────────────────────────────────────────────────────

    def run(self, base_outcome: dict[str, Any]) -> dict[str, Any]:
        """Investigate an ``answered`` base outcome; return the ``investigation`` block.

        The caller guarantees ``base_outcome["category"] == "answered"`` and that
        the trigger classified the question as investigative.
        """
        self._trace: list[dict[str, Any]] = []
        self._evidence: list[dict[str, Any]] = []
        self._visited: set[str] = set()
        self._steps = 0
        self._status = "investigated"
        self._stopped: str | None = None
        self._deadline = self._clock() + self._latency_budget

        metric = base_outcome.get("metric")
        base_rows = base_outcome.get("rows") or []

        # Step 1: the base answer IS the floor and the first governed step.
        base_intent = t1_metric_total(str(metric), str(base_outcome.get("time_range", "")))
        base_sig = build_signature(base_intent)
        self._visited.add(base_sig)
        self._steps = 1
        self._trace.append(self._trace_record(1, base_intent, base_sig, "answered"))

        base_total = _sum_metric(base_rows, str(metric))
        cs, ce = _parse_window(base_outcome.get("time_range"))
        have_window = cs is not None and ce is not None

        self._plan_and_execute(str(metric), base_total, cs, ce, have_window)

        if self._stopped is None:
            self._stopped = "no_warranted_follow_up"

        summary = self._synthesize(str(metric))
        block = {
            "status": self._status,
            "steps_taken": self._steps,
            "stopped_reason": self._stopped,
            "trace": self._trace,
            "evidence": self._evidence,
        }
        if summary is not None:
            block["summary"] = summary

        # Defensive final linter pass: causation must be structurally absent.
        violations = lint_investigation(block)
        if violations:
            logger.error("Causal leakage in investigation block %s — dropping summary", violations)
            block.pop("summary", None)
        return block

    # ── plan / decide ────────────────────────────────────────────────────

    def _plan_and_execute(
        self,
        metric: str,
        base_total: float,
        cs: datetime.date | None,
        ce: datetime.date | None,
        have_window: bool,
    ) -> None:
        """Deterministic plan: movement → dimensional contribution → coincident."""
        prior_total: float | None = None

        # ── movement (needs the prior-period total) ──
        if have_window:
            ps, pe = _prior_window(cs, ce)  # type: ignore[arg-type]
            att = self._attempt(t1_metric_total(metric, _window_str(ps, pe)))
            if att.status == "ok" and att.result.answered:
                prior_total = _sum_metric(att.result.rows, metric)
                self._emit_movement(metric, base_total, prior_total, source_step=1)

        # ── dimensional contribution (additive metrics only; needs a delta) ──
        additive = self.tool.is_additive(metric)
        if additive and have_window and prior_total is not None:
            total_delta = base_total - prior_total
            ps, pe = _prior_window(cs, ce)  # type: ignore[arg-type]
            for dim in self._dim_priority(metric):
                if self._budget_left() < 2:  # a T3 pair needs two steps
                    self._stopped = self._stopped or "bounds"
                    break
                cur = self._attempt(t2_decompose_by_dimension(metric, dim, _window_str(cs, ce)))  # type: ignore[arg-type]
                if cur.status != "ok":
                    break  # bounds / latency / repeat already recorded
                pri = self._attempt(t2_decompose_by_dimension(metric, dim, _window_str(ps, pe)))
                if pri.status != "ok":
                    break
                if cur.result.answered and pri.result.answered and total_delta != 0:
                    self._emit_contribution(
                        dim, cur.result, pri.result, total_delta, source_step=cur.step
                    )

        # ── coincident signal (best-effort, if budget remains) ──
        if have_window and self._budget_left() >= 1:
            sibling = _COINCIDENT_SIBLING.get(metric)
            if sibling and self.tool.metric_entry(sibling):
                att = self._attempt(t4_coincident_signal(sibling, _window_str(cs, ce)))  # type: ignore[arg-type]
                if att.status == "ok" and att.result.answered:
                    self._emit_coincident(sibling, att.result, source_step=att.step)

    def _attempt(self, intent: MetricIntent) -> _Attempt:
        """Run one drill under the deadline / bounds / loop-guard, record its trace step.

        Precedence when several bounds trip at once: latency > bounds > repeat.
        """
        if self._clock() >= self._deadline:
            self._stopped = "latency"
            self._status = "partial"
            return _Attempt("latency")
        if self._steps >= MAX_STEPS:
            self._stopped = self._stopped or "bounds"
            return _Attempt("bounds")
        sig = build_signature(intent)
        if sig in self._visited:
            self._stopped = self._stopped or "repeat"
            return _Attempt("repeat")

        result = self.tool.run(intent)
        self._visited.add(sig)
        self._steps += 1
        step = self._steps
        self._trace.append(self._trace_record(step, intent, sig, result.category))
        if result.category == "system_error":
            self._status = "partial"  # a step failed → warranted evidence may be missing
        return _Attempt("ok", result, step)

    # ── evidence emitters ────────────────────────────────────────────────

    def _emit_movement(
        self, metric: str, current_total: float, prior_total: float, source_step: int
    ) -> None:
        delta = current_total - prior_total
        pct = (delta / prior_total) if prior_total not in (0, None) else None
        self._evidence.append(
            {
                "relationship": "correlation",
                "governed": True,
                "source_tool_call_step": source_step,
                "claim_type": "movement",
                "measured_delta": round(delta, 4),
                "pct_change": (round(pct, 4) if pct is not None else None),
                "baseline_value": round(prior_total, 4),
                "current_value": round(current_total, 4),
            }
        )
        self._mark_produced(source_step)

    def _emit_contribution(
        self,
        dim: str,
        cur_result: Any,
        pri_result: Any,
        total_delta: float,
        source_step: int,
    ) -> None:
        cur_members = _member_totals(cur_result.rows, cur_result.intent.metric, dim)
        pri_members = _member_totals(pri_result.rows, pri_result.intent.metric, dim)
        if not cur_members and not pri_members:
            return  # nothing governed to attribute → abstain from a factor
        members = set(cur_members) | set(pri_members)
        deltas = sorted(
            ((m, cur_members.get(m, 0.0) - pri_members.get(m, 0.0)) for m in members),
            key=lambda pair: abs(pair[1]),
            reverse=True,
        )
        if not deltas or total_delta == 0:
            return
        top_member, top_delta = deltas[0]
        self._evidence.append(
            {
                "relationship": "correlation",
                "governed": True,
                "source_tool_call_step": source_step,
                "claim_type": "dimensional_contribution",
                "dimension": dim,
                "contributor": str(top_member),
                "measured_delta": round(top_delta, 4),
                "share_of_total_delta": round(top_delta / total_delta, 4),
            }
        )
        self._mark_produced(source_step)

    def _emit_coincident(self, sibling: str, result: Any, source_step: int) -> None:
        self._evidence.append(
            {
                "relationship": "correlation",
                "governed": True,
                "source_tool_call_step": source_step,
                "claim_type": "coincident_signal",
                "coincident_metric": sibling,
                "measured_value": round(_sum_metric(result.rows, sibling), 4),
            }
        )
        self._mark_produced(source_step)

    # ── synthesis (programmatic, correlational, linted) ──────────────────

    def _synthesize(self, metric: str) -> str | None:
        parts: list[str] = []
        mv = next((e for e in self._evidence if e["claim_type"] == "movement"), None)
        if mv is not None:
            pct = ""
            if mv.get("pct_change") is not None:
                pct = f" ({mv['pct_change'] * 100:.1f}%)"
            parts.append(f"{metric} moved by {mv['measured_delta']}{pct} between the prior and current window.")
        for e in self._evidence:
            if e["claim_type"] == "dimensional_contribution":
                share = round(e["share_of_total_delta"] * 100, 1)
                parts.append(f"By {e['dimension']}, {e['contributor']} co-moved with {share}% of the movement.")
        for e in self._evidence:
            if e["claim_type"] == "coincident_signal":
                parts.append(
                    f"{e['coincident_metric']} registered {e['measured_value']} over the same window (parallel signal)."
                )
        if not parts:
            return None
        parts.append("These are governed correlations over the same window, not attributions.")
        text = " ".join(parts)
        if lint_causal_text(text):
            logger.warning("Synthesized summary tripped the causal linter — dropping it")
            return None
        return text

    # ── small helpers ────────────────────────────────────────────────────

    def _budget_left(self) -> int:
        return MAX_STEPS - self._steps

    def _dim_priority(self, metric: str) -> list[str]:
        """Governed dims, de-prioritising the high-cardinality bare ``account_id``."""
        dims = self.tool.valid_dimensions(metric)
        return sorted(dims, key=lambda d: (d == "account_id", d))

    def _mark_produced(self, step: int) -> None:
        for rec in self._trace:
            if rec["step"] == step:
                rec["produced_evidence"] = True

    @staticmethod
    def _trace_record(step: int, intent: MetricIntent, signature: str, category: str) -> dict[str, Any]:
        return {
            "step": step,
            "tool": intent.tool,
            "intent": {
                "metric": intent.metric,
                "group_by": list(intent.group_by),
                "time_window": intent.time_window,
                "rank": intent.rank,
                "filters": list(intent.filters),
            },
            "signature": signature,
            "category": category,
            "produced_evidence": False,
        }


# ── orchestrator: the /query intent gate ─────────────────────────────────────


def _not_investigated_block() -> dict[str, Any]:
    """The additive block a plain-lookup ``answered`` response carries (TR12.5)."""
    return {
        "status": "not_investigated",
        "steps_taken": 0,
        "stopped_reason": None,
        "trace": [],
        "evidence": [],
    }


def run_query(
    question: str,
    catalog: dict[str, Any],
    llm_result: dict[str, Any] | None = None,
    time_override: str | None = None,
    *,
    investigation_enabled: bool = True,
) -> dict[str, Any]:
    """Single entry the API calls: base floor + (conditionally) the loop.

    Decision 1 = A. Only an ``answered`` base with investigative intent runs the
    loop; every other path returns today's single-shot outcome. The four
    non-answer categories are returned byte-for-byte with NO investigation key
    (TR12.2); a plain-lookup ``answered`` carries ``not_investigated`` (TR12.5).
    """
    from . import intent_classifier  # noqa: PLC0415 – late import keeps startup lean

    base = route_to_metric_node(question, catalog, llm_result, time_override)

    # Non-answered base → short-circuit; no investigation key at all (TR12.2).
    if base.get("category") != "answered":
        return base

    # Plain lookup (or the kill-switch is off) → single-shot shape + annotation.
    if not investigation_enabled or not intent_classifier.is_investigative(question):
        base["investigation"] = _not_investigated_block()
        return base

    # Investigative + answered → run the bounded loop. It must NEVER regress the
    # floor: on any unexpected failure, fall back to a partial, honest block.
    try:
        tool = GovernedMetricTool(catalog, time_override=time_override, question="")
        base["investigation"] = InvestigationLoop(tool).run(base)
    except Exception:  # noqa: BLE001 – floor preservation is the whole point
        logger.exception("Investigation loop failed; preserving the base floor")
        base["investigation"] = {
            "status": "partial",
            "steps_taken": 1,
            "stopped_reason": "error",
            "trace": [
                {
                    "step": 1,
                    "tool": "T1",
                    "intent": {
                        "metric": base.get("metric"),
                        "group_by": [],
                        "time_window": base.get("time_range", ""),
                        "rank": None,
                        "filters": [],
                    },
                    "signature": f"{base.get('metric')}||{base.get('time_range', '')}|",
                    "category": "answered",
                    "produced_evidence": False,
                }
            ],
            "evidence": [],
            "note": "investigation aborted after the base answer; floor preserved",
        }
    return base
