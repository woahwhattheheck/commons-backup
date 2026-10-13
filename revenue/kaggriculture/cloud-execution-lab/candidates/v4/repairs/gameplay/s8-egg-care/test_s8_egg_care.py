# SPDX-License-Identifier: Apache-2.0
"""Focused checks for V4 ``r04_s8_egg_care``."""
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
import r04_s8_egg_care as lane  # noqa: E402
from titan_runtime import Features  # noqa: E402

CONFIG = {"episodeSteps": 720, "turnsPerDay": 24, "boardSize": 10,
          "shedCapacity": 100, "maxMarketOrdersPerTurn": 10, "farmHandCostMult": 1}


def observation(step=263, units=0, placed=5, *, egg=180, fertilizer=100,
                shed_fertilizer=6, pending_bonus=0, second=False):
    tiles = [[None for _ in range(10)] for _ in range(10)]
    goose = {"kind": "COOP", "animal": "GOOSE", "placed_day": placed,
             "yield_units": units, "consecutive_unfed": 0, "fed_today": True,
             "cared_today": False, "fertilizer_available": True,
             "pending_care_bonus": pending_bonus}
    tiles[2][2] = goose
    hands = []
    if second:
        tiles[3][3] = copy.deepcopy(goose)
        hands = [[3, 3]]
    farm = {"tiles": tiles, "farmer": [2, 2], "hands": hands,
            "money": 1000, "unlocked_quadrants": ["NW"], "hires_today": 0}
    return {"step": step, "day": step // 24, "hour": step % 24, "player": 0,
            "farms": [farm, copy.deepcopy(farm)],
            "private": {"inventories": [{} for _ in range(1 + len(hands))],
                        "shed": {"FERTILIZER": shed_fertilizer}},
            "market": {"prices": {"EGG": egg, "FERTILIZER": fertilizer}},
            "town": {"unlocked_shops": ["BAKERY", "BRUNCH_SPOT"]}}


def action(second=False, farmer=None, hand=None):
    return {"farmer": farmer or ["COLLECT_FERTILIZER"],
            "hands": ([hand or ["COLLECT_FERTILIZER"]] if second else []),
            "market": []}


class EggCare(unittest.TestCase):
    def tearDown(self):
        r04.S8_EGG_CARE = False
        lane.telemetry.clear()

    def test_key_ships_off_and_features_accept_it(self):
        data = json.loads((ROOT / "TITAN-CONFIG.json").read_text(encoding="utf-8"))
        self.assertIs(data["r04_s8_egg_care"], False)
        self.assertIs(Features(**data).r04_s8_egg_care, False)

    def test_install_plumbs_key(self):
        r04.install(s8_egg_care=True)
        self.assertIs(r04.S8_EGG_CARE, True)

    def test_disabled_returns_exact_parent(self):
        parent = action()
        self.assertIs(lane.apply_egg_care(observation(), parent, CONFIG, enabled=False), parent)

    def test_price_positive_hour23_collection_becomes_care(self):
        parent = action()
        out = lane.apply_egg_care(observation(), parent, CONFIG, enabled=True)
        self.assertIsNot(out, parent)
        self.assertEqual(out["farmer"], ["CARE"])
        self.assertEqual(parent["farmer"], ["COLLECT_FERTILIZER"])

    def test_h3c_harvest_priority_is_untouched(self):
        parent = action(farmer=["HARVEST"])
        self.assertIs(lane.apply_egg_care(observation(), parent, CONFIG, enabled=True), parent)

    def test_low_price_and_low_fertilizer_buffer_fail_closed(self):
        parent = action()
        self.assertIs(lane.apply_egg_care(observation(egg=115), parent, CONFIG, enabled=True), parent)
        parent = action()
        self.assertIs(lane.apply_egg_care(observation(shed_fertilizer=3), parent, CONFIG, enabled=True), parent)

    def test_no_harvest_cap_upper_bound_blocks(self):
        parent = action()
        self.assertIs(lane.apply_egg_care(observation(units=2), parent, CONFIG, enabled=True), parent)

    def test_final_unpayable_day_and_existing_bonus_block(self):
        parent = action()
        self.assertIs(lane.apply_egg_care(observation(step=28 * 24 + 23), parent, CONFIG, enabled=True), parent)
        parent = action()
        self.assertIs(lane.apply_egg_care(observation(pending_bonus=1), parent, CONFIG, enabled=True), parent)

    def test_independent_geese_transform_together(self):
        parent = action(second=True)
        out = lane.apply_egg_care(observation(second=True), parent, CONFIG, enabled=True)
        self.assertEqual(out["farmer"], ["CARE"])
        self.assertEqual(out["hands"], [["CARE"]])

    def test_stacked_active_worker_blocks_ambiguity(self):
        obs = observation()
        obs["farms"][0]["hands"] = [[2, 2]]
        obs["farms"][1] = copy.deepcopy(obs["farms"][0])
        obs["private"]["inventories"] = [{}, {}]
        parent = {"farmer": ["COLLECT_FERTILIZER"], "hands": [["HARVEST"]], "market": []}
        self.assertIs(lane.apply_egg_care(obs, parent, CONFIG, enabled=True), parent)


if __name__ == "__main__":
    unittest.main()
