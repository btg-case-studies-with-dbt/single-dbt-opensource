"""Unit tests for the rank / argmax coverage guard (never-confidently-wrong).

Run with the repo venv (no new dependency — stdlib ``unittest`` only)::

    cd conversational-bi
    .venv/bin/python -m unittest tests.test_check_rank_coverage -v

The guard lives in ``backend.query_translator.check_rank_coverage`` and is wired
into ``process_question`` RIGHT AFTER the filter-coverage guard and BEFORE the
MetricFlow query is built or run. These tests assert the additive contract:

* ``rank`` absent AND no superlative in the question → pass through (``None``).
* ``rank`` absent BUT a superlative frame is present → abstain (lexical backstop).
* "peak" is a metric name, NOT a superlative → it must NOT fire the backstop.
* ``rank`` present with a null / ungoverned ``by_field`` → abstain, showing the
  governed dimensions that DO exist (``unsupported_argmax_dimension``).
* a valid rank → the argmax is computed over the parsed rows (``apply_argmax``),
  picking the true max (desc) / min (asc), and ``by_field`` is auto-added to the
  group-by when the model omitted it (``rank_group_by``).
"""

from __future__ import annotations

import os
import sys
import unittest

# Make ``backend`` importable when run from the conversational-bi/ directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import query_translator as qt  # noqa: E402


def _catalog() -> dict:
    """A minimal catalog with a metric that can be ranked by ``model``."""
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
                "valid_dimensions": ["account", "model"],
            },
        ],
        "dimensions": [],
    }


def _rows() -> list[dict]:
    """Parsed rows whose metric column carries a clear max (45810) and min (30012)."""
    return [
        {"model": "gpt-4o", "total_tokens_consumed": 42929},
        {"model": "opus", "total_tokens_consumed": 45810},
        {"model": "haiku", "total_tokens_consumed": 30012},
    ]


class CheckRankCoverageTests(unittest.TestCase):
    # ── pass-through: no rank, no superlative ──────────────────────────

    def test_no_rank_no_superlative_passes_through(self):
        """The regression guarantee: additive, byte-for-byte pass-through."""
        out = qt.check_rank_coverage(
            "total_tokens_consumed", None, [], _catalog(), "how many tokens this week"
        )
        self.assertIsNone(out)

    # ── abstain: rank present, by_field null ───────────────────────────

    def test_null_by_field_abstains(self):
        rank = {"by_field": None, "direction": "max"}
        out = qt.check_rank_coverage("total_tokens_consumed", rank, [], _catalog())
        self.assertIsNotNone(out)
        self.assertEqual(out["category"], "unknown_metric")
        self.assertEqual(out["reason"], "unsupported_argmax_dimension")
        self.assertEqual(out["computable_metric"], "total_tokens_consumed")
        self.assertEqual(out["available_dimensions"], ["account", "model"])
        self.assertEqual(out["proposed_metrics"], ["total_tokens_consumed"])
        self.assertFalse(out["backstop"])

    # ── abstain: rank present, by_field ungoverned ─────────────────────

    def test_ungoverned_by_field_abstains_and_shows_dimensions(self):
        rank = {"by_field": "region", "direction": "max"}  # region ∉ valid_dimensions
        out = qt.check_rank_coverage("total_tokens_consumed", rank, [], _catalog())
        self.assertIsNotNone(out)
        self.assertEqual(out["reason"], "unsupported_argmax_dimension")
        self.assertEqual(out["requested_rank_field"], "region")
        # Message shows its work: names the metric AND the governed dimensions.
        msg = out["message"]
        self.assertIn("total_tokens_consumed", msg)
        self.assertIn("account, model", msg)
        self.assertIn("region", msg)

    # ── abstain: lexical backstop (no rank, superlative present) ───────

    def test_lexical_backstop_abstains(self):
        out = qt.check_rank_coverage(
            "total_tokens_consumed",
            None,
            [],
            _catalog(),
            "which model consumed the most tokens this month",
        )
        self.assertIsNotNone(out)
        self.assertEqual(out["reason"], "unsupported_argmax_dimension")
        self.assertTrue(out["backstop"])
        self.assertIn("account, model", out["message"])

    def test_backstop_fires_on_top_but_not_on_substring(self):
        """'top' fires; 'topic' (word-boundary) must NOT."""
        fired = qt.check_rank_coverage(
            "total_tokens_consumed", None, [], _catalog(), "top model by tokens"
        )
        self.assertIsNotNone(fired)
        not_fired = qt.check_rank_coverage(
            "total_tokens_consumed", None, [], _catalog(), "tokens by topic segment"
        )
        self.assertIsNone(not_fired)

    # ── HARD CONSTRAINT: "peak" is a metric name, not a superlative ────

    def test_peak_does_not_trigger_backstop(self):
        """'peak' (peak_rpm/peak_tpm, fixture 'quota peak') must pass through."""
        out = qt.check_rank_coverage(
            "total_tokens_consumed",
            None,
            [],
            _catalog(),
            "what was the peak tpm last week",
        )
        self.assertIsNone(out)

    # ── valid rank passes the guard (argmax handled by the caller) ─────

    def test_valid_rank_passes_guard(self):
        rank = {"by_field": "model", "direction": "max"}
        out = qt.check_rank_coverage("total_tokens_consumed", rank, ["model"], _catalog())
        self.assertIsNone(out)


