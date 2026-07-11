"""Unit tests for the deterministic investigative-intent classifier (TR12.5).

Run with the repo venv (stdlib ``unittest`` only)::

    cd conversational-bi
    .venv/bin/python -m unittest tests.test_intent_classifier -v

The classifier is the Decision-1(A) trigger: investigative intent runs the loop;
everything else keeps the single-shot path. The ground truth is the ai-architect's
``eval/intent_classifier_fixtures.csv`` — all 20 rows must classify correctly, or
the gate red-lights. These tests read that CSV directly so the fixture stays the
single source of truth.
"""

from __future__ import annotations

import csv
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import intent_classifier as ic  # noqa: E402

_FIXTURES = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "eval",
    "intent_classifier_fixtures.csv",
)


def _load_fixtures() -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    with open(_FIXTURES, newline="") as f:
        for row in csv.DictReader(f):
            rows.append(
                (row["question"], row["expected_intent"].strip().lower(), row.get("note", ""))
            )
    return rows


class IntentFixtureTests(unittest.TestCase):
    """Every fixture row must classify exactly as the ai-architect expects."""

    def test_all_twenty_fixtures_match(self):
        fixtures = _load_fixtures()
        self.assertEqual(len(fixtures), 20, "expected 20 fixture rows")
        mismatches = []
        for question, expected, note in fixtures:
            got = "investigative" if ic.is_investigative(question) else "lookup"
            if got != expected:
                mismatches.append(f"[{note}] {question!r}: expected {expected}, got {got}")
        self.assertEqual(mismatches, [], "intent misclassifications:\n" + "\n".join(mismatches))

    def test_investigative_rows_true(self):
        for question, expected, note in _load_fixtures():
            if expected == "investigative":
                self.assertTrue(ic.is_investigative(question), f"[{note}] {question!r}")

    def test_lookup_rows_false(self):
        for question, expected, note in _load_fixtures():
            if expected == "lookup":
                self.assertFalse(ic.is_investigative(question), f"[{note}] {question!r}")


class IntentEdgeCaseTests(unittest.TestCase):
    """Guard the tricky false-positive / false-negative boundaries."""

    def test_empty_and_none_default_to_lookup(self):
        self.assertFalse(ic.is_investigative(""))
        self.assertFalse(ic.is_investigative("   "))
        self.assertFalse(ic.is_investigative(None))

    def test_argmax_superlative_is_not_investigative(self):
        # "most"/"fewest" are governed lookups (check_rank_coverage owns them).
        self.assertFalse(ic.is_investigative("Which model used the most tokens last week?"))
        self.assertFalse(ic.is_investigative("Which customer used the fewest tokens last week?"))

    def test_comparison_metric_is_not_investigative(self):
        # "growth"/"compared" alone must never trigger the loop.
        self.assertFalse(ic.is_investigative("Revenue growth rate compared to last quarter?"))

    def test_plain_group_by_is_not_investigative(self):
        self.assertFalse(ic.is_investigative("Show me net revenue by product line for this year"))

    def test_break_down_needs_a_movement_noun(self):
        # A bare group-by "break down" is a lookup; only a movement makes it investigative.
        self.assertFalse(ic.is_investigative("Break down net revenue by segment"))
        self.assertTrue(ic.is_investigative("Break down the movement in gross revenue this quarter."))

    def test_strong_explanatory_triggers(self):
        for q in [
            "Why did total net revenue change last month?",
            "What drove the change in total tokens consumed last week?",
            "What caused revenue to fall last quarter?",
            "What's behind the shift in input tokens last week?",
            "Explain the drop in gross revenue this month.",
            "What accounts for the increase in token usage last week?",
            "What is driving the decline in net revenue?",
            "Reason for the spike in output tokens last week?",
        ]:
            self.assertTrue(ic.is_investigative(q), q)


if __name__ == "__main__":
    unittest.main()
