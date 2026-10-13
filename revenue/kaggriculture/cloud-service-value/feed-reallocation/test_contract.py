# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from copy import deepcopy
import unittest

import feed_reallocation as F


class Mechanics:
    ANIMALS = {"COW": {"product": "MILK"}}


class FeedReallocationContractTests(unittest.TestCase):
    def states(self):
        tile = {
            "kind": "PASTURE", "animal": "COW", "fed_today": False,
            "consecutive_unfed": 0, "pending_care_bonus": 2,
            "yield_units": 0,
        }
        base = {
            "farm": {"tiles": [[deepcopy(tile)]]},
            "private": {"shed": {"WHEAT": 4}},
        }
        candidate = deepcopy(base)
        candidate["private"]["shed"]["WHEAT"] = 5
        candidate["farm"]["tiles"][0][0]["consecutive_unfed"] = 1
        candidate["farm"]["tiles"][0][0]["pending_care_bonus"] = 1
        return base, candidate

    def test_exact_exchange_is_recognized(self):
        base, candidate = self.states()
        report = F._exchange(base, candidate, Mechanics)
        self.assertEqual(report["saved_product"], "WHEAT")
        self.assertEqual(report["deferred_product"], "MILK")
        self.assertEqual(report["saved_units"], 1)
        self.assertEqual(report["deferred_bonus_units"], 1)

    def test_extra_physical_change_rejects_exchange(self):
        base, candidate = self.states()
        candidate["farm"]["tiles"][0][0]["yield_units"] = 1
        self.assertIsNone(F._exchange(base, candidate, Mechanics))

    def test_escape_boundary_rejects_exchange(self):
        base, candidate = self.states()
        candidate["farm"]["tiles"][0][0]["consecutive_unfed"] = 2
        self.assertIsNone(F._exchange(base, candidate, Mechanics))

    def test_market_and_other_units_are_preserved(self):
        selected = {"farmer": ["PASS"], "hands": [["HARVEST"], ["CARE"]],
                    "market": [["SELL", "WHEAT", 2]]}
        out = F._put_units(selected, [["PASS"], ["FEED"], ["CARE"]])
        self.assertEqual(out["market"], selected["market"])
        self.assertEqual(out["hands"][1], selected["hands"][1])
        self.assertEqual(selected["hands"][0], ["HARVEST"])

    def test_sale_search_stops_at_checkpoint(self):
        route = [{"market": []} for _ in range(8)]
        route[5]["market"] = [["SELL", "WHEAT", 1]]
        self.assertEqual(F._sale_step(route, 3, "WHEAT", (), 8), 5)
        self.assertIsNone(F._sale_step(route, 3, "WHEAT", (4,), 8))

    def test_malformed_input_preserves_complete_action(self):
        selected = {"farmer": ["PASS"], "hands": [], "market": []}
        out, report = F.propose_feed_reallocation(
            Mechanics, {}, {}, selected, route=[], route_switch_steps=())
        self.assertEqual(out, selected)
        self.assertEqual(report["status"], "unchanged")
        self.assertEqual(report["controller_calls"], 0)


if __name__ == "__main__":
    unittest.main()
