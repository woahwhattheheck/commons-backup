# SPDX-License-Identifier: Apache-2.0
"""Focused S2 fail-closed numeric and activation custody regressions."""
from __future__ import annotations

import copy
import importlib.util
import os
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
SOURCE_OVERRIDE = os.environ.get("S2_SOURCE")
SOURCE = (Path(SOURCE_OVERRIDE) if SOURCE_OVERRIDE else
          HERE.parents[2] / "donor/overlay/r04_s2_sheep_swap.py")
SPEC = importlib.util.spec_from_file_location("s2_numeric_custody_source", SOURCE)
s2 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(s2)

CFG = dict(episodeSteps=720, boardSize=10, turnsPerDay=24,
           shedCapacity=100, maxMarketOrdersPerTurn=10)


def action(market=None, farmer=None, hands=None):
    return {
        "farmer": ["PASS"] if farmer is None else farmer,
        "hands": [["PASS"]] if hands is None else hands,
        "market": [] if market is None else market,
    }


def tape():
    return [action() for _ in range(720)]


def observation(step=100):
    board0 = [[None for _ in range(10)] for _ in range(10)]
    board1 = [[None for _ in range(10)] for _ in range(10)]
    return {
        "step": step,
        "player": 0,
        "farms": [
            {"money": 1000, "tiles": board0, "farmer": [4, 4],
             "hands": [[4, 4]], "hires_today": 0},
            {"money": 1000, "tiles": board1, "farmer": [4, 4],
             "hands": [[4, 4]], "hires_today": 0},
        ],
        "private": {"shed": {}, "inventories": [{}, {}]},
        "town": {"unlocked_shops": ["YARN_STORE"]},
        "market": {"prices": {"WOOL": 200, "MILK": 100}},
    }


class FailClosedNumericCustody(unittest.TestCase):
    def invoke(self, obs, parent, state, *, enabled=True):
        return s2.apply_s2_swap(obs, parent, state, enabled=enabled,
                                configuration=CFG, native_tape=tape())

    def assert_exact_parent_and_state(self, obs, parent, state, *, enabled=True):
        before = copy.deepcopy(state)
        returned = self.invoke(obs, parent, state, enabled=enabled)
        self.assertIs(returned, parent)
        self.assertEqual(state, before)

    def test_non_literal_true_activation_fails_closed(self):
        for enabled in (1, "yes", 1.0):
            with self.subTest(enabled=enabled):
                self.assert_exact_parent_and_state(
                    observation(), action([["BUY_ANIMAL", "COW", 1]]),
                    s2.new_state(), enabled=enabled)

    def test_observation_numeric_poison_fails_before_state_mutation(self):
        poisons = (
            ("shed-string", lambda o: o["private"]["shed"].__setitem__("SHEEP", "1")),
            ("inventory-bool", lambda o: o["private"]["inventories"][0].__setitem__("COW", True)),
            ("price-string", lambda o: o["market"]["prices"].__setitem__("WOOL", "200")),
            ("money-float", lambda o: o["farms"][0].__setitem__("money", 1000.0)),
            ("negative-stock", lambda o: o["private"]["shed"].__setitem__("WOOL", -1)),
            ("prices-none", lambda o: o["market"].__setitem__("prices", None)),
            ("shops-none", lambda o: o["town"].__setitem__("unlocked_shops", None)),
        )
        for label, poison in poisons:
            with self.subTest(label=label):
                obs = observation(); poison(obs)
                self.assert_exact_parent_and_state(
                    obs, action([["BUY_ANIMAL", "COW", 1]]), s2.new_state())

    def test_action_and_tile_numeric_poison_fail_before_state_mutation(self):
        cases = []
        obs = observation(); obs["private"]["shed"] = {"SHEEP": 1}
        cases.append(("pickup-string", obs, action(farmer=["PICKUP", "COW", "1"])))
        cases.append(("place-bool", observation(), action(farmer=["PLACE", "COW", True])))
        cases.append(("sell-string", observation(), action([["SELL", "WOOL", "3"]])))
        cases.append(("sell-other-string", observation(), action([["SELL", "CARROT", "1"]])))
        cases.append(("buy-string", observation(), action([["BUY_ANIMAL", "COW", "1"]])))
        cases.append(("buy-negative", observation(), action([["BUY_ANIMAL", "COW", -1]])))
        harvest = observation(); harvest["private"]["shed"] = {"WOOL": 5}
        harvest["farms"][0]["tiles"][4][4] = {
            "kind": "PASTURE", "animal": "SHEEP", "placed_day": 4, "yield_units": "2"
        }
        cases.append(("yield-string", harvest, action([["SELL", "WOOL", 3]], farmer=["HARVEST"])))
        for label, obs, parent in cases:
            with self.subTest(label=label):
                state = s2.new_state(); state["last"] = 99
                if label == "yield-string": state["sites"] = {(4, 4): 4}
                if label == "pickup-string": state["reserved"] = 1
                self.assert_exact_parent_and_state(obs, parent, state)

    def test_valid_owned_buy_behavior_is_preserved(self):
        state = s2.new_state()
        parent = action([["BUY_ANIMAL", "COW", 1]])
        returned = self.invoke(observation(), parent, state)
        self.assertEqual(returned["market"], [["BUY_ANIMAL", "SHEEP", 1]])
        self.assertEqual(parent["market"], [["BUY_ANIMAL", "COW", 1]])
        self.assertEqual(state["requested"], 1)
        self.assertEqual(state["pending_buy"], {"before": 0, "quantity": 1})


if __name__ == "__main__":
    unittest.main()
