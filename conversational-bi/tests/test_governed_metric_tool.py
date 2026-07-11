"""Unit tests for GovernedMetricTool — the loop's only governed data access.

Run::

    cd conversational-bi
    .venv/bin/python -m unittest tests.test_governed_metric_tool -v

Focus (no live MetricFlow — ``process_question`` is exercised only on the guard
paths that abstain BEFORE mf executes, mirroring the existing test style):

* off-catalog metric → ``unknown_metric`` (branch abstains);
* off-catalog decomposition dimension → ABSTAINS with ``unsupported_domain``
  *before* mf, never silently dropping the dim and answering the grand total;
* the additivity gate reads the governed ``agg`` (sum = additive; average = not);
* the visited-signature builder is deterministic and group-by-order-independent.
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import governed_metric_tool as gmt  # noqa: E402


def _catalog() -> dict:
    return {
        "domains": ["Revenue", "Token usage"],
        "metrics": [
            {
                "name": "total_net_revenue",
                "domain": "Revenue",
                "agg": "sum",
                "valid_dimensions": ["account_id", "account_id__segment"],
            },
            {
                "name": "error_rate",
                "domain": "Token usage",
                "agg": "average",
                "valid_dimensions": ["account_id", "model_variant"],
            },
            {
                "name": "tokens_per_request",
                "domain": "Token usage",
                "agg": None,  # ratio metric — non-additive
                "valid_dimensions": ["model_variant"],
            },
        ],
        "dimensions": [],
    }


class AdditivityGateTests(unittest.TestCase):
    def test_sum_metric_is_additive(self):
        tool = gmt.GovernedMetricTool(_catalog())
        self.assertTrue(tool.is_additive("total_net_revenue"))

    def test_average_metric_is_not_additive(self):
        tool = gmt.GovernedMetricTool(_catalog())
        self.assertFalse(tool.is_additive("error_rate"))

    def test_ratio_metric_is_not_additive(self):
        tool = gmt.GovernedMetricTool(_catalog())
        self.assertFalse(tool.is_additive("tokens_per_request"))

    def test_unknown_metric_is_not_additive(self):
        tool = gmt.GovernedMetricTool(_catalog())
        self.assertFalse(tool.is_additive("nope_not_a_metric"))


class GovernanceAbstainTests(unittest.TestCase):
    def test_off_catalog_metric_abstains(self):
        tool = gmt.GovernedMetricTool(_catalog())
        res = tool.run(gmt.t1_metric_total("recurring_revenue", "last month"))
        self.assertFalse(res.answered)
        self.assertEqual(res.category, "unknown_metric")

    def test_ungoverned_decomposition_dimension_abstains_before_mf(self):
        """The critical guard: an ungoverned breakdown dim must NOT degrade to the
        grand total — it abstains here with a non-answered category."""
        tool = gmt.GovernedMetricTool(_catalog())
        res = tool.run(gmt.t2_decompose_by_dimension("total_net_revenue", "source_region", "last month"))
        self.assertFalse(res.answered)
        self.assertEqual(res.category, "unsupported_domain")
        self.assertEqual(res.outcome.get("reason"), "ungoverned_decomposition_dimension")
        self.assertIn("source_region", res.outcome.get("requested_dimensions", []))

    def test_governed_dimension_does_not_abstain_at_precondition(self):
        """A governed dim passes the precondition (it will then reach mf, which is
        absent in unit context → system_error is acceptable; the point is the
        tool did NOT abstain at the ungoverned-dim precondition)."""
        tool = gmt.GovernedMetricTool(_catalog())
        res = tool.run(gmt.t2_decompose_by_dimension("total_net_revenue", "account_id__segment", "last month"))
        self.assertNotEqual(res.outcome.get("reason"), "ungoverned_decomposition_dimension")
        self.assertIn(res.category, {"answered", "system_error"})


class SignatureTests(unittest.TestCase):
    def test_signature_is_group_by_order_independent(self):
        a = gmt.MetricIntent(metric="m", tool="T2", group_by=("x", "y"), time_window="w")
        b = gmt.MetricIntent(metric="m", tool="T2", group_by=("y", "x"), time_window="w")
        self.assertEqual(gmt.build_signature(a), gmt.build_signature(b))

    def test_signature_distinguishes_window(self):
        a = gmt.MetricIntent(metric="m", tool="T1", time_window="dec")
        b = gmt.MetricIntent(metric="m", tool="T1", time_window="nov")
        self.assertNotEqual(gmt.build_signature(a), gmt.build_signature(b))

    def test_signature_encodes_rank(self):
        a = gmt.MetricIntent(metric="m", tool="T1", time_window="w")
        b = gmt.MetricIntent(metric="m", tool="T1", time_window="w", rank={"by_field": "model", "direction": "max"})
        self.assertNotEqual(gmt.build_signature(a), gmt.build_signature(b))


if __name__ == "__main__":
    unittest.main()
