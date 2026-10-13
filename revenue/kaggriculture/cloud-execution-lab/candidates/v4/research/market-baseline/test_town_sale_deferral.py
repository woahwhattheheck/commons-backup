#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import engine_bound_baseline as baseline
import town_sale_deferral as sale
import town_wheat_timing as timing

ENGINE = (
    Path(os.environ["TITAN_ENGINE"])
    if "TITAN_ENGINE" in os.environ
    else HERE.parents[3] / "reference" / "engine" / "kaggriculture.py"
)


class TownSaleDeferralTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = baseline.load_engine(ENGINE)

    def _market_state(self, item: str, quantity: int, inventory: int, shops):
        e = self.engine
        cfg = {
            "boardSize": 10,
            "startingMoney": 3000,
            "turnsPerDay": 24,
            "episodeSteps": 720,
            "shedCapacity": 1000,
            "farmHandCostMult": 1,
            "maxMarketOrdersPerTurn": 10,
            "townShopSellInterval": 4,
            "townCenterSellInterval": 24,
        }
        farms = [e._new_farm(10, 3000) for _ in range(2)]
        private = [e._new_private() for _ in range(2)]
        market, town = e._new_market(), e._new_town()
        town["unlocked_shops"] = list(shops)
        market["inventory"][item] = inventory
        e._refresh_prices(market)
        private[0]["shed"][item] = quantity
        states = []
        for player in range(2):
            obs = SimpleNamespace(
                player=player,
                farms=farms,
                market=market,
                town=town,
                private=private[player],
            )
            states.append(SimpleNamespace(observation=obs, action={}))
        env = SimpleNamespace(configuration=cfg, info={"seed": 1})
        return states, env, farms, private, market

    def test_constructed_five_unit_milk_witness(self):
        shops = [
            "PIZZA_SHOP",
            "PIZZA_SHOP",
            "ICE_CREAM_SHOP",
            "SMOOTHIE_SHOP",
            "SMOOTHIE_SHOP",
        ]
        demand = timing.town_demand_units(self.engine, 100, shops, item="MILK")
        self.assertEqual(demand, 5)
        row = sale.sale_deferral_window(self.engine, 10000, 100, demand, "MILK")
        self.assertEqual(row["sell_before_revenue"], 6205)
        self.assertEqual(row["sell_after_revenue"], 7072)
        self.assertEqual(row["post_drain_premium"], 867)
        self.assertTrue(row["post_drain_is_never_worse"])

    def test_official_engine_phase_witness_matches_ledger(self):
        shops = [
            "PIZZA_SHOP",
            "PIZZA_SHOP",
            "ICE_CREAM_SHOP",
            "SMOOTHIE_SHOP",
            "SMOOTHIE_SHOP",
        ]
        quantity = 100

        # Sell before step-100 town drain.
        states, env, farms, _, _ = self._market_state("MILK", quantity, 10000, shops)
        states[0].action = {"market": [["SELL", "MILK", quantity]]}
        self.engine._process_market(states, env)
        before_revenue = farms[0]["money"] - 3000

        # Identical sale after the deterministic step-100 town drain.
        states, env, farms, _, market = self._market_state("MILK", quantity, 10000, shops)
        self.engine._town_consume(env, states, 100)
        self.assertEqual(market["inventory"]["MILK"], 9995)
        states[0].action = {"market": [["SELL", "MILK", quantity]]}
        self.engine._process_market(states, env)
        after_revenue = farms[0]["money"] - 3000

        row = sale.sale_deferral_window(self.engine, 10000, quantity, 5, "MILK")
        self.assertEqual(before_revenue, row["sell_before_revenue"])
        self.assertEqual(after_revenue, row["sell_after_revenue"])
        self.assertEqual(after_revenue - before_revenue, 867)

    def test_zero_demand_is_exact_identity(self):
        for item in self.engine.TOWN_CENTER_PRODUCTS:
            row = sale.sale_deferral_window(self.engine, 10000, 50, 0, item)
            self.assertEqual(row["post_drain_premium"], 0)

    def test_fertilizer_has_no_public_town_drain(self):
        shops = list(self.engine.SHOPS)[: self.engine.MAX_SHOP_INSTANCES]
        self.assertEqual(
            timing.town_demand_units(self.engine, 96, shops, item="FERTILIZER"),
            0,
        )

    def test_grid_never_finds_negative_deterministic_premium(self):
        rows = sale.audit_grid(self.engine)
        self.assertEqual(
            len(rows),
            len(self.engine.TOWN_CENTER_PRODUCTS) * 6 * 10 * 5,
        )
        self.assertTrue(all(row["post_drain_premium"] >= 0 for row in rows))

    def test_public_oracle_is_fail_closed_and_all_product(self):
        obs = {
            "step": 100,
            "market": {"inventory": {"WOOL": 10000}},
            "town": {"unlocked_shops": ["YARN_STORE", "YARN_STORE"]},
        }
        out = sale.opportunity(self.engine, obs, item="WOOL", quantity=50)
        self.assertEqual(out["town_demand_units"], 4)
        self.assertEqual(out["status"], "DETERMINISTIC_POST_DRAIN_PREMIUM")
        self.assertGreater(out["post_drain_premium"], 0)

        with self.assertRaises(ValueError):
            sale.opportunity(
                self.engine,
                {"step": 100, "market": {"inventory": {}}, "town": {}},
                item="WOOL",
                quantity=50,
            )

    def test_off_tick_has_no_deterministic_sale_window(self):
        obs = {
            "step": 101,
            "market": {"inventory": {"MILK": 10000}},
            "town": {"unlocked_shops": ["PIZZA_SHOP"]},
        }
        out = sale.opportunity(self.engine, obs, item="MILK", quantity=20)
        self.assertEqual(out["status"], "NO_TOWN_DEMAND_THIS_STEP")
        self.assertEqual(out["town_demand_units"], 0)
        self.assertEqual(out["post_drain_premium"], 0)


if __name__ == "__main__":
    unittest.main()
