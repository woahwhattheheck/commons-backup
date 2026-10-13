# SPDX-License-Identifier: Apache-2.0
"""Source-custody contracts for the recovered V4 S1 wheat-fertilize helper."""
from __future__ import annotations

import copy
import unittest

import r04_wheat_fert as wf


def _tile(**overrides):
    tile = {
        "kind": "PLANT", "crop": "WHEAT", "planted_day": 4,
        "yield_units": 0, "fertilized_until_day": 0,
        "watered_today": False, "consecutive_unwatered": 0,
    }
    tile.update(overrides)
    return tile


def _obs(*, step=121, tile=None, inventory=None, shed=None, prices=None,
         player=0, hands=None, position=(1, 1)):
    board = [[None for _ in range(10)] for _ in range(10)]
    board[position[1]][position[0]] = tile
    hands = [] if hands is None else hands
    farm = {"farmer": list(position), "hands": hands, "tiles": board}
    other = {"farmer": [0, 0], "hands": [],
             "tiles": [[None for _ in range(10)] for _ in range(10)]}
    return {
        "step": step, "player": player, "farms": [farm, other],
        "private": {"inventories": [inventory or {}, *({} for _ in hands)],
                    "shed": shed or {}},
        "market": {"prices": prices or {"WHEAT": 100, "CARROT": 100,
                                        "MELON": 100, "FERTILIZER": 10}},
    }


def _action(command=None, market=None, hands=None):
    return {"farmer": command or ["WATER"], "hands": hands or [],
            "market": market or []}


class WheatFertilizeRecoveryTest(unittest.TestCase):
    def setUp(self):
        wf._STATE.clear()
        for key in list(wf.REPORT):
            wf.REPORT[key] = 0
        wf.SWAP_AGE1 = True
        wf.SWAP_AGE2 = True
        wf.RETAIN = False
        wf.PICKUP_PASS = False
        wf.ALT_GATE = True
        wf.CREDIT = True
        wf.FERT_MAX = 30
        wf.SHED_MAX = 85

    def test_disabled_is_exact_parent_identity(self):
        action = _action()
        self.assertIs(wf.apply_wheat_fertilize(
            _obs(tile=_tile(), inventory={"FERTILIZER": 1}), action, False), action)

    def test_age1_water_becomes_fertilize(self):
        action = _action()
        out = wf.apply_wheat_fertilize(
            _obs(tile=_tile(), inventory={"FERTILIZER": 1}), action, True)
        self.assertEqual(out["farmer"], ["FERTILIZE"])
        self.assertEqual(action["farmer"], ["WATER"])
        self.assertEqual(wf.REPORT["swap_units"], 2)

    def test_expensive_fertilizer_blocks(self):
        action = _action()
        observation = _obs(tile=_tile(), inventory={"FERTILIZER": 1},
            prices={"WHEAT": 100, "CARROT": 100, "MELON": 100, "FERTILIZER": 31})
        self.assertIs(wf.apply_wheat_fertilize(observation, action, True), action)
        self.assertEqual(wf.REPORT["declined_price"], 1)

    def test_tight_shed_blocks(self):
        action = _action()
        observation = _obs(tile=_tile(), inventory={"FERTILIZER": 1}, shed={"STRAWBERRY": 86})
        self.assertIs(wf.apply_wheat_fertilize(observation, action, True), action)
        self.assertEqual(wf.REPORT["declined_shed"], 1)

    def test_weed_risk_blocks(self):
        action = _action()
        observation = _obs(tile=_tile(consecutive_unwatered=1), inventory={"FERTILIZER": 1})
        self.assertIs(wf.apply_wheat_fertilize(observation, action, True), action)

    def test_bool_player_is_not_an_integer_seat(self):
        action = _action()
        observation = _obs(tile=_tile(), inventory={"FERTILIZER": 1}, player=True)
        self.assertIs(wf.apply_wheat_fertilize(observation, action, True), action)

    def test_higher_value_alternative_blocks(self):
        observation = _obs(tile=_tile(), inventory={"FERTILIZER": 1})
        observation["farms"][0]["tiles"][2][2] = _tile(crop="CARROT", planted_day=3, yield_units=0)
        observation["market"]["prices"]["CARROT"] = 1000
        action = _action()
        self.assertIs(wf.apply_wheat_fertilize(observation, action, True), action)
        self.assertEqual(wf.REPORT["declined_alt"], 1)

    def test_credit_bumps_existing_wheat_sale_by_added_units(self):
        first = _action()
        first_out = wf.apply_wheat_fertilize(_obs(tile=_tile(), inventory={"FERTILIZER": 1}), first, True)
        self.assertEqual(first_out["farmer"], ["FERTILIZE"])
        second_obs = _obs(step=122, tile=_tile(yield_units=6), shed={"WHEAT": 10})
        second = _action(["HARVEST"], [["SELL", "WHEAT", 5]])
        out = wf.apply_wheat_fertilize(second_obs, second, True)
        self.assertEqual(out["market"], [["SELL", "WHEAT", 7]])
        self.assertEqual(wf.REPORT["credit_units"], 2)
        self.assertEqual(wf.REPORT["sold_units"], 2)

    def test_credit_never_crosses_same_item_buy(self):
        wf.apply_wheat_fertilize(_obs(tile=_tile(), inventory={"FERTILIZER": 1}), _action(), True)
        observation = _obs(step=122, tile=_tile(yield_units=6), shed={"WHEAT": 10})
        action = _action(["HARVEST"], [["BUY_PRODUCT", "WHEAT", 1], ["SELL", "WHEAT", 5]])
        out = wf.apply_wheat_fertilize(observation, action, True)
        self.assertEqual(out["market"], action["market"])
        self.assertEqual(wf.REPORT["sold_units"], 0)

    def test_terminal_cutoff_is_exact_parent_identity(self):
        action = _action()
        observation = _obs(step=700, tile=_tile(planted_day=28), inventory={"FERTILIZER": 1})
        self.assertIs(wf.apply_wheat_fertilize(observation, action, True), action)


if __name__ == "__main__":
    unittest.main()