class ApplyArgmaxTests(unittest.TestCase):
    """THIS code computes the ranking over parsed rows."""

    def test_argmax_picks_true_max(self):
        rank = {"by_field": "model", "direction": "max"}
        sorted_rows, winner, value = qt.apply_argmax(_rows(), "total_tokens_consumed", rank)
        self.assertEqual(value, 45810)                 # the true max
        self.assertIs(winner, sorted_rows[0])          # winner is surfaced as rows[0]
        self.assertEqual(winner["model"], "opus")
        # Rows are sorted descending by the metric column.
        self.assertEqual(
            [r["total_tokens_consumed"] for r in sorted_rows], [45810, 42929, 30012]
        )

    def test_argmin_picks_true_min(self):
        rank = {"by_field": "model", "direction": "min"}
        sorted_rows, winner, value = qt.apply_argmax(_rows(), "total_tokens_consumed", rank)
        self.assertEqual(value, 30012)                 # the true min
        self.assertEqual(winner["model"], "haiku")
        self.assertEqual(
            [r["total_tokens_consumed"] for r in sorted_rows], [30012, 42929, 45810]
        )

    def test_direction_defaults_to_max(self):
        sorted_rows, _winner, value = qt.apply_argmax(
            _rows(), "total_tokens_consumed", {"by_field": "model"}
        )
        self.assertEqual(value, 45810)
        self.assertEqual(sorted_rows[0]["total_tokens_consumed"], 45810)

    def test_comma_grouped_strings_rank_numerically(self):
        """MetricFlow cells arrive as strings; ranking must be numeric, not lexical."""
        rows = [
            {"model": "a", "total_tokens_consumed": "9,000"},
            {"model": "b", "total_tokens_consumed": "45,810"},
        ]
        _sorted, winner, value = qt.apply_argmax(rows, "total_tokens_consumed", {"direction": "max"})
        self.assertEqual(winner["model"], "b")
        self.assertEqual(value, "45,810")  # raw source cell is surfaced, not the float

    def test_empty_rows_yield_no_winner(self):
        sorted_rows, winner, value = qt.apply_argmax([], "total_tokens_consumed", {})
        self.assertEqual(sorted_rows, [])
        self.assertIsNone(winner)
        self.assertIsNone(value)


class RankGroupByTests(unittest.TestCase):
    def test_by_field_auto_added_when_omitted(self):
        rank = {"by_field": "model", "direction": "max"}
        self.assertEqual(qt.rank_group_by(["account"], rank), ["account", "model"])

    def test_by_field_not_duplicated_when_present(self):
        rank = {"by_field": "model", "direction": "max"}
        self.assertEqual(qt.rank_group_by(["model"], rank), ["model"])

    def test_malformed_rank_leaves_group_by_unchanged(self):
        self.assertEqual(qt.rank_group_by(["account"], None), ["account"])


class ProcessQuestionIntegrationTests(unittest.TestCase):
    """Guard wired into process_question: abstains fire BEFORE mf executes."""

    def test_ungoverned_rank_routes_to_abstain(self):
        llm_result = {
            "classification": "answered",
            "metrics": ["total_tokens_consumed"],
            "dimensions": [],
            "filters": [],
            "rank": {"by_field": "region", "direction": "max"},
            "time_range": "",
            "domain": "Token usage",
        }
        out = qt.process_question(
            "which region used the most tokens", _catalog(), llm_result=llm_result
        )
        self.assertEqual(out["category"], "unknown_metric")
        self.assertEqual(out["reason"], "unsupported_argmax_dimension")

    def test_backstop_routes_to_abstain(self):
        """No rank emitted, but the question is an unmistakable superlative."""
        llm_result = {
            "classification": "answered",
            "metrics": ["total_tokens_consumed"],
            "dimensions": [],
            "filters": [],
            "time_range": "",
            "domain": "Token usage",
        }
        out = qt.process_question(
            "which model consumed the most tokens", _catalog(), llm_result=llm_result
        )
        self.assertEqual(out["category"], "unknown_metric")
        self.assertEqual(out["reason"], "unsupported_argmax_dimension")
        self.assertTrue(out["backstop"])

    def test_no_rank_plain_question_does_not_abstain(self):
        """Additive guarantee: a non-ranking question never hits the rank guard.

        We stop before mf execution by asserting the guard did not short-circuit
        into a rank abstention. (mf is not invoked in unit context; a
        system_error from a missing mf binary is acceptable — the point is the
        rank guard did not fire.)
        """
        llm_result = {
            "classification": "answered",
            "metrics": ["total_tokens_consumed"],
            "dimensions": [],
            "filters": [],
            "time_range": "this month",
            "domain": "Token usage",
        }
        out = qt.process_question("how many tokens this month", _catalog(), llm_result=llm_result)
        self.assertNotEqual(out.get("reason"), "unsupported_argmax_dimension")
        self.assertIn(out["category"], {"answered", "system_error"})


if __name__ == "__main__":
    unittest.main()
