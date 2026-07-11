"""Unit tests for the bounded investigation loop, evidence, linter, termination.

Run::

    cd conversational-bi
    .venv/bin/python -m unittest tests.test_investigation_loop -v

Covers the never-fabricate guarantees the eval gate (investigation_assertions.js)
checks, at the unit level:

* causal-language linter (mirror of the eval's CAUSAL_VALUE_RE / banned keys);
* termination bounds — MAX_STEPS, visited-signature loop-guard, latency deadline;
* evidence is governed + provenance-linked to an ``answered`` step; abstained
  branches contribute nothing;
* the additivity gate blocks contribution on non-additive metrics;
* the base floor is NEVER regressed when investigation fails (orchestrator).
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import agent_graph as ag  # noqa: E402
from backend.governed_metric_tool import (  # noqa: E402
    MetricIntent,
    ToolResult,
    build_signature,
    t2_decompose_by_dimension,
)


# ── a deterministic stub for the governed tool ───────────────────────────────


class StubTool:
    """Minimal GovernedMetricTool stand-in driven by a handler(intent)->outcome."""

    def __init__(self, handler, *, additive=True, dims=None, metrics=None):
        self._handler = handler
        self._additive = additive
        self._dims = dims or []
        self._metrics = set(metrics or [])
        self.calls: list[str] = []

    def is_additive(self, metric):  # noqa: ARG002
        return self._additive

    def valid_dimensions(self, metric):  # noqa: ARG002
        return list(self._dims)

    def metric_entry(self, metric):
        return {"name": metric} if metric in self._metrics else None

    def run(self, intent):
        sig = build_signature(intent)
        self.calls.append(sig)
        return ToolResult(intent, self._handler(intent), sig)


def _answered(metric, rows):
    return {"category": "answered", "metric": metric, "rows": rows}


def _revenue_handler(intent):
    """Governed happy path for metric M decomposed by 'segment'.

    Current window = Dec 2025 (total 15, Enterprise 10 / SMB 5);
    prior window = Nov 2025 (total 10, Enterprise 6 / SMB 4).
    total_delta = +5; Enterprise delta +4 → 80% share.
    """
    is_prior = "2025-12" not in intent.time_window
    if intent.tool == "T1":
        rows = [{"metric_time__month": "2025-11-01" if is_prior else "2025-12-01",
                 "M": "10" if is_prior else "15"}]
        return _answered("M", rows)
    if intent.tool == "T2":
        rows = (
            [{"segment": "Enterprise", "M": "6"}, {"segment": "SMB", "M": "4"}]
            if is_prior
            else [{"segment": "Enterprise", "M": "10"}, {"segment": "SMB", "M": "5"}]
        )
        return _answered("M", rows)
    return _answered(intent.metric, [])


def _base_outcome():
    return {
        "category": "answered",
        "metric": "M",
        "value": "15",
        "dimensions": [],
        "time_range": "2025-12-01 to 2025-12-31",
        "rows": [{"metric_time__month": "2025-12-01", "M": "15"}],
    }


# ── causal linter ────────────────────────────────────────────────────────────


class CausalLinterTests(unittest.TestCase):
    def test_clean_text_passes(self):
        self.assertEqual(ag.lint_causal_text("Revenue moved by -0.3; Enterprise co-moved with 80%."), [])

    def test_causal_connectives_detected(self):
        for bad in [
            "Revenue fell because of Enterprise churn.",
            "The Enterprise segment drove the decline.",
            "The drop was due to fewer requests.",
            "Churn led to the fall.",
            "It resulted in a decline.",
        ]:
            self.assertTrue(ag.lint_causal_text(bad), bad)

    def test_lint_investigation_flags_banned_key(self):
        inv = {"evidence": [{"cause": "Enterprise churn"}]}
        self.assertTrue(any(v.startswith("banned_key:") for v in ag.lint_investigation(inv)))

    def test_lint_investigation_flags_causal_value(self):
        inv = {"summary": "Revenue fell because of churn."}
        self.assertTrue(any(v.startswith("causal_connective:") for v in ag.lint_investigation(inv)))

    def test_causal_word_causal_not_flagged_as_caused(self):
        # 'causal' must NOT trip the '\bcaused\b' pattern (word boundary).
        self.assertEqual(ag.lint_causal_text("These are correlational, not causal, signals."), [])


# ── happy-path governed investigation ────────────────────────────────────────


class HappyPathTests(unittest.TestCase):
    def setUp(self):
        self.tool = StubTool(_revenue_handler, additive=True, dims=["segment"], metrics={"M"})
        self.loop = ag.InvestigationLoop(self.tool, clock=lambda: 0.0, latency_budget=100.0)
        self.inv = self.loop.run(_base_outcome())

    def test_status_investigated(self):
        self.assertEqual(self.inv["status"], "investigated")

    def test_steps_and_trace_agree(self):
        # base(1) + prior total(2) + segment pair(3,4) = 4
        self.assertEqual(self.inv["steps_taken"], 4)
        self.assertEqual(len(self.inv["trace"]), self.inv["steps_taken"])

    def test_no_duplicate_signatures(self):
        sigs = [s["signature"] for s in self.inv["trace"]]
        self.assertEqual(len(set(sigs)), len(sigs))

    def test_every_evidence_factor_is_governed_correlation(self):
        self.assertGreaterEqual(len(self.inv["evidence"]), 2)
        for f in self.inv["evidence"]:
            self.assertIs(f["governed"], True)
            self.assertEqual(f["relationship"], "correlation")
            self.assertIn("source_tool_call_step", f)

    def test_evidence_sources_point_at_answered_steps(self):
        answered = {s["step"] for s in self.inv["trace"] if s["category"] == "answered"}
        for f in self.inv["evidence"]:
            self.assertIn(f["source_tool_call_step"], answered)

    def test_movement_and_contribution_present_and_correct(self):
        mv = next(f for f in self.inv["evidence"] if f["claim_type"] == "movement")
        self.assertEqual(mv["measured_delta"], 5.0)  # 15 - 10
        contrib = next(f for f in self.inv["evidence"] if f["claim_type"] == "dimensional_contribution")
        self.assertEqual(contrib["contributor"], "Enterprise")
        self.assertEqual(contrib["share_of_total_delta"], 0.8)  # 4 / 5

    def test_summary_has_no_causal_language(self):
        self.assertEqual(ag.lint_causal_text(self.inv.get("summary")), [])

    def test_no_banned_keys_anywhere(self):
        self.assertEqual(ag.lint_investigation(self.inv), [])


# ── additivity gate: non-additive base claims no contribution ────────────────


class NonAdditiveTests(unittest.TestCase):
    def test_non_additive_metric_gets_no_dimensional_contribution(self):
        tool = StubTool(_revenue_handler, additive=False, dims=["segment"], metrics={"M"})
        inv = ag.InvestigationLoop(tool, clock=lambda: 0.0, latency_budget=100.0).run(_base_outcome())
        claim_types = {f["claim_type"] for f in inv["evidence"]}
        self.assertNotIn("dimensional_contribution", claim_types)
        # movement (a governed measured value) is still allowed.
        self.assertIn("movement", claim_types)


# ── abstained branch yields no evidence ──────────────────────────────────────


class AbstainBranchTests(unittest.TestCase):
    def test_abstained_decomposition_contributes_no_evidence(self):
        def handler(intent):
            if intent.tool == "T2":  # every decomposition abstains
                return {"category": "unsupported_domain", "metric": intent.metric, "rows": []}
            return _revenue_handler(intent)

        tool = StubTool(handler, additive=True, dims=["segment"], metrics={"M"})
        inv = ag.InvestigationLoop(tool, clock=lambda: 0.0, latency_budget=100.0).run(_base_outcome())
        # No dimensional_contribution factor descends from a non-answered step.
        answered = {s["step"] for s in inv["trace"] if s["category"] == "answered"}
        for f in inv["evidence"]:
            self.assertIn(f["source_tool_call_step"], answered)
        self.assertNotIn("dimensional_contribution", {f["claim_type"] for f in inv["evidence"]})


# ── termination bounds ───────────────────────────────────────────────────────


class TerminationTests(unittest.TestCase):
    def _fresh_loop(self):
        loop = ag.InvestigationLoop(StubTool(_revenue_handler), clock=lambda: 0.0, latency_budget=100.0)
        # Minimal state normally set at the top of run().
        loop._trace, loop._evidence, loop._visited = [], [], set()
        loop._steps, loop._status, loop._stopped = 1, "investigated", None
        loop._deadline = 100.0
        return loop

    def test_max_steps_bounds(self):
        loop = self._fresh_loop()
        loop._steps = ag.MAX_STEPS  # already at the ceiling
        att = loop._attempt(t2_decompose_by_dimension("M", "segment", "w"))
        self.assertEqual(att.status, "bounds")
        self.assertEqual(loop._stopped, "bounds")

    def test_visited_signature_loop_guard(self):
        loop = self._fresh_loop()
        intent = t2_decompose_by_dimension("M", "segment", "w")
        first = loop._attempt(intent)
        second = loop._attempt(intent)  # identical signature
        self.assertEqual(first.status, "ok")
        self.assertEqual(second.status, "repeat")
        self.assertEqual(loop._stopped, "repeat")

    def test_latency_deadline_terminates_partial(self):
        loop = self._fresh_loop()
        loop._deadline = -1.0  # clock (0.0) is already past the deadline
        att = loop._attempt(t2_decompose_by_dimension("M", "segment", "w"))
        self.assertEqual(att.status, "latency")
        self.assertEqual(loop._stopped, "latency")
        self.assertEqual(loop._status, "partial")

    def test_full_run_never_exceeds_max_steps_with_many_dims(self):
        tool = StubTool(_revenue_handler, additive=True, dims=["a", "b", "c", "d"], metrics={"M"})
        inv = ag.InvestigationLoop(tool, clock=lambda: 0.0, latency_budget=100.0).run(_base_outcome())
        self.assertLessEqual(inv["steps_taken"], ag.MAX_STEPS)
        self.assertEqual(len(inv["trace"]), inv["steps_taken"])
        sigs = [s["signature"] for s in inv["trace"]]
        self.assertEqual(len(set(sigs)), len(sigs))


# ── orchestrator: floor preservation + intent gate ──────────────────────────


class OrchestratorTests(unittest.TestCase):
    def test_non_answered_base_short_circuits_no_investigation_key(self):
        def fake_route(question, catalog, llm_result=None, time_override=None):
            return {"category": "unknown_metric", "message": "nope", "proposed_metrics": []}

        orig = ag.route_to_metric_node
        ag.route_to_metric_node = fake_route
        try:
            out = ag.run_query("Why did recurring revenue drop?", {"metrics": []})
        finally:
            ag.route_to_metric_node = orig
        self.assertEqual(out["category"], "unknown_metric")
        self.assertNotIn("investigation", out)  # TR12.2 byte-for-byte

    def test_answered_lookup_gets_not_investigated(self):
        def fake_route(question, catalog, llm_result=None, time_override=None):
            return _base_outcome()

        orig = ag.route_to_metric_node
        ag.route_to_metric_node = fake_route
        try:
            out = ag.run_query("What was total revenue last quarter?", {"metrics": []})
        finally:
            ag.route_to_metric_node = orig
        self.assertEqual(out["investigation"]["status"], "not_investigated")
        self.assertEqual(out["investigation"]["steps_taken"], 0)
        self.assertEqual(out["investigation"]["trace"], [])
        self.assertEqual(out["investigation"]["evidence"], [])

    def test_kill_switch_forces_not_investigated_even_on_investigative(self):
        def fake_route(question, catalog, llm_result=None, time_override=None):
            return _base_outcome()

        orig = ag.route_to_metric_node
        ag.route_to_metric_node = fake_route
        try:
            out = ag.run_query(
                "Why did net revenue change last month?", {"metrics": []}, investigation_enabled=False
            )
        finally:
            ag.route_to_metric_node = orig
        self.assertEqual(out["investigation"]["status"], "not_investigated")

    def test_floor_preserved_when_loop_raises(self):
        def fake_route(question, catalog, llm_result=None, time_override=None):
            return _base_outcome()

        def boom(self, base):  # noqa: ARG001
            raise RuntimeError("loop blew up")

        orig_route, orig_run = ag.route_to_metric_node, ag.InvestigationLoop.run
        ag.route_to_metric_node = fake_route
        ag.InvestigationLoop.run = boom
        try:
            out = ag.run_query("Why did net revenue change last month?", {"metrics": []})
        finally:
            ag.route_to_metric_node = orig_route
            ag.InvestigationLoop.run = orig_run
        # Floor intact ...
        self.assertEqual(out["category"], "answered")
        self.assertEqual(out["metric"], "M")
        self.assertEqual(out["value"], "15")
        # ... and investigation degraded honestly, not fabricated.
        self.assertEqual(out["investigation"]["status"], "partial")
        self.assertEqual(out["investigation"]["evidence"], [])


if __name__ == "__main__":
    unittest.main()
