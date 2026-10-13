from __future__ import annotations

import unittest

from gemini_market_bridge import (
    UnsupportedBridgeEvidence,
    build_public_partial_timing_envelope,
    sale_horizon_scenarios,
)


def pressure_report(*, product="WOOL", standing=1, start=0, end=15):
    added = 3
    absorption = 1
    return {
        "schema": "titan-v4-public-rival-route-pressure-v1",
        "research_only": True,
        "decision_authority": False,
        "incumbent": "MAIN",
        "target": "YARN",
        "start": start,
        "end": end,
        "incremental_sell_rows": [
            {
                "product": product,
                "incremental_target_sell_units": added,
                "visible_rival_standing_yield": standing,
                "known_current_shop_absorption": absorption,
                "public_pressure_units": max(0, added + standing - absorption),
            }
        ],
    }


class GeminiMarketBridgeScenarioCustodyTests(unittest.TestCase):
    def test_exact_builder_output_still_compiles(self):
        envelope = build_public_partial_timing_envelope(
            pressure_report(standing=2), now=4, end=5
        )
        compiled = sale_horizon_scenarios(envelope)
        self.assertEqual(len(compiled), 12)
        self.assertEqual(len(compiled), envelope["scenario_count"])

    def test_zero_standing_empty_envelope_still_compiles(self):
        envelope = build_public_partial_timing_envelope(
            pressure_report(standing=0), now=4, end=5
        )
        self.assertEqual(envelope["products"], [])
        self.assertEqual(envelope["scenarios"], [])
        self.assertEqual(sale_horizon_scenarios(envelope), [])

    def test_compiler_rejects_quantity_above_carried_product_bound(self):
        envelope = build_public_partial_timing_envelope(
            pressure_report(standing=1), now=0, end=0
        )
        envelope["scenarios"][0]["quantity"] = 2
        with self.assertRaises(UnsupportedBridgeEvidence):
            sale_horizon_scenarios(envelope)

    def test_compiler_rejects_supported_product_without_carried_evidence(self):
        envelope = build_public_partial_timing_envelope(
            pressure_report(product="WOOL", standing=1), now=0, end=0
        )
        envelope["scenarios"][0]["product"] = "MILK"
        with self.assertRaises(UnsupportedBridgeEvidence):
            sale_horizon_scenarios(envelope)

    def test_compiler_rejects_product_bound_above_visible_evidence(self):
        envelope = build_public_partial_timing_envelope(
            pressure_report(standing=1), now=0, end=0
        )
        envelope["products"][0]["tested_rival_quantity_max"] = 2
        envelope["products"][0]["partial_quantities_tested"] = 2
        envelope["products"][0]["scenario_count"] = 6
        with self.assertRaises(UnsupportedBridgeEvidence):
            sale_horizon_scenarios(envelope)

    def test_compiler_rejects_missing_cross_product_row_even_if_count_is_laundered(self):
        envelope = build_public_partial_timing_envelope(
            pressure_report(standing=2), now=0, end=0
        )
        envelope["scenarios"].pop()
        envelope["scenario_count"] -= 1
        with self.assertRaises(UnsupportedBridgeEvidence):
            sale_horizon_scenarios(envelope)

    def test_compiler_rejects_alignment_metadata_tamper(self):
        envelope = build_public_partial_timing_envelope(
            pressure_report(standing=1), now=0, end=0
        )
        envelope["alignments"] = ["before", "paired"]
        with self.assertRaises(UnsupportedBridgeEvidence):
            sale_horizon_scenarios(envelope)


if __name__ == "__main__":
    unittest.main()
