# SPDX-License-Identifier: Apache-2.0
"""Focused checks for V4 ``r04_eod_capacity_rescue``.

Run in a materialised candidate package:

    python -B -m unittest -v checks/test_v4_eod_capacity_rescue.py
"""
from __future__ import annotations

import copy
import inspect
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import r04_eod_capacity_rescue as lane  # noqa: E402
import r04_full_router as r04  # noqa: E402
from titan_runtime import Features, TitanAgent  # noqa: E402

CONFIG = {"episodeSteps": 720, "turnsPerDay": 24, "boardSize": 10,
          "shedCapacity": 100, "maxMarketOrdersPerTurn": 10,
          "farmHandCostMult": 1}


def observation(step=119, *, shed=None, inventories=None, prices=None, hands=((5, 4),)):
    tiles = [["LOCKED"] * 10 for _ in range(10)]
    for y in range(3, 7):
        for x in range(3, 7):
            tiles[y][x] = {"kind": "SOIL"}
    farm = {"tiles": tiles, "farmer": [4, 4], "hands": [list(p) for p in hands],
            "money": 1000, "unlocked_quadrants": ["NW"], "hires_today": 0}
    market_prices = {product: 10 for product in r04.PRODUCTS}
    market_prices.update(prices or {})
    inv = inventories if inventories is not None else [{"WHEAT": 2}, {"WHEAT": 1}]
    return {"step": step, "day": step // 24, "hour": step % 24, "player": 0,
            "farms": [farm, copy.deepcopy(farm)],
            "private": {"inventories": inv, "shed": shed or {}},
            "market": {"prices": market_prices},
            "town": {"unlocked_shops": ["BAKERY", "YARN_STORE"]}}


def action(farmer=None, hands=None, market=None):
    return {"farmer": farmer or ["PASS"], "hands": hands or [["PASS"]],
            "market": market or []}


