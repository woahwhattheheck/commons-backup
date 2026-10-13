from __future__ import annotations

import copy
import unittest

from gemini_market_bridge import (
    BRIDGE_SCHEMA,
    UnsupportedBridgeEvidence,
    build_public_partial_timing_envelope,
    sale_horizon_scenarios,
)


def pressure_report(
    *,
    product="WOOL",
    standing=2,
    added=3,
    absorption=1,
    pressure=None,
    start=0,
    end=15,
):
    if pressure is None:
        pressure = max(0, added + standing - absorption)
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
                "public_pressure_units": pressure,
            }
        ],
    }


class GeminiMarketBridgeTests(unittest.TestCase):
    def test_partial_quantity_cross_product(self):
        result = build_public_partial_timing_envelope(pressure_report(), now=7, end=8)
        self.assertEqual(result["schema"], BRIDGE_SCHEMA)
        self.assertEqual(result["scenario_count"], 12)
        self.assertEqual({r["quantity"] for r in result["scenarios"]}, {1, 2})
        self.assertEqual({r["step"] for r in result["scenarios"]}, {7, 8})
        self.assertEqual({r["alignment"] for r in result["scenarios"]}, {"before", "paired", "after"})

    def test_caps_at_existing_sale_horizon_bound(self):
        result = build_public_partial_timing_envelope(pressure_report(standing=250), now=0, end=0)
        self.assertEqual(result["products"][0]["tested_rival_quantity_max"], 100)
        self.assertEqual(result["scenario_count"], 300)

    def test_custom_lower_cap(self):
        result = build_public_partial_timing_envelope(
            pressure_report(standing=20), now=0, end=0, max_rival_quantity=4
        )
        self.assertEqual(result["products"][0]["tested_rival_quantity_max"], 4)
        self.assertEqual(result["scenario_count"], 12)

    def test_zero_public_standing_yield_adds_no_rival_stress(self):
        result = build_public_partial_timing_envelope(pressure_report(standing=0), now=0, end=3)
        self.assertEqual(result["products"], [])
        self.assertEqual(result["scenarios"], [])

    def test_rejects_decision_authority(self):
        report = pressure_report()
        report["decision_authority"] = True
        with self.assertRaises(UnsupportedBridgeEvidence):
            build_public_partial_timing_envelope(report, now=0, end=0)

    def test_rejects_nonresearch_report(self):
        report = pressure_report()
        report["research_only"] = False
        with self.assertRaises(UnsupportedBridgeEvidence):
            build_public_partial_timing_envelope(report, now=0, end=0)

    def test_rejects_schema_drift(self):
        report = pressure_report()
        report["schema"] = "other"
        with self.assertRaises(UnsupportedBridgeEvidence):
            build_public_partial_timing_envelope(report, now=0, end=0)

    def test_rejects_bool_poison(self):
        report = pressure_report()
        report["incremental_sell_rows"][0]["visible_rival_standing_yield"] = True
        with self.assertRaises(UnsupportedBridgeEvidence):
            build_public_partial_timing_envelope(report, now=0, end=0)

    def test_rejects_overlong_timing_window(self):
        with self.assertRaises(UnsupportedBridgeEvidence):
            build_public_partial_timing_envelope(pressure_report(end=16), now=0, end=16)

    def test_rejects_inverted_window(self):
        with self.assertRaises(UnsupportedBridgeEvidence):
            build_public_partial_timing_envelope(pressure_report(), now=3, end=2)

    def test_never_emits_authority(self):
        result = build_public_partial_timing_envelope(pressure_report(), now=0, end=0)
        self.assertIs(result["research_only"], True)
        self.assertIs(result["decision_authority"], False)
        self.assertIs(result["runtime_mutation_authority"], False)
        self.assertIs(result["stress_not_prediction"], True)
        self.assertTrue(all(row["stress_only"] and row["not_prediction"] for row in result["scenarios"]))

    def test_input_nonmutation(self):
        report = pressure_report(standing=4)
        frozen = copy.deepcopy(report)
        build_public_partial_timing_envelope(report, now=0, end=2)
        self.assertEqual(report, frozen)

    def test_product_evidence_is_carried_not_reinterpreted(self):
        result = build_public_partial_timing_envelope(
            pressure_report(product="MILK", standing=3, added=9, absorption=5),
            now=4,
            end=4,
        )
        row = result["products"][0]
        self.assertEqual(row["product"], "MILK")
        self.assertEqual(row["incremental_target_sell_units"], 9)
        self.assertEqual(row["known_current_shop_absorption"], 5)
        self.assertEqual(row["public_pressure_units"], 7)
        self.assertEqual(row["partial_quantities_tested"], 3)

    def test_compiles_exact_sale_horizon_abi(self):
        envelope = build_public_partial_timing_envelope(
            pressure_report(product="MILK", standing=2), now=7, end=7
        )
        compiled = sale_horizon_scenarios(envelope)
        self.assertEqual(len(compiled), 6)
        self.assertIn(("public_partial_MILK_7_1_before", ((7, 1),), "before"), compiled)
        self.assertIn(("public_partial_MILK_7_2_after", ((7, 2),), "after"), compiled)

    def test_compiler_rejects_tampered_authority(self):
        envelope = build_public_partial_timing_envelope(pressure_report(), now=0, end=0)
        envelope["runtime_mutation_authority"] = True
        with self.assertRaises(UnsupportedBridgeEvidence):
            sale_horizon_scenarios(envelope)

    def test_compiler_rejects_duplicate_scenarios(self):
        envelope = build_public_partial_timing_envelope(pressure_report(standing=1), now=0, end=0)
        envelope["scenarios"].append(copy.deepcopy(envelope["scenarios"][0]))
        envelope["scenario_count"] += 1
        with self.assertRaises(UnsupportedBridgeEvidence):
            sale_horizon_scenarios(envelope)

    def test_rejects_window_outside_upstream_pressure_custody(self):
        report = pressure_report(start=7, end=12)
        with self.assertRaises(UnsupportedBridgeEvidence):
            build_public_partial_timing_envelope(report, now=6, end=8)
        with self.assertRaises(UnsupportedBridgeEvidence):
            build_public_partial_timing_envelope(report, now=8, end=13)

    def test_rejects_unknown_product(self):
        with self.assertRaises(UnsupportedBridgeEvidence):
            build_public_partial_timing_envelope(
                pressure_report(product="NOT_A_PRODUCT"), now=0, end=0
            )

    def test_rejects_pressure_algebra_drift(self):
        report = pressure_report(standing=2, added=3, absorption=1, pressure=99)
        with self.assertRaises(UnsupportedBridgeEvidence):
            build_public_partial_timing_envelope(report, now=0, end=0)

    def test_rejects_duplicate_pressure_product_rows(self):
        report = pressure_report()
        report["incremental_sell_rows"].append(copy.deepcopy(report["incremental_sell_rows"][0]))
        with self.assertRaises(UnsupportedBridgeEvidence):
            build_public_partial_timing_envelope(report, now=0, end=0)

    def test_upstream_timing_custody_is_carried(self):
        result = build_public_partial_timing_envelope(
            pressure_report(start=5, end=12), now=7, end=8
        )
        self.assertEqual(result["upstream"]["start"], 5)
        self.assertEqual(result["upstream"]["end"], 12)

    def test_compiler_rejects_scenario_step_outside_envelope(self):
        envelope = build_public_partial_timing_envelope(pressure_report(), now=7, end=7)
        envelope["scenarios"][0]["step"] = 8
        with self.assertRaises(UnsupportedBridgeEvidence):
            sale_horizon_scenarios(envelope)

    def test_compiler_rejects_upstream_custody_tamper(self):
        envelope = build_public_partial_timing_envelope(pressure_report(), now=7, end=7)
        envelope["upstream"]["end"] = 6
        with self.assertRaises(UnsupportedBridgeEvidence):
            sale_horizon_scenarios(envelope)

    def test_compiler_rejects_bool_scenario_count(self):
        envelope = build_public_partial_timing_envelope(pressure_report(), now=0, end=0)
        envelope["scenario_count"] = True
        with self.assertRaises(UnsupportedBridgeEvidence):
            sale_horizon_scenarios(envelope)


if __name__ == "__main__":
    unittest.main()
