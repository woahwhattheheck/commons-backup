#!/usr/bin/env python3
from __future__ import annotations
import unittest

import market_pressure as m


class MarketPressureTests(unittest.TestCase):
    def test_exact_starting_cash_capacity(self):
        t = m.max_affordable_wheat()
        self.assertEqual(t.quantity, 95)
        self.assertEqual(t.money, 2995)
        self.assertEqual(t.end_inventory, 9905)

    def test_self_roundtrip_is_zero(self):
        for q in (1, 10, 64, 95, 100, 300):
            with self.subTest(q=q):
                r = m.self_roundtrip(q)
                self.assertEqual(r["profit"], 0)
                self.assertEqual(r["final_inventory"], m.MARKET_I0)

    def test_external_demand_creates_symmetric_transfer(self):
        r = m.front_run_external_demand(64, 64)
        self.assertEqual(r["our_profit"], 280)
        self.assertEqual(r["rival_surcharge"], 280)
        self.assertEqual(r["margin_swing"], 560)

    def test_starting_cash_pressure_case(self):
        r = m.front_run_external_demand(95, 95)
        self.assertEqual(r["our_cost"], 2995)
        self.assertEqual(r["our_profit"], 510)
        self.assertEqual(r["rival_surcharge"], 510)
        self.assertEqual(r["margin_swing"], 1020)
        self.assertEqual(r["final_inventory"], 9905)

    def test_pressure_agent_uses_only_legal_direct_buy(self):
        obs = {
            "player": 0, "hour": 0,
            "farms": [{"money": 3000, "farmer": [4, 4], "hands": []}],
            "private": {"shed": {}, "inventories": [{}]},
            "market": {"inventory": {"WHEAT": 10000}},
        }
        a = m.pressure_agent(obs)
        self.assertEqual(a["market"], [["BUY_PRODUCT", "WHEAT", 95]])
        self.assertEqual(a["farmer"], ["PASS"])

    def test_pickup_frees_shed_before_buy(self):
        obs = {
            "player": 0, "hour": 1,
            "farms": [{"money": 5000, "farmer": [4, 4], "hands": []}],
            "private": {"shed": {"WHEAT": 70, "FERTILIZER": 30}, "inventories": [{}]},
            "market": {"inventory": {"WHEAT": 9905}},
        }
        a = m.pressure_agent(obs)
        self.assertEqual(a["farmer"], ["PICKUP", "WHEAT", 70])
        self.assertEqual(a["market"][0][:2], ["BUY_PRODUCT", "WHEAT"])
        self.assertLessEqual(a["market"][0][2], 70)

    def test_late_unwind_places_then_sells(self):
        obs = {
            "player": 0, "hour": 20,
            "farms": [{"money": 5, "farmer": [4, 4], "hands": [[5, 4]]}],
            "private": {"shed": {"FERTILIZER": 20}, "inventories": [{"WHEAT": 95}, {}]},
            "market": {"inventory": {"WHEAT": 9905}},
        }
        a = m.pressure_agent(obs)
        self.assertEqual(a["farmer"], ["PLACE", "WHEAT", 80])
        self.assertEqual(a["market"], [["SELL", "WHEAT", 80]])
        self.assertEqual(a["hands"], [["PASS"]])

    def test_non_adjacent_never_assumes_pickup_or_place(self):
        base = {
            "player": 0,
            "farms": [{"money": 3000, "farmer": [0, 0], "hands": []}],
            "private": {"shed": {"WHEAT": 95}, "inventories": [{"WHEAT": 50}]},
            "market": {"inventory": {"WHEAT": 9905}},
        }
        self.assertEqual(m.pressure_agent(dict(base, hour=1))["farmer"], ["PASS"])
        self.assertEqual(m.pressure_agent(dict(base, hour=20))["farmer"], ["PASS"])

    def test_bundle_records_falsifications(self):
        b = m.result_bundle()
        self.assertIn("rejected", b["interpretation"]["hinge_direct_buy"])
        self.assertIn("price pressure", b["interpretation"]["wheat_starvation"])


if __name__ == "__main__":
    unittest.main()
