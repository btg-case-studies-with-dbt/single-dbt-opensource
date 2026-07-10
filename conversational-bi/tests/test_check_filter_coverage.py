"""Unit tests for the filter-coverage guard (never-confidently-wrong increment).

Run with the repo venv (no new dependency — stdlib ``unittest`` only)::

    cd conversational-bi
    .venv/bin/python -m unittest tests.test_check_filter_coverage -v

The guard lives in ``backend.query_translator.check_filter_coverage`` and is
wired into ``process_question`` after the unknown/ambiguous checks and before
the MetricFlow query is built or run. These tests assert the Phase-1 rule:

* ANY non-empty ``filters`` → abstain (the number would be unscoped = wrong),
  keyed off "scope was actually applied to the query" NOT "field is valid".
* empty ``filters`` (``[]`` / ``None`` / absent key) → pass through.
* a breakdown-only question (dimensions set, filters empty) → NO false abstain.
"""

from __future__ import annotations

import os
import sys
import unittest

# Make ``backend`` importable when run from the conversational-bi/ directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import query_translator as qt  # noqa: E402


def _catalog() -> dict:
    """A minimal catalog with the two metrics the failure cases exercise."""
    return {
        "domains": ["Revenue", "Token usage"],
        "metrics": [
            {
                "name": "total_net_revenue",
                "label": "Total Net Revenue",
                "domain": "Revenue",
                "valid_dimensions": ["account", "segment", "model"],
            },
            {
                "name": "total_tokens_consumed",
                "label": "Total Tokens Consumed",
                "domain": "Token usage",
                "valid_dimensions": ["account", "model_variant"],
            },
        ],
        "dimensions": [],
    }


class CheckFilterCoverageTests(unittest.TestCase):
    # ── abstain cases (non-empty filters) ──────────────────────────────

    def test_field_null_filter_abstains_marketplace(self):
        """failure #1: 'from marketplace' — field:null → abstain, populated."""
        filters = [{"field": None, "value": "marketplace", "phrase": "from marketplace"}]
        out = qt.check_filter_coverage("total_net_revenue", filters, _catalog())

        self.assertIsNotNone(out)
        self.assertEqual(out["category"], "unknown_metric")
        self.assertEqual(out["reason"], "unsupported_filter")
        self.assertEqual(out["computable_metric"], "total_net_revenue")
        self.assertEqual(out["available_dimensions"], ["account", "segment", "model"])
        self.assertEqual(out["unsupported_filters"], filters)
        self.assertEqual(out["proposed_metrics"], ["total_net_revenue"])

    def test_field_null_filter_abstains_subscription(self):
        """failure #3: 'from subscriptions' — mechanically identical to #1."""
        filters = [{"field": None, "value": "subscription", "phrase": "from subscriptions"}]
        out = qt.check_filter_coverage("total_net_revenue", filters, _catalog())
        self.assertIsNotNone(out)
        self.assertEqual(out["reason"], "unsupported_filter")

    def test_cs_team_tokens_abstains(self):
        """failure #2 (most dangerous): CS-team scope on total_tokens_consumed."""
        filters = [
            {
                "field": None,
                "value": "Customer Success team",
                "phrase": "billed to the Customer Success team",
            }
        ]
        out = qt.check_filter_coverage("total_tokens_consumed", filters, _catalog())
        self.assertIsNotNone(out)
        self.assertEqual(out["computable_metric"], "total_tokens_consumed")
        self.assertEqual(out["available_dimensions"], ["account", "model_variant"])

    def test_valid_field_still_abstains_in_phase1(self):
        """Keyed off 'scope applied to query', NOT 'field is a valid dimension'.

        A filter naming a REAL catalog dimension still yields a wrong answer
        today because nothing pushes it down — so it must still abstain.
        """
        filters = [{"field": "segment", "value": "enterprise", "phrase": "for enterprise"}]
        out = qt.check_filter_coverage("total_net_revenue", filters, _catalog())
        self.assertIsNotNone(out)
        self.assertEqual(out["reason"], "unsupported_filter")

    # ── message: explain and show its work ─────────────────────────────

    def test_message_shows_dimensions_and_names_value(self):
        filters = [{"field": None, "value": "marketplace", "phrase": "from marketplace"}]
        out = qt.check_filter_coverage("total_net_revenue", filters, _catalog())
        msg = out["message"]
        self.assertIn("total_net_revenue", msg)          # (1) computable metric
        self.assertIn("account, segment, model", msg)    # (2) available dimensions
        self.assertIn("marketplace", msg)                # (3) the unmatched value

    # ── pass-through cases (empty / absent) ────────────────────────────

    def test_empty_filters_pass_through(self):
        self.assertIsNone(qt.check_filter_coverage("total_net_revenue", [], _catalog()))

    def test_none_filters_pass_through(self):
        """Absent 'filters' key is read as None by the caller → treated as []."""
        self.assertIsNone(qt.check_filter_coverage("total_net_revenue", None, _catalog()))

    def test_malformed_filters_non_list_pass_through(self):
        """A malformed non-list payload is treated as no usable scope (no crash)."""
        self.assertIsNone(qt.check_filter_coverage("total_net_revenue", {}, _catalog()))  # type: ignore[arg-type]


class ProcessQuestionIntegrationTests(unittest.TestCase):
    """Guard wired into process_question: abstain fires; breakdown still answers."""

    def test_scope_filter_routes_to_abstain(self):
        llm_result = {
            "classification": "answered",
            "metrics": ["total_net_revenue"],
            "dimensions": [],
            "filters": [{"field": None, "value": "marketplace", "phrase": "from marketplace"}],
            "time_range": "",
            "domain": "Revenue",
        }
        out = qt.process_question("value from marketplace", _catalog(), llm_result=llm_result)
        self.assertEqual(out["category"], "unknown_metric")
        self.assertEqual(out["reason"], "unsupported_filter")

    def test_breakdown_only_does_not_falsely_abstain(self):
        """'revenue by product line' — a BREAKDOWN (unexpressible dim), no filter.

        The guard must NOT abstain; validate_dimensions drops the unexpressible
        breakdown and the metric total still answers. We stop before mf execution
        by asserting the guard did not short-circuit into an abstain — the
        outcome is NOT the unsupported_filter object. (mf is not invoked in unit
        context; a system_error from a missing mf binary is acceptable here — the
        point is that the filter guard did not fire.)
        """
        llm_result = {
            "classification": "answered",
            "metrics": ["total_net_revenue"],
            "dimensions": ["product_line"],  # not in valid_dimensions → dropped
            "filters": [],
            "time_range": "this year",
            "domain": "Revenue",
        }
        out = qt.process_question("revenue by product line", _catalog(), llm_result=llm_result)
        # The guard must not have converted this into a filter abstention.
        self.assertNotEqual(out.get("reason"), "unsupported_filter")
        self.assertIn(out["category"], {"answered", "system_error"})


if __name__ == "__main__":
    unittest.main()
