# SPDX-License-Identifier: Apache-2.0
"""Focused regression for H3b strict PASTURE authentication."""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import r04_full_router as r04  # noqa: E402
import r04_h3b_sheep_clip as lane  # noqa: E402

CONFIG = {
    "episodeSteps": 720,
    "turnsPerDay": 24,
    "boardSize": 10,
    "shedCapacity": 100,
    "maxMarketOrdersPerTurn": 10,
    "farmHandCostMult": 1,
}
STEP = 18 * 24 + 10
TARGETS = [(5, 5), (6, 5), (7, 5)]


def sheep(*, units=1, placed=13, fed=True, cared=True, bonus=1):
    return {
        "kind": "PASTURE",
        "animal": "SHEEP",
        "placed_day": placed,
        "yield_units": units,
        "consecutive_unfed": 0,
        "fed_today": fed,
        "cared_today": cared,
        "fertilizer_available": True,
        "pending_care_bonus": bonus,
    }


def fixture():
    tiles = [[None for _ in range(10)] for _ in range(10)]
    tiles[5][5] = sheep(units=1)
    tiles[5][6] = sheep(units=6)
    tiles[5][7] = sheep(units=1)
    action = {"farmer": ["PASS"], "hands": [["HARVEST"]], "market": []}
    farm = {
        "farmer": [4, 4],
        "hands": [[5, 5]],
        "tiles": tiles,
        "money": 1000,
        "unlocked_quadrants": ["NW"],
        "hires_today": 0,
    }
    observation = {
        "step": STEP,
        "player": 0,
        "farms": [farm, copy.deepcopy(farm)],
        "private": {"inventories": [{}, {}], "shed": {}},
    }
    state = {
        "last_step": STEP,
        "day": STEP // 24,
        "workers": {1: list(TARGETS)},
        "work": {1: {"step": STEP, "command": ["HARVEST"], "inventory": {}}},
        "credit": {"WOOL": 0, "FERTILIZER": 0},
        "committed": True,
    }
    return action, observation, state


class H3bStrictSheepKind(unittest.TestCase):
    def setUp(self):
        self.saved_states = r04._V233_STATES
        r04._V233_STATES = {}

    def tearDown(self):
        r04._V233_STATES = self.saved_states

    def test_wrong_kind_sheep_shaped_target_preserves_parent_identity(self):
        action, observation, state = fixture()
        observation["farms"][0]["tiles"][5][6]["kind"] = "FIELD"
        r04._V233_STATES[0] = state
        result = lane.apply_h3b_sheep_clip(
            action, observation, dict(CONFIG), enabled=True)
        self.assertIs(result, action)
        self.assertEqual(state["work"][1]["command"], ["HARVEST"])

    def test_literal_pasture_still_allows_existing_rescue(self):
        action, observation, state = fixture()
        r04._V233_STATES[0] = state
        result = lane.apply_h3b_sheep_clip(
            action, observation, dict(CONFIG), enabled=True)
        self.assertIsNot(result, action)
        self.assertEqual(result["hands"][0], ["EAST"])
        self.assertEqual(state["work"][1]["command"], ["EAST"])


if __name__ == "__main__":
    unittest.main()
