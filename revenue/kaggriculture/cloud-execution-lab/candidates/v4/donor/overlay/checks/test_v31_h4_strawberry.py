# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import r04_full_router as r04  # noqa: E402
import r04_h4_strawberry as h4  # noqa: E402


def observation(step, shed=None, inventory=None):
    size = 10
    tiles = [["LOCKED"] * size for _ in range(size)]
    for y in range(3, 7):
        for x in range(3, 7):
            tiles[y][x] = {"kind": "SOIL"}
    farm = {"tiles": tiles, "farmer": [4, 4], "hands": [], "money": 1000,
            "unlocked_quadrants": ["NW"], "hires_today": 0}
    prices = {product: 10 for product in r04.PRODUCTS}
    return {"step": step, "day": step // 24, "hour": step % 24, "player": 0,
            "farms": [farm, copy.deepcopy(farm)],
            "private": {"inventories": [dict(inventory or {})],
                        "shed": dict(shed or {"STRAWBERRY": 10})},
            "market": {"prices": prices}, "town": {"unlocked_shops": []}}


def blank_tape():
    return [{"farmer": ["PASS"], "hands": [], "market": []}
            for _ in range(r04.LAST_STEP + 1)]


def action(quantity=2, extra=None, farmer=None):
    market = [["SELL", "STRAWBERRY", quantity]]
    market.extend(copy.deepcopy(extra or []))
    return {"farmer": list(farmer or ["PASS"]), "hands": [], "market": market}


class StrawberryTopupTests(unittest.TestCase):
    def setUp(self):
        self.step = 300
        self.state = r04.DayState()
        self.tape = blank_tape()

    def run_candidate(self, act, shed=None, enabled=True, step=None, inventory=None):
        step = self.step if step is None else step
        view = r04.FarmView(observation(step, shed=shed, inventory=inventory))
        return h4.reconcile_strawberry(act, view, self.state, self.tape, step, enabled)

    def test_flag_off_is_exact_object_identity(self):
        act = action(2)
        self.tape[301]["market"] = [["SELL", "STRAWBERRY", 4]]
        out, added = self.run_candidate(act, enabled=False)
        self.assertIs(out, act)
        self.assertEqual(added, 0)
        self.assertFalse(hasattr(self.state, "sale_window_debts"))

    def test_reuses_current_row_for_future_planned_sales(self):
        act = action(2)
        self.tape[301]["market"] = [["SELL", "STRAWBERRY", 4]]
        self.tape[302]["market"] = [["SELL", "STRAWBERRY", 3]]
        out, added = self.run_candidate(act, shed={"STRAWBERRY": 10})
        self.assertEqual(added, 7)
        self.assertEqual(out["market"], [["SELL", "STRAWBERRY", 9]])
        self.assertEqual(self.state.sale_window_debts,
                         {301: {"STRAWBERRY": 4}, 302: {"STRAWBERRY": 3}})
        self.assertEqual(act["market"], [["SELL", "STRAWBERRY", 2]])

    def test_topup_is_bounded_by_current_projected_stock(self):
        act = action(2)
        self.tape[301]["market"] = [["SELL", "STRAWBERRY", 9]]
        out, added = self.run_candidate(act, shed={"STRAWBERRY": 5})
        self.assertEqual((added, out["market"][0][2]), (3, 5))
        self.assertEqual(self.state.sale_window_debts, {301: {"STRAWBERRY": 3}})

    def test_existing_debt_is_not_reserved_twice(self):
        act = action(1)
        self.state.sale_window_debts = {301: {"STRAWBERRY": 3}}
        self.tape[301]["market"] = [["SELL", "STRAWBERRY", 5]]
        out, added = self.run_candidate(act, shed={"STRAWBERRY": 10})
        self.assertEqual((added, out["market"][0][2]), (2, 3))
        self.assertEqual(self.state.sale_window_debts, {301: {"STRAWBERRY": 5}})

    def test_current_same_item_purchase_fails_closed(self):
        act = action(2, [["BUY_PRODUCT", "STRAWBERRY", 1]])
        self.tape[301]["market"] = [["SELL", "STRAWBERRY", 4]]
        out, added = self.run_candidate(act)
        self.assertIs(out, act)
        self.assertEqual(added, 0)

    def test_current_pickup_fails_closed(self):
        act = action(2, farmer=["PICKUP", "STRAWBERRY", 1])
        self.tape[301]["market"] = [["SELL", "STRAWBERRY", 4]]
        out, added = self.run_candidate(act)
        self.assertIs(out, act)
        self.assertEqual(added, 0)

    def test_future_pickup_stops_later_reservations(self):
        act = action(1)
        self.tape[301]["market"] = [["SELL", "STRAWBERRY", 2]]
        self.tape[302]["farmer"] = ["PICKUP", "STRAWBERRY", 1]
        self.tape[303]["market"] = [["SELL", "STRAWBERRY", 5]]
        out, added = self.run_candidate(act)
        self.assertEqual((added, out["market"][0][2]), (2, 3))
        self.assertEqual(self.state.sale_window_debts, {301: {"STRAWBERRY": 2}})

    def test_does_not_cross_72_step_route_boundary(self):
        step = 358
        act = action(1)
        self.tape[359]["market"] = [["SELL", "STRAWBERRY", 3]]
        self.tape[360]["market"] = [["SELL", "STRAWBERRY", 5]]
        out, added = self.run_candidate(act, step=step)
        self.assertEqual((added, out["market"][0][2]), (3, 4))
        self.assertEqual(self.state.sale_window_debts, {359: {"STRAWBERRY": 3}})

    def test_market_row_cap_does_not_block_same_row_topup(self):
        extra = [["SELL", "WHEAT", 1] for _ in range(r04.MAX_ORDERS - 1)]
        act = action(1, extra)
        self.assertEqual(len(act["market"]), r04.MAX_ORDERS)
        self.tape[301]["market"] = [["SELL", "STRAWBERRY", 4]]
        out, added = self.run_candidate(act)
        self.assertEqual(added, 4)
        self.assertEqual(len(out["market"]), r04.MAX_ORDERS)
        self.assertEqual(out["market"][0], ["SELL", "STRAWBERRY", 5])

    def test_multiple_current_strawberry_rows_fail_closed(self):
        act = action(1, [["SELL", "STRAWBERRY", 2]])
        self.tape[301]["market"] = [["SELL", "STRAWBERRY", 4]]
        out, added = self.run_candidate(act)
        self.assertIs(out, act)
        self.assertEqual(added, 0)

    def test_animal_place_uncertainty_matches_e184_fail_closed(self):
        act = action(1, farmer=["PLACE", "COW"])
        self.tape[301]["market"] = [["SELL", "STRAWBERRY", 4]]
        out, added = self.run_candidate(act, inventory={"COW": 1})
        self.assertIs(out, act)
        self.assertEqual(added, 0)

    def test_no_stock_beyond_current_sale_is_unchanged(self):
        act = action(5)
        self.tape[301]["market"] = [["SELL", "STRAWBERRY", 4]]
        out, added = self.run_candidate(act, shed={"STRAWBERRY": 5})
        self.assertIs(out, act)
        self.assertEqual(added, 0)


if __name__ == "__main__":
    unittest.main()
