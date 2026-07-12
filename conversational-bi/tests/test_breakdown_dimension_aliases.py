"""Unit tests for deterministic breakdown dimension aliasing."""

from __future__ import annotations

import os
import sys
import unittest

# Make ``backend`` importable when run from the conversational-bi/ directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import query_translator as qt  # noqa: E402


def _catalog(valid_dimensions: list[str]) -> dict:
    return {
        "domains": ["Revenue"],
        "metrics": [
            {
                "name": "total_net_revenue",
                "label": "Total Net Revenue",
                "domain": "Revenue",
                "valid_dimensions": valid_dimensions,
            },
        ],
        "dimensions": [],
    }


class BreakdownDimensionAliasTests(unittest.TestCase):
    def test_region_phrase_maps_to_prefixed_source_region(self):
        out = qt.infer_breakdown_dimensions(
            ["total_net_revenue"],
            [],
            _catalog(["account_id", "revenue_id__source_region", "model_variant"]),
            "What is total net revenue by region?",
        )
        self.assertEqual(out, ["revenue_id__source_region"])

    def test_bare_source_region_maps_to_prefixed_source_region(self):
        out = qt.infer_breakdown_dimensions(
            ["total_net_revenue"],
            ["source_region"],
            _catalog(["revenue_id__source_region"]),
            "What is total net revenue by source region?",
        )
        self.assertEqual(out, ["revenue_id__source_region"])

    def test_ambiguous_alias_is_not_guessed(self):
        out = qt.infer_breakdown_dimensions(
            ["total_net_revenue"],
            [],
            _catalog(["revenue_id__source_region", "model_variant__source_region"]),
            "What is total net revenue by region?",
        )
        self.assertEqual(out, [])


if __name__ == "__main__":
    unittest.main()
