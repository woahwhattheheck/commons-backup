#!/usr/bin/env python3
import unittest
import market_baseline as m

class BaselineTests(unittest.TestCase):
    def test_T_normalizes_target_move(self):
        for item, p in m.MARKET_PARAMS.items():
            with self.subTest(item=item):
                expected = round(p["base"] * (1 + p["below_target"]))
                self.assertEqual(m.market_price(item, p["I0"] - p["T"]), expected)

    def test_no_action_unlock_schedule_and_cap(self):
        r = m.simulate(17)
        self.assertEqual([x["day"] for x in r["unlocks"]], [3,6,9,12,15,18,21,24])
        self.assertEqual(len(r["unlocks"]), 8)
        self.assertEqual([x["shop"] for x in r["unlocks"]], [
            "BAKERY", "BRUNCH_SPOT", "PET_CAFE", "PIZZA_SHOP",
            "PET_CAFE", "YARN_STORE", "BAKERY", "YARN_STORE",
        ])

    def test_fertilizer_is_exactly_flat_without_players(self):
        r = m.simulate(17)
        for row in r["steps"]:
            self.assertEqual(row["inventory"]["FERTILIZER"], 10000)
            self.assertEqual(row["prices"]["FERTILIZER"], 100)

    def test_melon_is_center_only(self):
        # No shop consumes MELON. Center ticks at steps 0,24,...696: 30 units.
        for seed in (1,17,6607,100):
            r = m.simulate(seed)
            self.assertEqual(r["steps"][-1]["inventory"]["MELON"], 9970)
            self.assertEqual(r["steps"][-1]["prices"]["MELON"], 280)

    def test_action_step_contract(self):
        r = m.simulate(1)
        self.assertEqual(len(r["steps"]), 719)
        self.assertEqual(r["steps"][0]["step"], 0)
        self.assertEqual(r["steps"][-1]["step"], 718)

    def test_strawberry_and_wool_are_not_hinge(self):
        self.assertEqual(m.MARKET_PARAMS["STRAWBERRY"]["below_func"], "sqrt")
        self.assertEqual(m.MARKET_PARAMS["WOOL"]["below_func"], "log")
        self.assertNotEqual(m.MARKET_PARAMS["STRAWBERRY"]["below_func"], "hinge")
        self.assertNotEqual(m.MARKET_PARAMS["WOOL"]["below_func"], "hinge")

    def test_100_seed_receipt_sentinels(self):
        _, _, report = m.summarize(list(range(1,101)))
        self.assertEqual(report["threshold_crossings"]["STRAWBERRY"]["seeds_reaching_T"], 97)
        self.assertEqual(report["threshold_crossings"]["WOOL"]["seeds_reaching_T"], 55)
        self.assertEqual(report["final"]["MELON"]["price_mean"], 280.0)
        self.assertEqual(report["final"]["FERTILIZER"]["price_mean"], 100.0)

if __name__ == "__main__":
    unittest.main()
