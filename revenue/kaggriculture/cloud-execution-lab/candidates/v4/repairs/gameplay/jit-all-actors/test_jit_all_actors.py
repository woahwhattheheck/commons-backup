# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

OVERLAY = Path(__file__).resolve().parents[3] / "donor" / "overlay"
if str(OVERLAY) not in sys.path:
    sys.path.insert(0, str(OVERLAY))
import jit_pass_fertilize as jit


def _tile(crop="WHEAT"):
    return {
        "kind": "PLANT",
        "crop": crop,
        "planted_day": 0,
        "yield_units": 1,
        "fertilized_until_day": 1,
        "watered_today": False,
    }


def _obs(positions, crops=None, fertilizer=None):
    crops = crops or ["WHEAT"] * len(positions)
    fertilizer = fertilizer or [1] * len(positions)
    tiles = [[None for _ in range(4)] for _ in range(4)]
    for pos, crop in zip(positions, crops):
        x, y = pos
        if tiles[y][x] is None:
            tiles[y][x] = _tile(crop)
    return {
        "step": 50,
        "player": 0,
        "farms": [{
            "farmer": list(positions[0]),
            "hands": [list(pos) for pos in positions[1:]],
            "tiles": tiles,
        }],
        "private": {
            "inventories": [{"FERTILIZER": units} for units in fertilizer],
        },
    }


def _action(farmer, hands):
    return {
        "farmer": [farmer],
        "hands": [[command] for command in hands],
        "market": [],
    }


class JitAllActorsRegression(unittest.TestCase):
    def test_colocated_farmer_fertilize_blocks_hand_jit(self):
        observation = _obs([(1, 1), (1, 1)])
        action = _action("FERTILIZE", ["PASS"])
        following = _action("PASS", ["WATER"])
        before = copy.deepcopy(action)
        out, events = jit.apply_jit_pass_fertilize(
            action, observation, following, enabled=True
        )
        self.assertIs(out, action)
        self.assertEqual(events, ())
        self.assertEqual(action, before)

    def test_colocated_hand_fertilize_blocks_farmer_jit(self):
        observation = _obs([(1, 1), (1, 1)])
        action = _action("PASS", ["FERTILIZE"])
        following = _action("WATER", ["PASS"])
        out, events = jit.apply_jit_pass_fertilize(
            action, observation, following, enabled=True
        )
        self.assertIs(out, action)
        self.assertEqual(events, ())

    def test_two_qualifying_workers_same_tile_fail_closed(self):
        observation = _obs([(1, 1), (1, 1)])
        action = _action("PASS", ["PASS"])
        following = _action("WATER", ["WATER"])
        out, events = jit.apply_jit_pass_fertilize(
            action, observation, following, enabled=True
        )
        self.assertIs(out, action)
        self.assertEqual(events, ())

    def test_unique_tiles_still_activate_independently(self):
        observation = _obs([(1, 1), (2, 1)])
        action = _action("PASS", ["PASS"])
        following = _action("WATER", ["WATER"])
        before = copy.deepcopy(action)
        out, events = jit.apply_jit_pass_fertilize(
            action, observation, following, enabled=True
        )
        self.assertIsNot(out, action)
        self.assertEqual(out["farmer"], ["FERTILIZE"])
        self.assertEqual(out["hands"], [["FERTILIZE"]])
        self.assertEqual(len(events), 2)
        self.assertEqual(action, before)

    def test_unhashable_crop_is_noop_not_exception(self):
        observation = _obs([(1, 1)])
        observation["farms"][0]["tiles"][1][1]["crop"] = ["WHEAT"]
        action = _action("PASS", [])
        following = _action("WATER", [])
        out, events = jit.apply_jit_pass_fertilize(
            action, observation, following, enabled=True
        )
        self.assertIs(out, action)
        self.assertEqual(events, ())

    def test_omitted_future_hand_rows_do_not_block_farmer(self):
        observation = _obs([(1, 1), (2, 1)])
        action = _action("PASS", ["PASS"])
        following = {"farmer": ["WATER"], "hands": [], "market": []}
        out, events = jit.apply_jit_pass_fertilize(
            action, observation, following, enabled=True
        )
        self.assertEqual(out["farmer"], ["FERTILIZE"])
        self.assertEqual(out["hands"], [["PASS"]])
        self.assertEqual(len(events), 1)

    def test_malformed_public_actor_position_fails_closed(self):
        observation = _obs([(1, 1), (2, 1)])
        observation["farms"][0]["hands"][0] = ["x", 1]
        action = _action("PASS", ["PASS"])
        following = _action("WATER", ["WATER"])
        out, events = jit.apply_jit_pass_fertilize(
            action, observation, following, enabled=True
        )
        self.assertIs(out, action)
        self.assertEqual(events, ())

    def test_disabled_preserves_exact_identity(self):
        observation = _obs([(1, 1)])
        action = _action("PASS", [])
        following = _action("WATER", [])
        out, events = jit.apply_jit_pass_fertilize(
            action, observation, following, enabled=False
        )
        self.assertIs(out, action)
        self.assertEqual(events, ())


if __name__ == "__main__":
    unittest.main()
