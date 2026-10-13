# SPDX-License-Identifier: Apache-2.0
"""Focused fail-closed contract for the additive E3 strict rewrite donor."""

from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest

V3 = Path(__file__).resolve().parents[2]
OVERLAY = V3 / "overlay"
DONOR = Path(__file__).resolve().parent
for path in (OVERLAY, DONOR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import r04_price_forecaster as pf  # noqa: E402
import strict_price_forecaster as strict  # noqa: E402


def observation(step=300, player=0, money=100000, inventory=None, prices=None, shops=None):
    inv = {item: 10000 for item in pf.PRODUCTS}
    inv.update(inventory or {})
    prc = {item: pf.market_price(item, inv[item]) for item in pf.PRODUCTS}
    prc.update(prices or {})
    farms = [{"money": money}, {"money": money}]
    return {
        "step": step,
        "player": player,
        "farms": farms,
        "market": {"inventory": inv, "prices": prc},
        "town": {"unlocked_shops": list(shops or [])},
    }


def action(rows):
    return {"farmer": ["PASS"], "hands": [], "market": copy.deepcopy(rows)}


class StrictRewriteContract(unittest.TestCase):
    def setUp(self):
        pf.reset()

    def tearDown(self):
        pf.reset()

    def test_full_deferral_preserves_cardinality_falsey_barrier_and_tail(self):
        original = action([
            ["SELL", "MILK", 50],
            [],
            ["SELL", "WOOL", 20],
            ["HIRE"],
        ])
        before = copy.deepcopy(original)
        out = strict.apply_price_forecaster(
            observation(inventory={"MILK": 10100}, shops=["PIZZA_SHOP"]),
            original,
        )
        self.assertEqual(len(out["market"]), 4)
        self.assertEqual(out["market"][0], [])
        self.assertEqual(out["market"][1:], before["market"][1:])
        self.assertEqual(original, before)

    def test_non_sell_first_row_is_hard_barrier(self):
        original = action([["HIRE"], ["SELL", "MILK", 50]])
        out = strict.apply_price_forecaster(
            observation(inventory={"MILK": 10100}, shops=["PIZZA_SHOP"]),
            original,
        )
        self.assertIs(out, original)

    def test_partial_shrink_only_changes_leading_sell_row(self):
        original = action([["SELL", "WOOL", 60], ["HIRE"], ["SELL", "MILK", 50]])
        before = copy.deepcopy(original)
        out = strict.apply_price_forecaster(
            observation(inventory={"WOOL": 9900}, shops=["YARN_STORE"]),
            original,
        )
        self.assertEqual(out["market"][0], ["SELL", "WOOL", 2])
        self.assertEqual(out["market"][1:], before["market"][1:])
        self.assertEqual(len(out["market"]), len(before["market"]))
        self.assertEqual(original, before)

    def test_malformed_late_sell_poison_fails_whole_action_closed(self):
        original = action([["SELL", "MILK", 50], ["HIRE"], ["SELL", "WOOL", "20"]])
        out = strict.apply_price_forecaster(
            observation(inventory={"MILK": 10100}, shops=["PIZZA_SHOP"]),
            original,
        )
        self.assertIs(out, original)

    def test_runtime_type_poisons_return_original_action(self):
        cases = []
        cases += [("step", value) for value in (True, "300", 300.0)]
        cases += [("player", value) for value in (True, "0", 0.0)]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                obs = observation(inventory={"MILK": 10100}, shops=["PIZZA_SHOP"])
                obs[field] = value
                original = action([["SELL", "MILK", 50]])
                self.assertIs(strict.apply_price_forecaster(obs, original), original)

        for value in (True, "50", 50.0):
            with self.subTest(qty=value):
                original = action([["SELL", "MILK", value]])
                self.assertIs(
                    strict.apply_price_forecaster(
                        observation(inventory={"MILK": 10100}, shops=["PIZZA_SHOP"]),
                        original,
                    ),
                    original,
                )

        for value in (True, "10100", 10100.0):
            with self.subTest(inventory=value):
                obs = observation(inventory={"MILK": 10100}, shops=["PIZZA_SHOP"])
                obs["market"]["inventory"]["MILK"] = value
                original = action([["SELL", "MILK", 50]])
                self.assertIs(strict.apply_price_forecaster(obs, original), original)

        for value in (True, "1", float("nan"), float("inf")):
            with self.subTest(price=value):
                obs = observation(inventory={"MILK": 10100}, shops=["PIZZA_SHOP"])
                obs["market"]["prices"]["MILK"] = value
                original = action([["SELL", "MILK", 50]])
                self.assertIs(strict.apply_price_forecaster(obs, original), original)

        for value in (True, "100000", float("nan"), float("inf")):
            with self.subTest(money=value):
                original = action([["SELL", "MILK", 50]])
                self.assertIs(
                    strict.apply_price_forecaster(
                        observation(
                            money=value,
                            inventory={"MILK": 10100},
                            shops=["PIZZA_SHOP"],
                        ),
                        original,
                    ),
                    original,
                )

    def test_negative_inventory_fails_closed(self):
        obs = observation(inventory={"MILK": 10100}, shops=["PIZZA_SHOP"])
        obs["market"]["inventory"]["MILK"] = -1
        original = action([["SELL", "MILK", 50]])
        self.assertIs(strict.apply_price_forecaster(obs, original), original)

    def test_falsey_non_list_tape_market_is_not_laundered_to_empty(self):
        for value in (False, 0, ""):
            with self.subTest(tape_market=value):
                tape = [None] * 302
                tape[301] = {"market": value}
                original = action([["SELL", "MILK", 50]])
                self.assertIs(
                    strict.apply_price_forecaster(
                        observation(inventory={"MILK": 10100}, shops=["PIZZA_SHOP"]),
                        original,
                        tape=tape,
                    ),
                    original,
                )

    def test_tuple_market_rows_fail_closed_without_shape_coercion(self):
        cases = [
            [("SELL", "WOOL", 60), ["HIRE"]],
            [["SELL", "MILK", 50], ("HIRE",)],
        ]
        for rows in cases:
            with self.subTest(rows=rows):
                original = action(rows)
                before = copy.deepcopy(original)
                out = strict.apply_price_forecaster(
                    observation(inventory={"MILK": 10100, "WOOL": 9900}, shops=["PIZZA_SHOP", "YARN_STORE"]),
                    original,
                )
                self.assertIs(out, original)
                self.assertEqual(original, before)

    def test_poisoned_rival_state_does_not_get_coerced(self):
        pf._FLOW["rate"]["MILK"] = "1.0"
        original = action([["SELL", "MILK", 50]])
        out = strict.apply_price_forecaster(
            observation(inventory={"MILK": 10100}, shops=["PIZZA_SHOP"]),
            original,
        )
        self.assertIs(out, original)
        self.assertEqual(pf._FLOW["rate"]["MILK"], "1.0")

    def test_helper_failure_restores_flow_and_telemetry(self):
        original_keep = pf.keep_quantity
        flow_before = copy.deepcopy(pf._FLOW)
        report_before = copy.deepcopy(pf.REPORT)

        def explode(*_args, **_kwargs):
            raise RuntimeError("probe")

        pf.keep_quantity = explode
        try:
            original = action([["SELL", "MILK", 50]])
            out = strict.apply_price_forecaster(
                observation(inventory={"MILK": 10100}, shops=["PIZZA_SHOP"]),
                original,
            )
            self.assertIs(out, original)
            self.assertEqual(pf._FLOW, flow_before)
            self.assertEqual(pf.REPORT, report_before)
        finally:
            pf.keep_quantity = original_keep


if __name__ == "__main__":
    unittest.main()
