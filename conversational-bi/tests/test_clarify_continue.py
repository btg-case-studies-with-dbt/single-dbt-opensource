"""Unit tests for FR4a/FR4b clarify-and-continue.

Run locally with:

    cd conversational-bi
    .venv/bin/python -m unittest tests.test_clarify_continue -v

The tests stay backend-local: no LLM/provider call, no promptfoo, no network.
"""

from __future__ import annotations

import os
import sys
import unittest

# Make ``backend`` importable when run from the conversational-bi/ directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import query_translator as qt  # noqa: E402


def _catalog() -> dict:
    return {
        "domains": ["Quota", "Revenue"],
        "metrics": [
            {
                "name": "peak_rpm_utilization",
                "label": "Peak RPM Utilization",
                "domain": "Quota",
                "valid_dimensions": ["model_variant"],
            },
            {
                "name": "peak_tpm_utilization",
                "label": "Peak TPM Utilization",
                "domain": "Quota",
                "valid_dimensions": ["model_variant"],
            },
            {
                "name": "total_net_revenue",
                "label": "Total Net Revenue",
                "domain": "Revenue",
                "valid_dimensions": [],
            },
        ],
        "dimensions": [],
    }


def _ambiguous_llm_result(metrics: list[str] | None = None) -> dict:
    return {
        "classification": "ambiguous",
        "metrics": metrics or ["peak_rpm_utilization", "peak_tpm_utilization"],
        "dimensions": ["model_variant"],
        "filters": [],
        "rank": None,
        "time_range": "last week",
        "domain": "Quota",
    }


class ClarifyResponseTests(unittest.TestCase):
    def test_ambiguous_response_adds_catalog_grounded_continuation(self):
        out = qt.process_question(
            "What was quota utilization by model last week?",
            _catalog(),
            llm_result=_ambiguous_llm_result(),
        )

        self.assertEqual(out["category"], "ambiguous")
        self.assertIn("clarifying_question", out)
        self.assertEqual(
            [c["metric"] for c in out["choices"]],
            ["peak_rpm_utilization", "peak_tpm_utilization"],
        )
        self.assertEqual(out["continuation"]["type"], "metric_clarification")
        self.assertEqual(out["continuation"]["rounds_remaining"], 0)
        self.assertNotIn("investigation", out)

    def test_ambiguous_with_unknown_choice_declines_instead_of_clarifying(self):
        out = qt.process_question(
            "What was quota utilization by model last week?",
            _catalog(),
            llm_result=_ambiguous_llm_result(["peak_tpm_utilization", "not_a_metric"]),
        )

        self.assertEqual(out["category"], "unknown_metric")
        self.assertEqual(out["proposed_metrics"], ["not_a_metric"])
        self.assertNotIn("continuation", out)


class ClarificationResolutionTests(unittest.TestCase):
    def _continuation(self) -> dict:
        out = qt.process_question(
            "What was quota utilization by model last week?",
            _catalog(),
            llm_result=_ambiguous_llm_result(),
        )
        return out["continuation"]

    def test_valid_reply_executes_selected_metric(self):
        resolution = qt.resolve_clarification_reply("tpm", self._continuation(), _catalog())
        self.assertTrue(resolution["ok"])
        self.assertEqual(resolution["selected_metric"], "peak_tpm_utilization")

        orig_execute = qt.execute_mf_query
        try:
            qt.execute_mf_query = lambda cmd: (
                0,
                (
                    "metric_time__day  peak_tpm_utilization\n"
                    "---------------  --------------------\n"
                    "2026-01-01       0.42\n"
                ),
                "",
            )
            out = qt.process_question(
                resolution["question"],
                _catalog(),
                llm_result=resolution["llm_result"],
            )
        finally:
            qt.execute_mf_query = orig_execute

        self.assertEqual(out["category"], "answered")
        self.assertEqual(out["metric"], "peak_tpm_utilization")
        self.assertEqual(out["value"], "0.42")

    def test_invalid_reply_declines_without_second_continuation(self):
        resolution = qt.resolve_clarification_reply("gross margin", self._continuation(), _catalog())
        self.assertFalse(resolution["ok"])
        out = resolution["outcome"]
        self.assertEqual(out["category"], "unknown_metric")
        self.assertEqual(out["reason"], "invalid_clarification_reply")
        self.assertNotIn("continuation", out)

    def test_still_ambiguous_reply_declines_without_second_continuation(self):
        resolution = qt.resolve_clarification_reply("utilization", self._continuation(), _catalog())
        self.assertFalse(resolution["ok"])
        out = resolution["outcome"]
        self.assertEqual(out["category"], "ambiguous")
        self.assertEqual(out["reason"], "clarification_reply_ambiguous")
        self.assertNotIn("continuation", out)


if __name__ == "__main__":
    unittest.main()
