# SPDX-License-Identifier: Apache-2.0
"""S2 persistent-state shape must fail closed before any lane mutation."""
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parents[2] / "donor/overlay/r04_s2_sheep_swap.py"
SPEC = importlib.util.spec_from_file_location("s2_state_custody_source", SOURCE)
s2 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(s2)

CFG = dict(episodeSteps=720, boardSize=10, turnsPerDay=24,
           shedCapacity=100, maxMarketOrdersPerTurn=10)


def action():
    return {"farmer": ["PASS"], "hands": [["PASS"]],
            "market": [["BUY_ANIMAL", "COW", 1]]}


def tape():
    return [{"farmer": ["PASS"], "hands": [["PASS"]], "market": []}
            for _ in range(720)]


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


class PersistentStateFailClosed(unittest.TestCase):
    def assert_rejected_without_mutation(self, state):
        parent = action()
        before = copy.deepcopy(state)
        returned = s2.apply_s2_swap(
            observation(), parent, state,
            enabled=True, configuration=CFG, native_tape=tape())
        self.assertIs(returned, parent)
        self.assertEqual(state, before)

    def test_last_type_poison_fails_closed(self):
        state = s2.new_state(); state["last"] = "99"
        self.assert_rejected_without_mutation(state)

    def test_pending_buy_shape_poison_fails_closed(self):
        state = s2.new_state(); state["last"] = 99; state["pending_buy"] = 1
        self.assert_rejected_without_mutation(state)

    def test_pending_places_container_poison_fails_closed(self):
        state = s2.new_state(); state["last"] = 99; state["pending_places"] = None
        self.assert_rejected_without_mutation(state)

    def test_state_mapping_poison_fails_closed(self):
        parent = action()
        state = None
        returned = s2.apply_s2_swap(
            observation(), parent, state,
            enabled=True, configuration=CFG, native_tape=tape())
        self.assertIs(returned, parent)


if __name__ == "__main__":
    unittest.main()
