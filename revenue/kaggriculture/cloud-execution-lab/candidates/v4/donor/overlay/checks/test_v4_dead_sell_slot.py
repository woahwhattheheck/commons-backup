# SPDX-License-Identifier: Apache-2.0
"""Focused regressions for the V4 DEAD-SELL-SLOT fold-in."""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import r04_dead_sell_slot as lane  # noqa: E402
import r04_full_router as r04  # noqa: E402


def observation(*, shed=None, inventories=None, farmer=None, hands=None, prices=None):
    farmer = farmer or [0, 0]
    hands = hands or []
    tiles = [[None for _ in range(10)] for _ in range(10)]
    products = {item: 10 for item in r04.PRODUCTS}
    products.update(prices or {})
    return {
        "step": 1,
        "player": 0,
        "farms": [{"tiles": tiles, "farmer": farmer, "hands": hands}],
        "private": {
            "shed": dict(shed or {}),
            "inventories": list(inventories or [{} for _ in range(1 + len(hands))]),
        },
        "market": {"prices": products, "inventory": {item: 10000 for item in r04.PRODUCTS}},
        "town": {"unlocked_shops": []},
    }


def action(market, farmer=None, hands=None):
    return {
        "farmer": farmer or ["PASS"],
        "hands": list(hands or []),
        "market": market,
    }


def hires(count):
    return [["HIRE"] for _ in range(count)]


class DeadSellSlot(unittest.TestCase):
    def test_disabled_is_exact_parent(self):
        parent = action(hires(9) + [["SELL", "WOOL", 1]])
        view = r04.FarmView(observation())
        self.assertIs(lane.prune_trailing_dead_sells(parent, view, enabled=False), parent)

    def test_trailing_zero_stock_nonbuyable_is_removed_when_saturated(self):
        prefix = hires(9)
        parent = action(prefix + [["SELL", "WOOL", 1]])
        view = r04.FarmView(observation())
        out = lane.prune_trailing_dead_sells(parent, view, enabled=True)
        self.assertIsNot(out, parent)
        self.assertEqual(out["market"], prefix)
        self.assertIs(out["market"][0], parent["market"][0])

    def test_multiple_dead_suffix_rows_are_removed_from_saturated_queue(self):
        prefix = hires(7) + [["SELL", "MILK", 1]]
        parent = action(prefix + [
            ["SELL", "EGG", 0],
            ["SELL", "WOOL", 4],
        ])
        view = r04.FarmView(observation(shed={"MILK": 2}))
        out = lane.prune_trailing_dead_sells(parent, view, enabled=True)
        self.assertEqual(out["market"], prefix)

    def test_unsaturated_dead_tail_is_exact_parent_and_keeps_append_index(self):
        parent = action([["HIRE"], ["SELL", "WOOL", 1]])
        obs = observation(shed={"MILK": 2}, prices={"MILK": 160})
        view = r04.FarmView(obs)
        tape = [{"market": []} for _ in range(3)]
        tape[2] = {"market": [["SELL", "MILK", 2]]}

        candidate = lane.prune_trailing_dead_sells(parent, view, enabled=True)
        self.assertIs(candidate, parent)

        baseline = copy.deepcopy(parent)
        baseline_state = r04.DayState()
        r04.advance_sales(baseline, view, baseline_state, tape, 1)
        self.assertEqual(baseline["market"], [["HIRE"], ["SELL", "WOOL", 1], ["SELL", "MILK", 2]])

        state = r04.DayState()
        r04.advance_sales(candidate, view, state, tape, 1)
        self.assertEqual(candidate["market"], baseline["market"])
        self.assertEqual(state.advanced_sales, baseline_state.advanced_sales)

    def test_interspersed_dead_row_never_shifts_later_authored_row(self):
        parent = action(hires(8) + [
            ["SELL", "WOOL", 1],
            ["SELL", "MILK", 1],
        ])
        view = r04.FarmView(observation(shed={"MILK": 1}))
        self.assertIs(lane.prune_trailing_dead_sells(parent, view, enabled=True), parent)

    def test_buyable_product_is_a_barrier_even_when_empty(self):
        parent = action(hires(9) + [["SELL", "WHEAT", 1]])
        view = r04.FarmView(observation())
        self.assertIs(lane.prune_trailing_dead_sells(parent, view, enabled=True), parent)

    def test_unhashable_malformed_item_fails_closed(self):
        parent = action(hires(9) + [["SELL", ["WOOL"], 1]])
        view = r04.FarmView(observation())
        self.assertIs(lane.prune_trailing_dead_sells(parent, view, enabled=True), parent)

    def test_possible_same_turn_drop_fails_closed(self):
        parent = action(hires(9) + [["SELL", "WOOL", 1]], farmer=["DROP"])
        obs = observation(inventories=[{"WOOL": 1}], farmer=[4, 4])
        view = r04.FarmView(obs)
        self.assertIs(lane.prune_trailing_dead_sells(parent, view, enabled=True), parent)

    def test_possible_same_turn_place_fails_closed(self):
        parent = action(hires(9) + [["SELL", "WOOL", 1]], farmer=["PLACE", "WOOL", 1])
        obs = observation(inventories=[{"WOOL": 1}], farmer=[4, 4])
        view = r04.FarmView(obs)
        self.assertIs(lane.prune_trailing_dead_sells(parent, view, enabled=True), parent)

    def test_off_shed_cargo_does_not_rescue_dead_market_row(self):
        prefix = hires(9)
        parent = action(prefix + [["SELL", "WOOL", 1]], farmer=["PASS"])
        obs = observation(inventories=[{"WOOL": 1}], farmer=[0, 0])
        view = r04.FarmView(obs)
        out = lane.prune_trailing_dead_sells(parent, view, enabled=True)
        self.assertEqual(out["market"], prefix)

    def test_pruned_tail_releases_slot_for_native_advance_sales(self):
        parent_market = hires(9) + [["SELL", "WOOL", 1]]
        parent = action(copy.deepcopy(parent_market))
        obs = observation(shed={"MILK": 2}, prices={"MILK": 160})
        view = r04.FarmView(obs)
        tape = [{"market": []} for _ in range(3)]
        tape[2] = {"market": [["SELL", "MILK", 2]]}

        blocked = copy.deepcopy(parent)
        blocked_state = r04.DayState()
        r04.advance_sales(blocked, view, blocked_state, tape, 1)
        self.assertEqual(len(blocked["market"]), r04.MAX_ORDERS)
        self.assertNotIn(["SELL", "MILK", 2], blocked["market"])

        pruned = lane.prune_trailing_dead_sells(parent, view, enabled=True)
        state = r04.DayState()
        r04.advance_sales(pruned, view, state, tape, 1)
        self.assertEqual(len(pruned["market"]), r04.MAX_ORDERS)
        self.assertEqual(pruned["market"][-1], ["SELL", "MILK", 2])
        self.assertEqual(state.advanced_sales, {"MILK": 2})

    def test_materialized_policy_has_internal_seam_when_present(self):
        import inspect
        source = inspect.getsource(r04.Policy.act)
        if hasattr(r04, "DEAD_SELL_SLOT"):
            self.assertIn("prune_trailing_dead_sells", source)
            self.assertIs(r04.DEAD_SELL_SLOT, False)


if __name__ == "__main__":
    unittest.main()
