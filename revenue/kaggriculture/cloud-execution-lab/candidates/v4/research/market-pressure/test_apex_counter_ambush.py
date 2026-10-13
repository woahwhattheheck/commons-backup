from __future__ import annotations

import json
import unittest

import apex_counter_ambush as oracle


class CounterAmbushTests(unittest.TestCase):
    def test_source_contract_constants_match_authenticated_readback(self):
        contract = oracle.APEX_ANTI_CLONE
        self.assertEqual(contract["clone_window"], [2, 10])
        self.assertEqual(contract["clone_min_opponent_hands"], 3)
        self.assertEqual(contract["clone_min_opponent_structures"], 1)
        fert = [e for e in contract["events"] if e["item"] == "FERTILIZER"]
        self.assertEqual(len(fert), 1)
        self.assertEqual(fert[0]["steps"], [522])
        self.assertEqual(fert[0]["max_sell"], 4)

    def test_price_landmarks_match_official_formula(self):
        self.assertEqual(oracle.market_price("FERTILIZER", 10000), 100)
        self.assertEqual(oracle.market_price("FERTILIZER", 10493), 1)
        self.assertEqual(oracle.market_price("STRAWBERRY", 10000), 120)
        self.assertEqual(oracle.market_price("STRAWBERRY", 10062), 1)

    def test_floor_sell_is_a_sink_not_new_market_supply(self):
        row = oracle.sell_block("FERTILIZER", 10493, 4)
        self.assertEqual(row["cash"], 4)
        self.assertEqual(row["market_units_added"], 0)
        self.assertEqual(row["end_inventory"], 10493)

    def test_fertilizer_sponge_is_tiny_at_neutral_inventory(self):
        row = oracle.fertilizer_sponge(10000)
        self.assertEqual(row["apex_market_units_added"], 4)
        self.assertEqual(row["opponent_attributable_units"], 4)
        self.assertEqual(row["direct_quote_savings"], 3)

    def test_fertilizer_floor_has_zero_opponent_subsidy(self):
        row = oracle.fertilizer_sponge(10493)
        self.assertEqual(row["apex_market_units_added"], 0)
        self.assertEqual(row["opponent_attributable_units"], 0)
        self.assertEqual(row["direct_quote_savings"], 0)

    def test_fertilizer_sweep_direct_savings_is_bounded(self):
        rows = [oracle.fertilizer_sponge(inv) for inv in range(9000, 10601)]
        self.assertLessEqual(max(r["direct_quote_savings"] for r in rows), 4)
        self.assertTrue(all(r["apex_market_units_added"] <= 4 for r in rows))

    def test_strawberry_front_run_transfers_cash_at_neutral_inventory(self):
        row = oracle.strawberry_cut(10000)
        self.assertEqual(row["our_cash_gain"], 121)
        self.assertEqual(row["apex_cash_change"], -121)
        self.assertEqual(row["front_run_end_inventory"], row["late_end_inventory"])

    def test_strawberry_floor_has_no_ambush_transfer(self):
        row = oracle.strawberry_cut(10062)
        self.assertEqual(row["our_cash_gain"], 0)
        self.assertEqual(row["apex_cash_change"], 0)

    def test_report_keeps_policy_boundary_explicit(self):
        report = oracle.build_report()
        self.assertEqual(
            report["fertilizer_523_sponge"]["verdict"],
            "falsified_as_massive_opponent_subsidy",
        )
        self.assertEqual(
            report["strawberry_380_402_cut"]["verdict"],
            "mechanically_real_cash_transfer_policy_unproven",
        )
        self.assertFalse(report["promotion"]["runtime_change"])
        self.assertLessEqual(
            report["fertilizer_523_sponge"]["max_observed_direct_quote_savings"],
            4,
        )
        encoded = json.dumps(report, sort_keys=True)
        self.assertEqual(json.loads(encoded)["schema"], report["schema"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
