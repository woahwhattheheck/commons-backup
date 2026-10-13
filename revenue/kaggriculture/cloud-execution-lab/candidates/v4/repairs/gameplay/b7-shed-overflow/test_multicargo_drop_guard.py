#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("_b7_multicargo", HERE / "multicargo_drop_guard.py")
assert SPEC is not None and SPEC.loader is not None
GUARD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GUARD)
CFG = {"boardSize": 10, "shedCapacity": 100}


def observation(room, inventories, positions=None, capacity=100):
    positions = positions or [[4, 4] for _ in inventories]
    shed = {item: 0 for item in sorted(GUARD.CARRYABLE)}
    shed["CARROT"] = capacity - room
    return {
        "player": 0,
        "farms": [{"farmer": positions[0], "hands": positions[1:]}],
        "private": {"shed": shed, "inventories": copy.deepcopy(inventories)},
    }


def action(rows):
    return {"farmer": rows[0], "hands": rows[1:], "market": []}


def project_drop(shed, inventory, capacity=100):
    """Literal capacity/cargo projection of official-engine DROP."""
    out_shed = dict(shed)
    out_inventory = dict(inventory)
    for item, qty in list(out_inventory.items()):
        if qty <= 0:
            del out_inventory[item]
            continue
        room = max(0, capacity - sum(out_shed.values()))
        take = min(qty, room)
        if take > 0:
            out_shed[item] = out_shed.get(item, 0) + take
        del out_inventory[item]
    return out_shed, out_inventory


def project_place(shed, inventory, item, qty, capacity=100):
    out_shed = dict(shed)
    out_inventory = dict(inventory)
    qty = min(qty, out_inventory.get(item, 0))
    room = max(0, capacity - sum(out_shed.values()))
    qty = min(qty, room)
    if qty > 0:
        out_inventory[item] -= qty
        if out_inventory[item] == 0:
            del out_inventory[item]
        out_shed[item] = out_shed.get(item, 0) + qty
    return out_shed, out_inventory


