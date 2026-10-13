# SPDX-License-Identifier: Apache-2.0
"""Focused checks for V4 ``r04_goose_pass_rescue``.

Run in a materialised candidate package:

    python -B -m unittest -v checks/test_v4_goose_pass_rescue.py
"""
from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import r04_full_router as r04  # noqa: E402
import r04_goose_pass_rescue as lane  # noqa: E402
from titan_runtime import Features, TitanAgent  # noqa: E402

CONFIG = {"episodeSteps": 720, "turnsPerDay": 24, "boardSize": 10,
          "shedCapacity": 100, "maxMarketOrdersPerTurn": 10,
          "farmHandCostMult": 1}


def goose_tile(*, units=4, fed=True, cared=True, bonus=0, placed_day=0):
    return {"kind": "COOP", "animal": "GOOSE", "placed_day": placed_day,
            "yield_units": units, "consecutive_unfed": 0,
            "fed_today": fed, "cared_today": cared,
            "fertilizer_available": True, "pending_care_bonus": bonus}


def observation(step=119, *, shed=None, inventories=None, tile=None,
                farmer=(4, 4), hands=((5, 4),)):
    tiles = [["LOCKED"] * 10 for _ in range(10)]
    tiles[4][4] = tile if tile is not None else goose_tile()
    farm = {"tiles": tiles, "farmer": list(farmer), "hands": [list(p) for p in hands],
            "money": 1000, "unlocked_quadrants": ["NW"], "hires_today": 0}
    prices = {product: 10 for product in r04.PRODUCTS}
    return {"step": step, "day": step // 24, "hour": step % 24, "player": 0,
            "farms": [farm, copy.deepcopy(farm)],
            "private": {"inventories": inventories or [{}, {}],
                        "shed": shed or {}},
            "market": {"prices": prices},
            "town": {"unlocked_shops": ["BAKERY", "YARN_STORE"]}}


def action(farmer=None, hands=None, market=None):
    return {"farmer": farmer or ["PASS"], "hands": hands or [["PASS"]],
            "market": market or []}


class GoosePassRescue(unittest.TestCase):
    def tearDown(self):
        r04.GOOSE_PASS_RESCUE = False

    def test_key_ships_off_and_features_accept_it(self):
        data = json.loads((ROOT / "TITAN-CONFIG.json").read_text(encoding="utf-8"))
        self.assertIs(data["r04_goose_pass_rescue"], False)
        self.assertIs(Features(**data).r04_goose_pass_rescue, False)

    def test_disabled_is_exact_parent_object(self):
        parent = action()
        self.assertIs(lane.apply_goose_pass_rescue(
            parent, observation(), dict(CONFIG), enabled=False), parent)

    def test_pass_on_clipping_goose_becomes_harvest(self):
        parent = action()
        out = lane.apply_goose_pass_rescue(parent, observation(), dict(CONFIG), enabled=True)
        self.assertIsNot(out, parent)
        self.assertEqual(out["farmer"], ["HARVEST"])
        self.assertEqual(out["hands"], [["PASS"]])
        self.assertEqual(out["market"], [])

    def test_non_hour23_is_exact_parent_object(self):
        parent = action()
        self.assertIs(lane.apply_goose_pass_rescue(
            parent, observation(step=118), dict(CONFIG), enabled=True), parent)

    def test_no_clip_is_exact_parent_object(self):
        parent = action()
        obs = observation(tile=goose_tile(units=3))
        self.assertIs(lane.apply_goose_pass_rescue(
            parent, obs, dict(CONFIG), enabled=True), parent)

    def test_uncared_goose_is_exact_parent_object(self):
        parent = action()
        obs = observation(tile=goose_tile(cared=False))
        self.assertIs(lane.apply_goose_pass_rescue(
            parent, obs, dict(CONFIG), enabled=True), parent)

    def test_capacity_fail_closed(self):
        parent = action()
        obs = observation(shed={"WHEAT": 97})
        self.assertIs(lane.apply_goose_pass_rescue(
            parent, obs, dict(CONFIG), enabled=True), parent)

    def test_same_site_active_worker_blocks(self):
        parent = action(hands=[["FEED"]])
        obs = observation(hands=((4, 4),))
        self.assertIs(lane.apply_goose_pass_rescue(
            parent, obs, dict(CONFIG), enabled=True), parent)

    def test_duplicate_pass_workers_fail_closed(self):
        parent = action(hands=[["PASS"]])
        obs = observation(hands=((4, 4),))
        self.assertIs(lane.apply_goose_pass_rescue(
            parent, obs, dict(CONFIG), enabled=True), parent)

    def test_same_turn_market_inflow_blocks(self):
        parent = action(market=[["BUY_ANIMAL", "GOOSE", 1]])
        self.assertIs(lane.apply_goose_pass_rescue(
            parent, observation(), dict(CONFIG), enabled=True), parent)

    def test_nonstandard_configuration_fails_closed(self):
        parent = action()
        bad = dict(CONFIG)
        bad["shedCapacity"] = 99
        self.assertIs(lane.apply_goose_pass_rescue(
            parent, observation(), bad, enabled=True), parent)

    def test_install_and_titan_diagnostics_carry_key(self):
        r04.install(goose_pass_rescue=True)
        self.assertIs(r04.GOOSE_PASS_RESCUE, True)
        r04.install(goose_pass_rescue=False)
        self.assertIs(r04.GOOSE_PASS_RESCUE, False)

        agent = TitanAgent(Features(r04_sale_window=True, r04_goose_pass_rescue=True))
        agent.act(observation(step=0, inventories=[{}, {}]), dict(CONFIG))
        self.assertIs(r04.GOOSE_PASS_RESCUE, True)
        self.assertIs(agent.diagnostics["goose_pass_rescue"], True)


if __name__ == "__main__":
    unittest.main()
