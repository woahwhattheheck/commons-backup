# SPDX-License-Identifier: Apache-2.0
"""Focused C5 -> S4 market-prefix composition checks."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import r04_full_router as r04  # noqa: E402
import r04_s4_route12_seed_reserve as lane  # noqa: E402


def _pass_action():
    return {"farmer": ["PASS"], "hands": [], "market": []}


def _tapes():
    tapes = [[_pass_action() for _ in range(719)] for _ in range(13)]
    tape = tapes[12]
    tape[257] = {"farmer": ["PLANT", "WHEAT"], "hands": [], "market": []}
    tape[261] = {"farmer": ["PLANT", "WHEAT"], "hands": [], "market": []}
    tape[262] = {
        "farmer": ["PLANT", "WHEAT"],
        "hands": [["PLANT", "WHEAT"], ["PLANT", "WHEAT"]],
        "market": [],
    }
    return tapes


def _observation(*, money=50):
    shed = {item: 0 for item in (
        "WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON",
        "EGG", "MILK", "WOOL", "FERTILIZER", "GOOSE", "COW", "SHEEP")}
    shed["WHEAT"] = 1
    return {
        "step": 256,
        "player": 0,
        "town": {"unlocked_shops": ["YARN_STORE", "YARN_STORE"]},
        "farms": [{"money": money, "hands": []}],
        "private": {
            "seeds": {"WHEAT": 0, "CARROT": 0, "TOMATO": 0,
                      "STRAWBERRY": 0, "MELON": 0},
            "shed": shed,
        },
        "market": {
            "inventory": {"FERTILIZER": 10000},
            "prices": {"FERTILIZER": 100},
        },
    }


class C5S4Composition(unittest.TestCase):
    def setUp(self):
        self.original_policy = r04._POLICY
        r04._POLICY = SimpleNamespace(
            players={0: SimpleNamespace(last_step=256, plan=12)},
            tapes=_tapes(),
        )

    def tearDown(self):
        r04._POLICY = self.original_policy

    def test_c5_empty_tombstone_is_inert_for_s4_funding(self):
        obs = _observation(money=50)
        parent = {
            "farmer": ["PASS"],
            "hands": [],
            "market": [[], ["SELL", "WHEAT", 1]],
        }
        out = lane.apply_route12_seed_reserve(obs, parent, enabled=True)
        self.assertEqual(
            out["market"],
            [[], ["SELL", "WHEAT", 1], ["BUY_SEED", "WHEAT", 5]],
        )

    def test_post_c5_ten_row_shape_still_vetoes(self):
        obs = _observation(money=1000)
        parent = {
            "farmer": ["PASS"],
            "hands": [],
            "market": [[], ["SELL", "WHEAT", 1]]
            + [["SELL", "WOOL", 1] for _ in range(8)],
        }
        self.assertIs(
            lane.apply_route12_seed_reserve(obs, parent, enabled=True),
            parent,
        )

    def test_non_list_tombstone_remains_fail_closed(self):
        obs = _observation(money=1000)
        parent = {
            "farmer": ["PASS"],
            "hands": [],
            "market": [(), ["SELL", "WHEAT", 1]],
        }
        self.assertIs(
            lane.apply_route12_seed_reserve(obs, parent, enabled=True),
            parent,
        )


if __name__ == "__main__":
    unittest.main()