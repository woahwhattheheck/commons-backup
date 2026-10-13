#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
OVERLAY = HERE.parent / "overlay"
if str(OVERLAY) not in sys.path:
    sys.path.insert(0, str(OVERLAY))

import b7_shed_room_guard as b7
from r04_full_router import FarmView, projected_shed


def observation(*, shed=None, inventories=None, farmer=(4, 4), hands=None):
    hands = list(hands or [])
    tiles = [[None for _x in range(10)] for _y in range(10)]
    return {
        "step": 500,
        "player": 0,
        "farms": [
            {
                "farmer": list(farmer),
                "hands": [list(position) for position in hands],
                "tiles": tiles,
            }
        ],
        "private": {
            "shed": dict(shed or {}),
            "inventories": [dict(value) if isinstance(value, dict) else value for value in (inventories or [{}])],
        },
        "market": {"prices": {}},
    }


def config(**changes):
    value = {"boardSize": 10, "shedCapacity": 100}
    value.update(changes)
    return value


class ShedRoomGuardTests(unittest.TestCase):
    def setUp(self):
        b7.telemetry.clear()

    def test_disabled_preserves_exact_parent_object(self):
        obs = observation(shed={"MILK": 98}, inventories=[{"WOOL": 7}])
        action = {"farmer": ["DROP"], "hands": [], "market": [["SELL", "MILK", 1]]}
        self.assertIs(b7.transform(obs, action, config(), enabled=False), action)

    def test_single_product_overflow_becomes_exact_room_place(self):
        obs = observation(shed={"MILK": 98}, inventories=[{"WOOL": 7}])
        action = {"farmer": ["DROP"], "hands": [], "market": [["SELL", "MILK", 1]]}
        result = b7.transform(obs, action, config(), enabled=True)
        self.assertEqual(result["farmer"], ["PLACE", "WOOL", 2])
        self.assertEqual(result["market"], action["market"])
        self.assertEqual(action["farmer"], ["DROP"])
        self.assertEqual(b7.telemetry["saved_units"], 5)
        self.assertEqual(b7.telemetry["placed_units"], 2)

    def test_full_shed_turns_lossy_drop_into_pass(self):
        obs = observation(shed={"MILK": 100}, inventories=[{"WOOL": 7}])
        action = {"farmer": ["DROP"], "hands": [], "market": []}
        result = b7.transform(obs, action, config(), enabled=True)
        self.assertEqual(result["farmer"], ["PASS"])
        self.assertEqual(b7.telemetry["saved_units"], 7)
        self.assertEqual(b7.telemetry["full_shed_pass_rows"], 1)

    def test_roomy_drop_is_exact_identity(self):
        obs = observation(shed={"MILK": 90}, inventories=[{"WOOL": 7}])
        action = {"farmer": ["DROP"], "hands": [], "market": []}
        self.assertIs(b7.transform(obs, action, config(), enabled=True), action)

    def test_off_shed_drop_is_exact_identity(self):
        obs = observation(shed={"MILK": 100}, inventories=[{"WOOL": 7}], farmer=(0, 0))
        action = {"farmer": ["DROP"], "hands": [], "market": []}
        self.assertIs(b7.transform(obs, action, config(), enabled=True), action)

    def test_multi_item_inventory_is_not_rewritten(self):
        obs = observation(shed={"MILK": 99}, inventories=[{"WOOL": 7, "EGG": 2}])
        action = {"farmer": ["DROP"], "hands": [], "market": []}
        self.assertIs(b7.transform(obs, action, config(), enabled=True), action)

    def test_animal_inventory_is_not_rewritten(self):
        obs = observation(shed={"MILK": 100}, inventories=[{"SHEEP": 1}])
        action = {"farmer": ["DROP"], "hands": [], "market": []}
        self.assertIs(b7.transform(obs, action, config(), enabled=True), action)

    def test_actor_order_accounts_for_earlier_drop(self):
        obs = observation(
            shed={"WHEAT": 97},
            inventories=[{"MILK": 1}, {"WOOL": 5}],
            hands=[(5, 4)],
        )
        action = {"farmer": ["DROP"], "hands": [["DROP"]], "market": []}
        result = b7.transform(obs, action, config(), enabled=True)
        self.assertEqual(result["farmer"], ["DROP"])
        self.assertEqual(result["hands"], [["PLACE", "WOOL", 2]])
        self.assertEqual(b7.telemetry["saved_units"], 3)

    def test_actor_order_accounts_for_earlier_product_place(self):
        obs = observation(
            shed={"WHEAT": 97},
            inventories=[{"MILK": 2}, {"WOOL": 5}],
            hands=[(5, 4)],
        )
        action = {"farmer": ["PLACE", "MILK", 2], "hands": [["DROP"]], "market": []}
        result = b7.transform(obs, action, config(), enabled=True)
        self.assertEqual(result["farmer"], ["PLACE", "MILK", 2])
        self.assertEqual(result["hands"], [["PLACE", "WOOL", 1]])
        self.assertEqual(b7.telemetry["saved_units"], 4)

    def test_actor_order_prior_pickup_fails_guard_closed(self):
        # Official actor order: actor0 PICKUP frees five slots before actor1 DROP,
        # so the parent can deposit all five WOOL. B7 must not use stale room=0
        # to rewrite actor1 to PASS.
        obs = observation(
            shed={"CARROT": 5, "WHEAT": 95},
            inventories=[{}, {"WOOL": 5}],
            hands=[(5, 4)],
        )
        action = {
            "farmer": ["PICKUP", "CARROT", 5],
            "hands": [["DROP"]],
            "market": [],
        }
        self.assertIs(b7.transform(obs, action, config(), enabled=True), action)
        self.assertEqual(b7.telemetry["changed_actions"], 0)
        self.assertEqual(b7.telemetry["pickup_before_guarded_drop"], 1)

    def test_ambiguous_animal_place_fails_entire_transform_closed(self):
        obs = observation(
            shed={"WHEAT": 100},
            inventories=[{"WOOL": 5}, {"SHEEP": 1}],
            hands=[(5, 4)],
        )
        # Main actor would qualify, but the later shed-adjacent animal PLACE has
        # structure-vs-shed semantics the guard deliberately refuses to model.
        action = {"farmer": ["DROP"], "hands": [["PLACE", "SHEEP", 1]], "market": []}
        self.assertIs(b7.transform(obs, action, config(), enabled=True), action)
        self.assertEqual(b7.telemetry["changed_actions"], 0)

    def test_malformed_later_worker_fails_entire_transform_closed(self):
        obs = observation(
            shed={"WHEAT": 100},
            inventories=[{"WOOL": 5}, {}],
            hands=[(5, 4)],
        )
        action = {"farmer": ["DROP"], "hands": ["PASS"], "market": []}
        self.assertIs(b7.transform(obs, action, config(), enabled=True), action)
        self.assertEqual(b7.telemetry["changed_actions"], 0)

    def test_malformed_later_position_fails_entire_transform_closed(self):
        action = {"farmer": ["DROP"], "hands": [["PASS"]], "market": []}
        for bad_position in ([5], [True, 4], [10, 4], "54"):
            with self.subTest(position=bad_position):
                obs = observation(
                    shed={"WHEAT": 100},
                    inventories=[{"WOOL": 5}, {}],
                    hands=[(5, 4)],
                )
                obs["farms"][0]["hands"][0] = bad_position
                b7.telemetry.clear()
                self.assertIs(b7.transform(obs, action, config(), enabled=True), action)
                self.assertEqual(b7.telemetry["changed_actions"], 0)
                self.assertEqual(b7.telemetry["malformed_position"], 1)

    def test_malformed_inventory_and_config_fail_closed(self):
        action = {"farmer": ["DROP"], "hands": [], "market": []}
        obs = observation(shed={"WHEAT": 100}, inventories=[{"WOOL": True}])
        self.assertIs(b7.transform(obs, action, config(), enabled=True), action)
        for bad in (100.0, "100", True, None):
            with self.subTest(bad=bad):
                obs = observation(shed={"WHEAT": 100}, inventories=[{"WOOL": 5}])
                cfg = config(shedCapacity=bad)
                self.assertIs(b7.transform(obs, action, cfg, enabled=True), action)

    def test_r04_projected_shed_is_identical_after_rewrite(self):
        obs = observation(
            shed={"WHEAT": 97},
            inventories=[{"MILK": 1}, {"WOOL": 5}],
            hands=[(5, 4)],
        )
        action = {
            "farmer": ["DROP"],
            "hands": [["DROP"]],
            "market": [["SELL", "EGG", 1]],
        }
        guarded = b7.transform(obs, action, config(), enabled=True)
        view = FarmView(obs)
        self.assertEqual(projected_shed(action, view), projected_shed(guarded, view))
        self.assertEqual(guarded["market"], action["market"])

    def test_install_disabled_preserves_parent_object(self):
        action = {"farmer": ["DROP"], "hands": [], "market": []}
        obs = observation(shed={"WHEAT": 100}, inventories=[{"WOOL": 5}])

        def parent(_observation, _configuration=None):
            return action

        self.assertIs(b7.install(parent, False)(obs, config()), action)


if __name__ == "__main__":
    unittest.main()
