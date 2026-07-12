"""Unit tests for deterministic supported-domain metric-gap overrides."""

from __future__ import annotations

import os
import sys
import unittest

# Make ``backend`` importable when run from the conversational-bi/ directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import query_translator as qt  # noqa: E402


def _catalog() -> dict:
    return {
        "domains": ["Revenue", "Token usage", "Quota"],
        "metrics": [
            {
                "name": "total_net_revenue",
                "label": "Total Net Revenue",
                "domain": "Revenue",
                "valid_dimensions": ["revenue_id__source_region"],
            }
        ],
        "dimensions": [],
    }


class KnownMetricGapTests(unittest.TestCase):
    def test_profit_margin_drift_to_unsupported_domain_becomes_unknown_metric(self):
        llm_result = {
            "classification": "unsupported_domain",
            "metrics": [],
            "dimensions": [],
            "filters": [],
            "time_range": "",
            "domain": "Finance",
        }
        out = qt.process_question("What is our profit margin by region?", _catalog(), llm_result)
        self.assertEqual(out["category"], "unknown_metric")
        self.assertIn("profit margin", out["message"])

    def test_known_metric_gap_overrides_bad_valid_metric_guess(self):
        llm_result = {
            "classification": "answered",
            "metrics": ["total_net_revenue"],
            "dimensions": [],
            "filters": [],
            "time_range": "",
            "domain": "Revenue",
        }
        out = qt.process_question("Revenue growth rate compared to last quarter?", _catalog(), llm_result)
        self.assertEqual(out["category"], "unknown_metric")
        self.assertIn("growth rate", out["message"])

    def test_true_unsupported_domain_stays_unsupported(self):
        llm_result = {
            "classification": "unsupported_domain",
            "metrics": [],
            "dimensions": [],
            "filters": [],
            "time_range": "",
            "domain": "HR",
        }
        out = qt.process_question("What is the employee headcount by department?", _catalog(), llm_result)
        self.assertEqual(out["category"], "unsupported_domain")


if __name__ == "__main__":
    unittest.main()