class EodCapacityRescue(unittest.TestCase):
    def tearDown(self):
        r04.EOD_CAPACITY_RESCUE = False

    def test_key_ships_off_and_features_accept_it(self):
        data = json.loads((ROOT / "TITAN-CONFIG.json").read_text(encoding="utf-8"))
        self.assertIs(data["r04_eod_capacity_rescue"], False)
        self.assertIs(Features(**data).r04_eod_capacity_rescue, False)

    def test_disabled_is_exact_parent_object(self):
        parent = action()
        obs = observation(shed={"WHEAT": 98, "CARROT": 1})
        self.assertIs(lane.apply_eod_capacity_rescue(
            parent, obs, dict(CONFIG), enabled=False), parent)

    def test_single_product_overflow_appends_exact_rescue_sell(self):
        parent = action()
        obs = observation(shed={"WHEAT": 98, "CARROT": 1})
        out = lane.apply_eod_capacity_rescue(parent, obs, dict(CONFIG), enabled=True)
        self.assertIsNot(out, parent)
        self.assertEqual(out["farmer"], ["PASS"])
        self.assertEqual(out["hands"], [["PASS"]])
        self.assertEqual(out["market"], [["SELL", "WHEAT", 2]])
        self.assertEqual(parent["market"], [])

        baseline_wheat = 98 + 1
        candidate_wheat = (98 - 2) + 3
        self.assertEqual(candidate_wheat, baseline_wheat)
        self.assertEqual((99 - 2) + 3, 100)

    def test_full_shed_recycles_same_product(self):
        parent = action()
        obs = observation(shed={"WHEAT": 100}, inventories=[{"WHEAT": 4}, {}])
        out = lane.apply_eod_capacity_rescue(parent, obs, dict(CONFIG), enabled=True)
        self.assertEqual(out["market"], [["SELL", "WHEAT", 4]])

    def test_safe_existing_market_rows_are_preserved_before_rescue(self):
        parent = action(market=[["HIRE"], ["BUY_SEED", "CARROT", 1]])
        obs = observation(shed={"WHEAT": 98, "CARROT": 1})
        out = lane.apply_eod_capacity_rescue(parent, obs, dict(CONFIG), enabled=True)
        self.assertEqual(out["market"], [
            ["HIRE"], ["BUY_SEED", "CARROT", 1], ["SELL", "WHEAT", 2]])

    def test_bogus_market_row_head_is_exact_parent(self):
        parent = action(market=[["BOGUS", "WHEAT", 1]])
        obs = observation(shed={"WHEAT": 98, "CARROT": 1})
        out = lane.apply_eod_capacity_rescue(parent, obs, dict(CONFIG), enabled=True)
        self.assertIs(out, parent)
        self.assertEqual(out["market"], [["BOGUS", "WHEAT", 1]])

    def test_helper_source_avoids_unlisted_pad_phrase(self):
        compact = " ".join(Path(lane.__file__).read_text(encoding="utf-8").lower().split())
        self.assertNotIn("unknown verb", compact)
        self.assertNotIn("unknown action", compact)
        self.assertNotIn("unlisted verb", compact)
        self.assertNotIn("unlisted action", compact)
        self.assertNotIn("unsupported verb", compact)
        self.assertNotIn("unsupported action", compact)

    def test_floor_price_is_allowed_and_does_not_need_coercion(self):
        parent = action()
        obs = observation(shed={"WHEAT": 98, "CARROT": 1}, prices={"WHEAT": 1})
        out = lane.apply_eod_capacity_rescue(parent, obs, dict(CONFIG), enabled=True)
        self.assertEqual(out["market"], [["SELL", "WHEAT", 2]])

    def test_roomy_shed_is_exact_parent_object(self):
        parent = action()
        obs = observation(shed={"WHEAT": 95}, inventories=[{"WHEAT": 2}, {"WHEAT": 1}])
        self.assertIs(lane.apply_eod_capacity_rescue(
            parent, obs, dict(CONFIG), enabled=True), parent)

    def test_mixed_carried_products_fail_closed(self):
        parent = action()
        obs = observation(shed={"WHEAT": 99}, inventories=[{"WHEAT": 1}, {"CARROT": 1}])
        self.assertIs(lane.apply_eod_capacity_rescue(
            parent, obs, dict(CONFIG), enabled=True), parent)

    def test_insufficient_same_product_shed_stock_fails_closed(self):
        parent = action()
        obs = observation(shed={"CARROT": 100}, inventories=[{"WHEAT": 3}, {}])
        self.assertIs(lane.apply_eod_capacity_rescue(
            parent, obs, dict(CONFIG), enabled=True), parent)

    def test_cargo_changing_unit_action_fails_closed(self):
        parent = action(farmer=["HARVEST"])
        obs = observation(shed={"WHEAT": 98, "CARROT": 1})
        self.assertIs(lane.apply_eod_capacity_rescue(
            parent, obs, dict(CONFIG), enabled=True), parent)

    def test_unhashable_unit_op_heads_fail_closed(self):
        obs = observation(shed={"WHEAT": 98, "CARROT": 1})
        for malformed in ([[]], [{}]):
            parent = action(farmer=malformed)
            self.assertIs(
                lane.apply_eod_capacity_rescue(
                    parent, obs, dict(CONFIG), enabled=True),
                parent,
            )

    def test_existing_shed_changing_market_order_fails_closed(self):
        parent = action(market=[["SELL", "CARROT", 1]])
        obs = observation(shed={"WHEAT": 98, "CARROT": 1})
        self.assertIs(lane.apply_eod_capacity_rescue(
            parent, obs, dict(CONFIG), enabled=True), parent)

    def test_full_market_order_budget_fails_closed(self):
        rows = [["BUY_SEED", "WHEAT", 1] for _ in range(10)]
        parent = action(market=rows)
        obs = observation(shed={"WHEAT": 98, "CARROT": 1})
        self.assertIs(lane.apply_eod_capacity_rescue(
            parent, obs, dict(CONFIG), enabled=True), parent)

    def test_non_hour23_and_post_last_eod_fail_closed(self):
        parent = action()
        for step in (118, 718, 719):
            obs = observation(step=step, shed={"WHEAT": 98, "CARROT": 1})
            self.assertIs(lane.apply_eod_capacity_rescue(
                parent, obs, dict(CONFIG), enabled=True), parent)

    def test_malformed_price_fails_closed_without_coercion(self):
        parent = action()
        obs = observation(shed={"WHEAT": 98, "CARROT": 1}, prices={"WHEAT": "10"})
        self.assertIs(lane.apply_eod_capacity_rescue(
            parent, obs, dict(CONFIG), enabled=True), parent)

    def test_nonstandard_configuration_fails_closed(self):
        parent = action()
        obs = observation(shed={"WHEAT": 98, "CARROT": 1})
        for key, bad_value in (
            ("shedCapacity", 99),
            ("episodeSteps", 696),
            ("episodeSteps", True),
            ("townShopSellInterval", 1),
            ("townCenterSellInterval", 1),
            ("townShopSellInterval", True),
        ):
            bad = dict(CONFIG)
            bad[key] = bad_value
            self.assertIs(lane.apply_eod_capacity_rescue(
                parent, obs, bad, enabled=True), parent)

    def test_custom_hour23_town_consume_is_exact_parent(self):
        parent = action()
        obs = observation(shed={"WHEAT": 98, "CARROT": 1}, inventories=[{"WHEAT": 3}, {}])
        for key, consume_every_hour in (
            ("townShopSellInterval", 1),
            ("townCenterSellInterval", 1),
        ):
            bad = dict(CONFIG)
            bad[key] = consume_every_hour
            out = lane.apply_eod_capacity_rescue(parent, obs, bad, enabled=True)
            self.assertIs(out, parent)
            self.assertEqual(out["market"], [])

        pinned = dict(CONFIG)
        pinned["townShopSellInterval"] = 4
        pinned["townCenterSellInterval"] = 24
        out = lane.apply_eod_capacity_rescue(parent, obs, pinned, enabled=True)
        self.assertEqual(out["market"], [["SELL", "WHEAT", 2]])

    def test_rescue_is_whole_agent_outer_seam_after_h3c(self):
        stack_source = inspect.getsource(r04._v3_stack)
        whole_source = inspect.getsource(r04.v3_agent)
        self.assertNotIn("apply_eod_capacity_rescue", stack_source)
        self.assertIn("EOD_CAPACITY_RESCUE", whole_source)
        self.assertLess(whole_source.index("apply_goose_eod_cap_rescue"),
                        whole_source.index("apply_eod_capacity_rescue"))
        self.assertLess(whole_source.index("_v3_core(observation, configuration)"),
                        whole_source.index("apply_eod_capacity_rescue"))

    def test_install_and_titan_diagnostics_carry_key(self):
        r04.install(eod_capacity_rescue=True)
        self.assertIs(r04.EOD_CAPACITY_RESCUE, True)
        r04.install(eod_capacity_rescue=False)
        self.assertIs(r04.EOD_CAPACITY_RESCUE, False)

        agent = TitanAgent(Features(r04_sale_window=True, r04_eod_capacity_rescue=True))
        agent.act(observation(step=0, shed={}, inventories=[{}, {}]), dict(CONFIG))
        self.assertIs(r04.EOD_CAPACITY_RESCUE, True)
        self.assertIs(agent.diagnostics["eod_capacity_rescue"], True)


if __name__ == "__main__":
    unittest.main()