class MultiCargoDropGuardTest(unittest.TestCase):
    def test_disabled_preserves_exact_identity(self):
        parent = action([["DROP"]])
        before_disabled = GUARD.telemetry["disabled"]
        before_invalid = GUARD.telemetry["invalid_enabled"]
        self.assertIs(GUARD.transform(observation(0, [{"MILK": 2, "WOOL": 3}]), parent, CFG), parent)
        self.assertEqual(GUARD.telemetry["disabled"], before_disabled + 1)
        self.assertEqual(GUARD.telemetry["invalid_enabled"], before_invalid)

    def test_nonbool_enable_poison_fails_closed_before_state_read(self):
        parent = action([["DROP"]])
        poisons = (None, 0, 1, 1.0, "false", [True], {"enabled": True}, object())
        before_invalid = GUARD.telemetry["invalid_enabled"]
        before_changed = GUARD.telemetry["changed_actions"]
        for bad in poisons:
            with self.subTest(bad=repr(bad)):
                self.assertIs(GUARD.transform(object(), parent, object(), enabled=bad), parent)
        self.assertEqual(GUARD.telemetry["invalid_enabled"], before_invalid + len(poisons))
        self.assertEqual(GUARD.telemetry["changed_actions"], before_changed)

    def test_install_metadata_is_literal_true_only(self):
        parent_action = action([["DROP"]])

        def parent(_observation, _configuration=None):
            return parent_action

        for bad in (None, 0, 1, 1.0, "false", [True], {"enabled": True}, object()):
            with self.subTest(bad=repr(bad)):
                agent = GUARD.install(parent, enabled=bad)
                self.assertFalse(agent.b7_multicargo_enabled)
                self.assertIs(agent(object(), object()), parent_action)
        self.assertTrue(GUARD.install(parent, enabled=True).b7_multicargo_enabled)
        self.assertFalse(GUARD.install(parent, enabled=False).b7_multicargo_enabled)

    def test_full_shed_multicargo_becomes_pass(self):
        parent = action([["DROP"]])
        obs = observation(0, [{"MILK": 2, "WOOL": 3}])
        out = GUARD.transform(obs, parent, CFG, enabled=True)
        self.assertEqual(out["farmer"], ["PASS"])
        original_shed, original_inv = project_drop(obs["private"]["shed"], obs["private"]["inventories"][0])
        self.assertEqual(original_shed, obs["private"]["shed"])
        self.assertEqual(original_inv, {})
        self.assertEqual(obs["private"]["inventories"][0], {"MILK": 2, "WOOL": 3})

    def test_full_shed_animal_first_is_still_exact_pass(self):
        parent = action([["DROP"]])
        out = GUARD.transform(observation(0, [{"GOOSE": 1, "MILK": 3}]), parent, CFG, enabled=True)
        self.assertEqual(out["farmer"], ["PASS"])

    def test_first_product_exceeds_room(self):
        parent = action([["DROP"]])
        obs = observation(2, [{"MILK": 5, "WOOL": 3}])
        out = GUARD.transform(obs, parent, CFG, enabled=True)
        self.assertEqual(out["farmer"], ["PLACE", "MILK", 2])
        drop_shed, _ = project_drop(obs["private"]["shed"], obs["private"]["inventories"][0])
        place_shed, place_inv = project_place(obs["private"]["shed"], obs["private"]["inventories"][0], "MILK", 2)
        self.assertEqual(place_shed, drop_shed)
        self.assertEqual(place_inv, {"MILK": 3, "WOOL": 3})

    def test_first_product_exactly_fills_room_and_saves_later_cargo(self):
        parent = action([["DROP"]])
        obs = observation(2, [{"MILK": 2, "WOOL": 3}])
        out = GUARD.transform(obs, parent, CFG, enabled=True)
        self.assertEqual(out["farmer"], ["PLACE", "MILK", 2])
        drop_shed, _ = project_drop(obs["private"]["shed"], obs["private"]["inventories"][0])
        place_shed, place_inv = project_place(obs["private"]["shed"], obs["private"]["inventories"][0], "MILK", 2)
        self.assertEqual(place_shed, drop_shed)
        self.assertEqual(place_inv, {"WOOL": 3})

    def test_spanning_two_products_fails_closed(self):
        parent = action([["DROP"]])
        self.assertIs(GUARD.transform(observation(2, [{"MILK": 1, "WOOL": 3}]), parent, CFG, enabled=True), parent)

    def test_zero_quantity_key_fails_that_drop_closed(self):
        parent = action([["DROP"]])
        obs = observation(0, [{"MILK": 2, "WOOL": 0}])
        self.assertIs(GUARD.transform(obs, parent, CFG, enabled=True), parent)
        drop_shed, drop_inv = project_drop(obs["private"]["shed"], obs["private"]["inventories"][0])
        self.assertEqual(drop_shed, obs["private"]["shed"])
        self.assertEqual(drop_inv, {})

    def test_animal_first_with_room_fails_closed(self):
        parent = action([["DROP"]])
        self.assertIs(GUARD.transform(observation(2, [{"GOOSE": 5, "MILK": 3}]), parent, CFG, enabled=True), parent)

    def test_prior_product_place_updates_later_room(self):
        parent = action([["PLACE", "EGG", 2], ["DROP"]])
        obs = observation(3, [{"EGG": 2}, {"MILK": 5, "WOOL": 2}])
        out = GUARD.transform(obs, parent, CFG, enabled=True)
        self.assertEqual(out["farmer"], ["PLACE", "EGG", 2])
        self.assertEqual(out["hands"][0], ["PLACE", "MILK", 1])

    def test_prior_drop_updates_later_room(self):
        parent = action([["DROP"], ["DROP"]])
        obs = observation(3, [{"EGG": 2}, {"MILK": 5, "WOOL": 2}])
        out = GUARD.transform(obs, parent, CFG, enabled=True)
        self.assertEqual(out["farmer"], ["DROP"])
        self.assertEqual(out["hands"][0], ["PLACE", "MILK", 1])

    def test_prior_pickup_fails_entire_transform_closed(self):
        parent = action([["PICKUP", "WHEAT", 1], ["DROP"]])
        obs = observation(2, [{}, {"MILK": 5, "WOOL": 2}])
        obs["private"]["shed"]["WHEAT"] = 1
        obs["private"]["shed"]["CARROT"] -= 1
        self.assertIs(GUARD.transform(obs, parent, CFG, enabled=True), parent)

    def test_unknown_cargo_and_overcapacity_fail_closed(self):
        parent = action([["DROP"]])
        obs = observation(0, [{"MYSTERY": 2}])
        self.assertIs(GUARD.transform(obs, parent, CFG, enabled=True), parent)
        obs = observation(0, [{"MILK": 2}])
        obs["private"]["shed"]["WOOL"] = 1
        self.assertIs(GUARD.transform(obs, parent, CFG, enabled=True), parent)

    def test_nonadjacent_and_bool_config_fail_closed(self):
        parent = action([["DROP"]])
        self.assertIs(GUARD.transform(observation(0, [{"MILK": 2}], positions=[[0, 0]]), parent, CFG, enabled=True), parent)
        self.assertIs(GUARD.transform(observation(0, [{"MILK": 2}]), parent, {"boardSize": 10, "shedCapacity": True}, enabled=True), parent)

    def test_parent_action_is_not_mutated(self):
        parent = action([["DROP"]])
        before = copy.deepcopy(parent)
        out = GUARD.transform(observation(2, [{"MILK": 5, "WOOL": 3}]), parent, CFG, enabled=True)
        self.assertEqual(parent, before)
        self.assertIsNot(out, parent)


if __name__ == "__main__":
    unittest.main()
