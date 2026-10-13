# SPDX-License-Identifier: Apache-2.0
"""Regression for the one-PLACE-per-worker terminal cash constraint."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import r04_full_router as r04  # noqa: E402
import r04_place_delivery as lane  # noqa: E402


class PlaceDeliveryCashMonotone(unittest.TestCase):
    def test_multi_product_overflow_worker_fails_closed_to_parent_drop(self):
        tiles = [["LOCKED"] * 10 for _ in range(10)]
        farm = {"tiles": tiles, "farmer": [4, 4], "hands": []}
        prices = {product: 10 for product in r04.PRODUCTS}
        prices.update({"CARROT": 30, "WOOL": 20})
        observation = {
            "step": 718,
            "player": 0,
            "farms": [farm],
            "private": {
                "shed": {"WHEAT": 98},
                # Preserve insertion order: official DROP takes CARROT first,
                # then one WOOL into the final free shed slot.
                "inventories": [{"CARROT": 1, "WOOL": 5}],
            },
            "market": {"prices": prices},
        }
        parent = {
            "farmer": ["DROP"],
            "hands": [],
            "market": [
                ["SELL", "WHEAT", 98],
                ["SELL", "CARROT", 1],
                ["SELL", "WOOL", 1],
            ],
        }

        view = r04.FarmView(observation)
        baseline = r04.projected_shed(parent, view)
        self.assertEqual(baseline["CARROT"], 1)
        self.assertEqual(baseline["WOOL"], 1)

        # A single PLACE can name only one product. Choosing CARROT alone would
        # leave one profitable shed slot unused and lose $20 at the terminal
        # market, so the correction must preserve the exact parent DROP.
        out = lane.apply_place_delivery(observation, parent, enabled=True)
        self.assertIs(out, parent)

    def test_out_of_board_sibling_actor_fails_closed_before_valid_overflow_rewrite(self):
        tiles = [["LOCKED"] * 10 for _ in range(10)]
        farm = {"tiles": tiles, "farmer": [4, 4], "hands": [[-1, 4]]}
        prices = {product: 10 for product in r04.PRODUCTS}
        prices["WOOL"] = 20
        observation = {
            "step": 718,
            "player": 0,
            "farms": [farm],
            "private": {
                "shed": {"WHEAT": 99},
                "inventories": [{"WOOL": 2}, {}],
            },
            "market": {"prices": prices},
        }
        parent = {
            "farmer": ["DROP"],
            "hands": [["PASS"]],
            "market": [["SELL", "WHEAT", 99], ["SELL", "WOOL", 1]],
        }

        # The farmer alone is a valid single-product overflow that would become
        # PLACE WOOL 1. The malformed sibling geometry poisons the whole public
        # actor surface, so the hotfix must preserve exact parent identity.
        out = lane.apply_place_delivery(observation, parent, enabled=True)
        self.assertIs(out, parent)

    def test_tuple_drop_cannot_poison_projected_shed_equality(self):
        # Official unit actions are list-only; r04.projected_shed is intentionally
        # lightweight and will interpret a tuple-shaped DROP. With one free slot,
        # that phantom tuple can make parent/candidate projections both say
        # CARROT even though the engine would execute parent CARROT vs candidate
        # WOOL. The terminal rewrite must therefore reject any non-list command.
        tiles = [["LOCKED"] * 10 for _ in range(10)]
        farm = {
            "tiles": tiles,
            "farmer": [4, 4],
            "hands": [[4, 4], [4, 4]],
        }
        prices = {product: 10 for product in r04.PRODUCTS}
        prices["WOOL"] = 100
        observation = {
            "step": 718,
            "player": 0,
            "farms": [farm],
            "private": {
                "shed": {"WHEAT": 99},
                "inventories": [
                    {"CARROT": 1},
                    {"CARROT": 1},
                    {"WOOL": 1},
                ],
            },
            "market": {"prices": prices},
        }
        parent = {
            "farmer": ["DROP"],
            "hands": [("DROP",), ["DROP"]],
            "market": [
                ["SELL", "WHEAT", 99],
                ["SELL", "CARROT", 1],
                ["SELL", "WOOL", 1],
            ],
        }

        # The proof surrogate demonstrates the trap: the tuple consumes the
        # slot in projected_shed(), but the engine's _apply_unit_action() ignores
        # it because it is not a list. Fail closed before using that surrogate.
        view = r04.FarmView(observation)
        self.assertEqual(r04.projected_shed(parent, view)["CARROT"], 1)
        self.assertIs(lane.apply_place_delivery(observation, parent, enabled=True), parent)

    def test_third_player_id_fails_closed_to_exact_parent(self):
        # Official Kaggriculture declares exactly two agents, so player=2 is
        # malformed even if a poisoned observation also supplies a third farm.
        tiles = [["LOCKED"] * 10 for _ in range(10)]
        farm = {"tiles": tiles, "farmer": [4, 4], "hands": []}
        prices = {product: 10 for product in r04.PRODUCTS}
        observation = {
            "step": 718,
            "player": 2,
            "farms": [farm, farm, farm],
            "private": {
                "shed": {"WHEAT": 98},
                "inventories": [{"CARROT": 5}],
            },
            "market": {"prices": prices},
        }
        parent = {
            "farmer": ["DROP"],
            "hands": [],
            "market": [["SELL", "WHEAT", 98], ["SELL", "CARROT", 2]],
        }
        self.assertIs(lane.apply_place_delivery(observation, parent, enabled=True), parent)


if __name__ == "__main__":
    unittest.main()
