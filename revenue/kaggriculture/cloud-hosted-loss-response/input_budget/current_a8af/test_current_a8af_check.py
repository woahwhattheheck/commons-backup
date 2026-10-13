# SPDX-License-Identifier: Apache-2.0
import importlib.util
import json
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("current_a8af_check", HERE / "check_current_a8af.py")
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


class CurrentA8afCheckTests(unittest.TestCase):
    def test_market_shape_ignores_only_fertilizer_quantity(self):
        a = {"market": [["SELL", "WHEAT", 3], ["BUY_PRODUCT", "FERTILIZER", 9]]}
        b = {"market": [["SELL", "WHEAT", 3], ["BUY_PRODUCT", "FERTILIZER", 8]]}
        self.assertEqual(check.market_shape(a), check.market_shape(b))
        b["market"][0][2] = 4
        self.assertNotEqual(check.market_shape(a), check.market_shape(b))

    def test_market_shape_preserves_fertilizer_operation_and_slot(self):
        buy = {"market": [[], ["BUY_PRODUCT", "FERTILIZER", 9]]}
        sell = {"market": [[], ["SELL", "FERTILIZER", 9]]}
        moved = {"market": [["BUY_PRODUCT", "FERTILIZER", 9], []]}
        self.assertNotEqual(check.market_shape(buy), check.market_shape(sell))
        self.assertNotEqual(check.market_shape(buy), check.market_shape(moved))

    def test_physical_farms_ignores_money_only(self):
        base = {"farms": [{"money": 10, "hands": [[1, 2]], "tiles": [None]}]}
        other = {"farms": [{"money": 99, "hands": [[1, 2]], "tiles": [None]}]}
        self.assertEqual(check.physical_farms(base), check.physical_farms(other))
        other["farms"][0]["hands"] = []
        self.assertNotEqual(check.physical_farms(base), check.physical_farms(other))

    def test_nonfert_private_ignores_only_fertilizer(self):
        a = {"private": {"shed": {"FERTILIZER": 9, "WHEAT": 2},
                           "inventories": [{"FERTILIZER": 1, "WHEAT": 3}],
                           "seeds": {"CARROT": 4}}}
        b = {"private": {"shed": {"FERTILIZER": 7, "WHEAT": 2},
                           "inventories": [{"FERTILIZER": 0, "WHEAT": 3}],
                           "seeds": {"CARROT": 4}}}
        self.assertEqual(check.nonfert_private(a), check.nonfert_private(b))
        b["private"]["shed"]["WHEAT"] = 1
        self.assertNotEqual(check.nonfert_private(a), check.nonfert_private(b))

    def test_fert_buy_requires_one_buy(self):
        self.assertEqual(check.fert_buy({"market": [["BUY_PRODUCT", "FERTILIZER", 8]]}), 8)
        self.assertIsNone(check.fert_buy({"market": []}))
        self.assertIsNone(check.fert_buy({"market": [["BUY_PRODUCT", "FERTILIZER", 8],
                                                       ["BUY_PRODUCT", "FERTILIZER", 1]]}))

    def test_verdict(self):
        self.assertEqual(check.verdict(2, 1), "W")
        self.assertEqual(check.verdict(1, 2), "L")
        self.assertEqual(check.verdict(2, 2), "T")

    def test_retained_result_contract(self):
        result = json.loads((HERE / "RESULTS.json").read_text())
        self.assertTrue(result["complete"])
        self.assertEqual(result["archive_sha256"], check.EXPECTED_ARCHIVE)
        self.assertEqual(result["games"], 16)
        self.assertEqual(result["pairs"], 8)
        self.assertEqual(result["active_pairs"], 6)
        self.assertEqual(result["inactive_pairs"], 2)
        self.assertEqual(result["flips"], {})
        self.assertEqual(result["worker_action_checks"], 11504)
        self.assertEqual(result["physical_farm_checks"], 11504)

    def test_every_active_pair_is_one_unit_and_final_day_only(self):
        result = json.loads((HERE / "RESULTS.json").read_text())
        active = [row for row in result["pairs_detail"] if row["active"]]
        self.assertEqual(len(active), 6)
        for row in active:
            self.assertEqual(row["requested_fertilizer"] - row["retained_fertilizer"], 1)
            self.assertTrue(row["exact_action_diff_steps"])
            self.assertGreaterEqual(min(row["exact_action_diff_steps"]), 696)
        for row in result["pairs_detail"]:
            if not row["active"]:
                self.assertEqual(row["exact_action_diff_steps"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
