# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
LAB = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(LAB))

import mechanics as m
from overflow_safe_drop import transform


def farm(*, farmer=None, hands=None):
    return {
        "farmer": list(farmer or [4, 4]),
        "hands": deepcopy(hands or []),
        "tiles": [[None for _ in range(10)] for _ in range(10)],
        "money": 10000,
        "unlocked_quadrants": ["NW"],
        "hires_today": len(hands or []),
    }


def obs(*, shed=None, inventories=None, farmer=None, hands=None):
    own = farm(farmer=farmer, hands=hands)
    return {
        "step": 500,
        "player": 0,
        "farms": [own, farm(farmer=[4, 4])],
        "private": {
            "shed": deepcopy(shed or {}),
            "inventories": deepcopy(inventories or [{}]),
            "seeds": {},
        },
        "market": {"inventory": {}, "prices": {}},
    }


def selected(*, farmer=None, hands=None, market=None):
    return {
        "farmer": deepcopy(farmer or ["PASS"]),
        "hands": deepcopy(hands or []),
        "market": deepcopy(market or []),
    }


class OverflowSafeDropTests(unittest.TestCase):
    def test_partial_place_matches_drop_shed_effect_and_preserves_overflow(self):
        observation = obs(shed={"MELON": 98}, inventories=[{"MELON": 5}])
        action = selected(farmer=["DROP"], market=[["SELL", "MELON", 2]])
        before = deepcopy((observation, action))

        result, report = transform(action, observation, {})
        self.assertEqual(result["farmer"], ["PLACE", "MELON", 2])
        self.assertEqual(result["market"], action["market"])
        self.assertEqual(report["baseline_same_item_stock"], 100)
        self.assertEqual(report["preserved_in_pocket_lower_bound"], 3)
        self.assertTrue(report["same_tick_shed_effect_preserved"])
        self.assertEqual((observation, action), before)

        base_farm = deepcopy(observation["farms"][0])
        base_private = deepcopy(observation["private"])
        cand_farm = deepcopy(base_farm)
        cand_private = deepcopy(base_private)
        m._apply_unit_action(base_farm, base_private, 0, ["DROP"], 10, 20, 24, 100)
        m._apply_unit_action(cand_farm, cand_private, 0, result["farmer"], 10, 20, 24, 100)
        self.assertEqual(base_farm, cand_farm)
        self.assertEqual(base_private["shed"], cand_private["shed"])
        self.assertEqual(base_private["inventories"][0], {})
        self.assertEqual(cand_private["inventories"][0], {"MELON": 3})

    def test_full_same_item_shed_turns_destructive_drop_into_pass(self):
        observation = obs(shed={"MELON": 100}, inventories=[{"MELON": 5}])
        action = selected(farmer=["DROP"], market=[["SELL", "MELON", 1]])
        result, report = transform(action, observation, {})
        self.assertEqual(result["farmer"], ["PASS"])
        self.assertEqual(report["shed_room"], 0)
        self.assertEqual(report["baseline_same_item_stock"], 100)
        self.assertEqual(report["preserved_in_pocket_lower_bound"], 5)

        base_farm = deepcopy(observation["farms"][0])
        base_private = deepcopy(observation["private"])
        cand_farm = deepcopy(base_farm)
        cand_private = deepcopy(base_private)
        m._apply_unit_action(base_farm, base_private, 0, ["DROP"], 10, 20, 24, 100)
        m._apply_unit_action(cand_farm, cand_private, 0, ["PASS"], 10, 20, 24, 100)
        self.assertEqual(base_private["shed"], cand_private["shed"])
        self.assertEqual(base_private["inventories"][0], {})
        self.assertEqual(cand_private["inventories"][0], {"MELON": 5})

    def test_full_other_item_shed_has_no_executable_same_item_sell(self):
        observation = obs(shed={"WOOL": 100}, inventories=[{"MELON": 5}])
        action = selected(farmer=["DROP"], market=[["SELL", "MELON", 1]])
        result, report = transform(action, observation, {})
        self.assertIs(result, action)
        self.assertEqual(report["reason"], "no_same_item_executable_sell")

    def test_hand_actor_rewrites_in_place_without_reordering(self):
        observation = obs(
            shed={"MILK": 99},
            inventories=[{}, {"MILK": 4}],
            hands=[[5, 4]],
        )
        action = selected(
            farmer=["PASS"], hands=[["DROP"]],
            market=[["SELL", "MILK", "2", "metadata"], ["BUY_SEED", "CARROT", 1]],
        )
        result, report = transform(action, observation, {})
        self.assertEqual(result["farmer"], ["PASS"])
        self.assertEqual(result["hands"], [["PLACE", "MILK", 1]])
        self.assertEqual(result["market"], action["market"])
        self.assertEqual(report["actor"], 1)

    def test_no_overflow_is_identity(self):
        observation = obs(shed={"MELON": 95}, inventories=[{"MELON": 5}])
        action = selected(farmer=["DROP"], market=[["SELL", "MELON", 2]])
        result, report = transform(action, observation, {})
        self.assertIs(result, action)
        self.assertEqual(report["reason"], "drop_has_no_overflow")

    def test_multi_item_pocket_is_identity(self):
        observation = obs(shed={"MELON": 99}, inventories=[{"MELON": 4, "WOOL": 1}])
        action = selected(farmer=["DROP"], market=[["SELL", "MELON", 2]])
        result, report = transform(action, observation, {})
        self.assertIs(result, action)
        self.assertEqual(report["reason"], "ambiguous_worker_inventory")

    def test_zero_valued_extra_inventory_key_is_identity(self):
        observation = obs(shed={"MELON": 99}, inventories=[{"MELON": 4, "WOOL": 0}])
        action = selected(farmer=["DROP"], market=[["SELL", "MELON", 2]])
        result, report = transform(action, observation, {})
        self.assertIs(result, action)
        self.assertEqual(report["reason"], "ambiguous_worker_inventory")

        # Predecessor killer: engine DROP deletes even the zero-valued WOOL key,
        # while the previously admitted partial PLACE would have preserved it.
        base_farm = deepcopy(observation["farms"][0])
        base_private = deepcopy(observation["private"])
        unsafe_farm = deepcopy(base_farm)
        unsafe_private = deepcopy(base_private)
        m._apply_unit_action(base_farm, base_private, 0, ["DROP"], 10, 20, 24, 100)
        m._apply_unit_action(unsafe_farm, unsafe_private, 0, ["PLACE", "MELON", 1], 10, 20, 24, 100)
        self.assertEqual(base_private["shed"], unsafe_private["shed"])
        self.assertEqual(base_private["inventories"][0], {})
        self.assertEqual(unsafe_private["inventories"][0], {"MELON": 3, "WOOL": 0})
        self.assertNotEqual(base_private, unsafe_private)

    def test_operating_inputs_are_out_of_scope(self):
        for item in ("WHEAT", "FERTILIZER"):
            with self.subTest(item=item):
                observation = obs(shed={item: 99}, inventories=[{item: 4}])
                action = selected(farmer=["DROP"], market=[["SELL", item, 2]])
                result, report = transform(action, observation, {})
                self.assertIs(result, action)
                self.assertEqual(report["reason"], "operating_or_unsupported_item")

    def test_same_item_executable_sell_is_required(self):
        observation = obs(shed={"MELON": 99}, inventories=[{"MELON": 4}])
        for rows in (
            [],
            [["SELL", "WOOL", 2]],
            [["SELL", "MELON"]],
            [["SELL", "MELON", 0]],
            [["SELL", "MELON", "x"]],
            [["SELL", "MELON", float("inf")]],
        ):
            with self.subTest(rows=rows):
                action = selected(farmer=["DROP"], market=rows)
                result, report = transform(action, observation, {})
                self.assertIs(result, action)
                self.assertEqual(report["reason"], "no_same_item_executable_sell")

    def test_engine_quantity_coercion_and_trailing_sell_are_admitted(self):
        observation = obs(shed={"MELON": 99}, inventories=[{"MELON": 4}])
        for quantity in (True, 2.9, "2"):
            with self.subTest(quantity=quantity):
                action = selected(
                    farmer=["DROP"],
                    market=[["SELL", "MELON", quantity, "trailing"]],
                )
                result, report = transform(action, observation, {})
                self.assertEqual(result["farmer"], ["PLACE", "MELON", 1])
                self.assertTrue(report["changed"])

    def test_multiple_shed_unit_actions_are_identity(self):
        observation = obs(
            shed={"MELON": 99}, inventories=[{"MELON": 4}, {}], hands=[[5, 4]])
        action = selected(
            farmer=["DROP"], hands=[["PICKUP", "WOOL", 1]],
            market=[["SELL", "MELON", 2]],
        )
        result, report = transform(action, observation, {})
        self.assertIs(result, action)
        self.assertEqual(report["reason"], "ambiguous_shed_unit_sequence")

    def test_malformed_prefix_and_nonstandard_config_fail_closed(self):
        observation = obs(shed={"MELON": 99}, inventories=[{"MELON": 4}])
        action = selected(farmer=["DROP"], market=[17, ["SELL", "MELON", 2]])
        result, report = transform(action, observation, {})
        self.assertIs(result, action)
        self.assertEqual(report["reason"], "malformed_market_prefix")

        action = selected(farmer=["DROP"], market=[["SELL", "MELON", 2]])
        for cfg, reason in (([], "malformed_input"),
                            ("", "malformed_input"),
                            (0, "malformed_input"),
                            (False, "malformed_input"),
                            ({"shedCapacity": 99}, "outside_standard_config"),
                            ({"boardSize": 8}, "outside_standard_config"),
                            ({"maxMarketOrdersPerTurn": 9}, "outside_standard_config")):
            with self.subTest(cfg=cfg):
                result, report = transform(action, observation, cfg)
                self.assertIs(result, action)
                self.assertEqual(report["reason"], reason)

    def test_public_identity_is_exact(self):
        action = selected(farmer=["DROP"], market=[["SELL", "MELON", 2]])
        for player, step in ((True, 500), (0, True), (2, 500), (0, -1), ("0", 500)):
            with self.subTest(player=player, step=step):
                observation = obs(shed={"MELON": 99}, inventories=[{"MELON": 4}])
                observation["player"] = player
                observation["step"] = step
                result, report = transform(action, observation, {})
                self.assertIs(result, action)
                self.assertEqual(report["reason"], "malformed_public_identity")


if __name__ == "__main__":
    unittest.main(verbosity=2)