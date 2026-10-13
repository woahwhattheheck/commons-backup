#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import engine_bound_baseline as baseline
import town_wheat_timing as timing

ENGINE = (Path(os.environ["TITAN_ENGINE"]) if "TITAN_ENGINE" in os.environ else HERE.parents[3] / "reference" / "engine" / "kaggriculture.py")


class TownWheatTimingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = baseline.load_engine(ENGINE)

    def test_exact_shop_demand_with_duplicates_and_center(self):
        e = self.engine
        shops = ["BAKERY", "BAKERY", "YARN_STORE", "PET_CAFE"]
        self.assertEqual(timing.town_demand_units(e, 100, shops), 2)
        self.assertEqual(timing.town_demand_units(e, 96, shops), 3)
        self.assertEqual(timing.town_demand_units(e, 101, shops), 0)

    def test_unknown_shop_fails_closed(self):
        with self.assertRaises(ValueError):
            timing.town_demand_units(self.engine, 100, ["NOT_A_SHOP"])

    def test_engine_impossible_shop_count_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "official cap"):
            timing.town_demand_units(self.engine, 100, ["BAKERY"] * (self.engine.MAX_SHOP_INSTANCES + 1))

    def test_constructed_five_shop_witness_is_42_dollars(self):
        e = self.engine
        shops = ["BAKERY", "PIZZA_SHOP", "BRUNCH_SPOT", "ICE_CREAM_SHOP", "FARMERS_MARKET"]
        demand = timing.town_demand_units(e, 100, shops)
        self.assertEqual(demand, 5)
        p = timing.procurement_window(e, 10000, 100, demand)
        r = timing.round_trip_window(e, 10000, 100, demand)
        self.assertEqual(p["buy_before_cost"], 3170)
        self.assertEqual(p["buy_after_cost"], 3212)
        self.assertEqual(p["buy_before_savings"], 42)
        self.assertEqual(r["profit"], 42)
        self.assertEqual(r["final_public_inventory"], 9995)

    def test_official_market_then_town_phase_witness(self):
        from types import SimpleNamespace
        e = self.engine
        cfg = {"boardSize":10,"startingMoney":3000,"turnsPerDay":24,"episodeSteps":720,
               "shedCapacity":100,"farmHandCostMult":1,"maxMarketOrdersPerTurn":10,
               "townShopSellInterval":4,"townCenterSellInterval":24}
        farms = [e._new_farm(10, 3000) for _ in range(2)]
        private = [e._new_private() for _ in range(2)]
        market, town = e._new_market(), e._new_town()
        town["unlocked_shops"] = ["BAKERY","PIZZA_SHOP","BRUNCH_SPOT","ICE_CREAM_SHOP","FARMERS_MARKET"]
        market["inventory"]["WHEAT"] = 10000
        e._refresh_prices(market)
        farms[0]["money"] = 10000
        states = []
        for player in range(2):
            obs = SimpleNamespace(player=player, farms=farms, market=market, town=town, private=private[player])
            states.append(SimpleNamespace(observation=obs, action={}))
        env = SimpleNamespace(configuration=cfg, info={"seed": 1})
        states[0].action = {"market": [["BUY_PRODUCT", "WHEAT", 100]]}
        states[1].action = {"market": []}
        e._process_market(states, env)
        e._town_consume(env, states, 100)
        self.assertEqual(farms[0]["money"], 6830)
        self.assertEqual(market["inventory"]["WHEAT"], 9895)
        self.assertEqual(private[0]["shed"].get("WHEAT"), 100)
        states[0].action = {"market": [["SELL", "WHEAT", 100]]}
        e._process_market(states, env)
        self.assertEqual(farms[0]["money"], 10042)
        self.assertEqual(market["inventory"]["WHEAT"], 9995)
        self.assertEqual(private[0]["shed"].get("WHEAT", 0), 0)

    def test_unchanged_market_round_trip_is_zero(self):
        r = timing.round_trip_window(self.engine, 10000, 100, 0)
        self.assertEqual(r["profit"], 0)
        self.assertEqual(r["final_public_inventory"], 10000)

    def test_buy_before_never_worse_on_standard_curve_grid(self):
        rows = timing.audit_grid(self.engine)
        self.assertEqual(len(rows), 6 * 10 * 5)
        self.assertTrue(all(row["procurement_savings"] >= 0 for row in rows))
        self.assertTrue(all(row["round_trip_profit"] >= 0 for row in rows))

    def test_off_tick_has_no_window(self):
        obs = {"step": 101, "market": {"inventory": {"WHEAT": 10000}},
               "town": {"unlocked_shops": ["BAKERY"]}}
        out = timing.opportunity(self.engine, obs, quantity=10)
        self.assertEqual(out["status"], "NO_TOWN_WHEAT_DEMAND_THIS_STEP")
        self.assertEqual(out["town_demand_units"], 0)
        self.assertEqual(out["buy_before_savings"], 0)

    def test_demand_tick_public_oracle(self):
        obs = {"step": 100, "market": {"inventory": {"WHEAT": 10000}},
               "town": {"unlocked_shops": ["BAKERY", "PIZZA_SHOP"]}}
        out = timing.opportunity(self.engine, obs, quantity=20)
        self.assertEqual(out["status"], "DEMAND_WINDOW")
        self.assertEqual(out["town_demand_units"], 2)
        self.assertGreater(out["buy_before_savings"], 0)


if __name__ == "__main__":
    unittest.main()
