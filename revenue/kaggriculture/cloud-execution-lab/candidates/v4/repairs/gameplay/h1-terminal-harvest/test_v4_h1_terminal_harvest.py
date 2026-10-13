# SPDX-License-Identifier: Apache-2.0
"""Focused checks for V4 ``r04_h1_terminal_harvest``.

Run in a materialised candidate package:

    python -B -m unittest -v checks/test_v4_h1_terminal_harvest.py
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
import r04_h1_terminal_harvest as lane  # noqa: E402
from titan_runtime import Features, TitanAgent  # noqa: E402

CONFIG = {"episodeSteps": 720, "turnsPerDay": 24, "boardSize": 10,
          "shedCapacity": 100, "maxMarketOrdersPerTurn": 10,
          "farmHandCostMult": 1}


def plant(**changes):
    value = {"kind": "PLANT", "crop": "WHEAT", "planted_day": 20,
             "yield_units": 3, "max_lifespan_step": 672,
             "watered_today": False, "fertilized_until_day": -1}
    value.update(changes)
    return value


def observation(current_tile=None, *, step=672, hands=None):
    tiles = [[None] * 10 for _ in range(10)]
    tiles[0][0] = current_tile if current_tile is not None else plant()
    farm = {"farmer": [0, 0], "hands": [list(p) for p in (hands or [])],
            "tiles": tiles, "money": 1000, "unlocked_quadrants": ["NW"],
            "hires_today": 0}
    prices = {product: 10 for product in r04.PRODUCTS}
    return {"step": step, "day": step // 24, "hour": step % 24,
            "player": 0, "farms": [farm, copy.deepcopy(farm)],
            "private": {"inventories": [{} for _ in range(1 + len(hands or []))],
                        "shed": {}, "seeds": {}},
            "market": {"prices": prices},
            "town": {"unlocked_shops": ["BAKERY", "YARN_STORE"]}}


def action(farmer=None, hands=None, market=None):
    return {"farmer": farmer or ["WATER"], "hands": hands or [],
            "market": market or []}


class H1TerminalHarvest(unittest.TestCase):
    def tearDown(self):
        r04.H1_TERMINAL_HARVEST = False

    def test_key_ships_off_and_features_accept_it(self):
        data = json.loads((ROOT / "TITAN-CONFIG.json").read_text(encoding="utf-8"))
        self.assertIs(data["r04_h1_terminal_harvest"], False)
        self.assertIs(Features(**data).r04_h1_terminal_harvest, False)

    def test_disabled_is_exact_parent_object(self):
        parent = action()
        self.assertIs(lane.apply_h1_terminal_harvest(
            parent, observation(), dict(CONFIG), enabled=False), parent)

    def test_exact_first_decay_mature_annual_harvests(self):
        parent = action(market=[["SELL", "MILK", 2]])
        out = lane.apply_h1_terminal_harvest(
            parent, observation(), dict(CONFIG), enabled=True)
        self.assertIsNot(out, parent)
        self.assertEqual(out["farmer"], ["HARVEST"])
        self.assertEqual(out["market"], parent["market"])
        self.assertEqual(parent["farmer"], ["WATER"])

    def test_future_lifespan_is_exact_parent_object(self):
        parent = action()
        self.assertIs(lane.apply_h1_terminal_harvest(
            parent, observation(plant(max_lifespan_step=696)), dict(CONFIG), enabled=True), parent)

    def test_later_decay_is_exact_parent_object(self):
        parent = action()
        self.assertIs(lane.apply_h1_terminal_harvest(
            parent, observation(plant(max_lifespan_step=670)), dict(CONFIG), enabled=True), parent)

    def test_zero_yield_and_ongoing_crop_are_exact_parent(self):
        for tile in (plant(yield_units=0),
                     plant(crop="TOMATO", planted_day=10, max_lifespan_step=672)):
            with self.subTest(tile=tile):
                parent = action()
                self.assertIs(lane.apply_h1_terminal_harvest(
                    parent, observation(tile), dict(CONFIG), enabled=True), parent)

    def test_non_water_is_exact_parent_object(self):
        parent = action(farmer=["HARVEST"])
        self.assertIs(lane.apply_h1_terminal_harvest(
            parent, observation(), dict(CONFIG), enabled=True), parent)

    def test_nonstandard_config_is_type_strict(self):
        for bad in (24.0, "24", True, None):
            with self.subTest(bad=bad):
                parent = action()
                cfg = dict(CONFIG)
                cfg["turnsPerDay"] = bad
                self.assertIs(lane.apply_h1_terminal_harvest(
                    parent, observation(), cfg, enabled=True), parent)

    def test_malformed_typed_crop_state_is_exact_parent(self):
        for key, bad in (("yield_units", True), ("planted_day", "20"),
                         ("max_lifespan_step", 672.0)):
            with self.subTest(key=key, bad=bad):
                parent = action()
                self.assertIs(lane.apply_h1_terminal_harvest(
                    parent, observation(plant(**{key: bad})), dict(CONFIG), enabled=True), parent)

    def test_multiple_workers_only_rewrites_qualifying_water(self):
        obs = observation(step=672, hands=((1, 0),))
        obs["farms"][0]["tiles"][0][1] = plant(crop="CARROT", yield_units=0)
        parent = action(hands=[["WATER"]])
        out = lane.apply_h1_terminal_harvest(parent, obs, dict(CONFIG), enabled=True)
        self.assertEqual(out["farmer"], ["HARVEST"])
        self.assertEqual(out["hands"], [["WATER"]])
        self.assertEqual(parent["farmer"], ["WATER"])

    def test_install_and_titan_diagnostics_carry_key(self):
        r04.install(h1_terminal_harvest=True)
        self.assertIs(r04.H1_TERMINAL_HARVEST, True)
        r04.install(h1_terminal_harvest=False)
        self.assertIs(r04.H1_TERMINAL_HARVEST, False)

        agent = TitanAgent(Features(r04_sale_window=True, r04_h1_terminal_harvest=True))
        agent.act(observation(step=0), dict(CONFIG))
        self.assertIs(r04.H1_TERMINAL_HARVEST, True)
        self.assertIs(agent.diagnostics["h1_terminal_harvest"], True)


if __name__ == "__main__":
    unittest.main()
