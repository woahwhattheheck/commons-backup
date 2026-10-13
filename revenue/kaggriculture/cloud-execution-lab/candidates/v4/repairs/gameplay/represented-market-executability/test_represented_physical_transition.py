#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import importlib.util
import math
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "represented_physical_materializer", HERE / "materialize_represented_physical_transition.py")
carrier = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(carrier)


class Mechanics:
    PRODUCTS = ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG", "MILK", "WOOL", "FERTILIZER")
    ANIMALS = {
        "GOOSE": {"cost": 300},
        "COW": {"cost": 400},
        "SHEEP": {"cost": 500},
    }

    @staticmethod
    def market_price(item, inventory, params=None):
        del inventory, params
        return {"WHEAT": 25, "FERTILIZER": 100}[item]

    @staticmethod
    def _hire_cost(n, mult=1):
        a, b = 1, 1
        for _ in range(n):
            a, b = b, a + b
        return mult * a

    @staticmethod
    def _spawn_hand(farm, board_size):
        del farm, board_size
        return [0, 0]


HELPER_NS = {"math": math, "m": Mechanics}
exec(carrier.CANDIDATE_HELPER, HELPER_NS)
transition = HELPER_NS["_represented_market_physical_transition"]


def world(*, money=0, shed=None, hands=0, hires_today=0):
    farm = {
        "money": money,
        "hires_today": hires_today,
        "hands": [[0, 0] for _ in range(hands)],
        "tiles": [[None]],
    }
    private = {
        "shed": dict(shed or {}),
        "inventories": [{} for _ in range(hands + 1)],
    }
    market = {
        "inventory": {"WHEAT": 10000, "FERTILIZER": 10000},
    }
    return farm, private, market


def run(orders, *, money=0, shed=None, cap=100, hands=0, hires_today=0,
        target="CARROT", state=None, mult=1):
    farm, private, market = world(
        money=money, shed=shed, hands=hands, hires_today=hires_today)
    state = dict(state or {"funding_exact": True, "market_exact": True})
    result = transition(
        farm, private, market, orders,
        {"shedCapacity": cap, "farmHandCostMult": mult}, target, state)
    return result, farm, private, state


class PhysicalTransitionTests(unittest.TestCase):
    def test_zero_cash_wheat_does_not_phantom_fill(self):
        result, farm, private, _ = run([["BUY_PRODUCT", "WHEAT", 1]], money=0)
        self.assertTrue(result["resolved"])
        self.assertEqual(private["shed"].get("WHEAT", 0), 0)
        self.assertEqual(farm["money"], 0)

    def test_illegal_buy_product_carrot_is_inert(self):
        result, farm, private, _ = run([["BUY_PRODUCT", "CARROT", 1]], money=1000)
        self.assertTrue(result["resolved"])
        self.assertNotIn("CARROT", private["shed"])
        self.assertEqual(farm["money"], 1000)

    def test_zero_cash_goose_does_not_phantom_fill(self):
        result, farm, private, _ = run([["BUY_ANIMAL", "GOOSE", 1]], money=0)
        self.assertTrue(result["resolved"])
        self.assertEqual(private["shed"].get("GOOSE", 0), 0)
        self.assertEqual(farm["money"], 0)

    def test_full_shed_rejects_animal(self):
        result, farm, private, _ = run(
            [["BUY_ANIMAL", "GOOSE", 1]], money=1000, shed={"WHEAT": 2}, cap=2)
        self.assertTrue(result["resolved"])
        self.assertNotIn("GOOSE", private["shed"])
        self.assertEqual(farm["money"], 1000)

    def test_buy_product_partial_fill_stops_on_capacity(self):
        result, farm, private, _ = run(
            [["BUY_PRODUCT", "WHEAT", 2]], money=1000, shed={"WHEAT": 1}, cap=2)
        self.assertTrue(result["resolved"])
        self.assertEqual(private["shed"]["WHEAT"], 2)
        self.assertEqual(farm["money"], 975)

    def test_fixed_price_animal_sequential_cash(self):
        result, farm, private, _ = run(
            [["BUY_ANIMAL", "GOOSE", 3]], money=700)
        self.assertTrue(result["resolved"])
        self.assertEqual(private["shed"]["GOOSE"], 2)
        self.assertEqual(farm["money"], 100)

    def test_funded_hire_mutates_actor_and_inventory_together(self):
        result, farm, private, _ = run([["HIRE"]], money=1)
        self.assertTrue(result["resolved"])
        self.assertEqual(farm["money"], 0)
        self.assertEqual(farm["hires_today"], 1)
        self.assertEqual(len(farm["hands"]), 1)
        self.assertEqual(len(private["inventories"]), 2)

    def test_fibonacci_1_1_2_then_stop(self):
        result, farm, private, _ = run(
            [["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]], money=4)
        self.assertTrue(result["resolved"])
        self.assertEqual(farm["money"], 0)
        self.assertEqual(farm["hires_today"], 3)
        self.assertEqual(len(farm["hands"]), 3)
        self.assertEqual(len(private["inventories"]), 4)

    def test_uncertain_sell_credit_before_hire_fails_closed(self):
        result, farm, private, _ = run(
            [["SELL", "WHEAT", 1], ["HIRE"]], money=0, shed={"WHEAT": 1})
        self.assertFalse(result["resolved"])
        self.assertIn("hire_funding_unknown", result["reason"])
        self.assertEqual(farm["hands"], [])
        self.assertEqual(private["shed"]["WHEAT"], 0)

    def test_preexisting_cash_survives_ignored_sell_credit_for_hire(self):
        result, farm, private, state = run(
            [["SELL", "WHEAT", 1], ["HIRE"]], money=1, shed={"WHEAT": 1})
        self.assertTrue(result["resolved"])
        self.assertFalse(state["funding_exact"])
        self.assertEqual(farm["money"], 0)
        self.assertEqual(farm["hires_today"], 1)
        self.assertEqual(len(farm["hands"]), 1)
        self.assertEqual(len(private["inventories"]), 2)

    def test_preexisting_cash_survives_ignored_sell_credit_for_animal(self):
        result, farm, private, state = run(
            [["SELL", "WHEAT", 1], ["BUY_ANIMAL", "GOOSE", 1]],
            money=300, shed={"WHEAT": 1})
        self.assertTrue(result["resolved"])
        self.assertFalse(state["funding_exact"])
        self.assertEqual(farm["money"], 0)
        self.assertEqual(private["shed"].get("GOOSE", 0), 1)

    def test_uncertain_sell_credit_cannot_prove_animal_rejection(self):
        result, farm, private, _ = run(
            [["SELL", "WHEAT", 1], ["BUY_ANIMAL", "GOOSE", 1]],
            money=0, shed={"WHEAT": 1})
        self.assertFalse(result["resolved"])
        self.assertIn("buy_animal_funding_unknown", result["reason"])
        self.assertEqual(farm["money"], 0)
        self.assertEqual(private["shed"].get("GOOSE", 0), 0)

    def test_uncertain_sell_credit_cannot_prove_product_rejection(self):
        result, farm, private, _ = run(
            [["SELL", "CARROT", 1], ["BUY_PRODUCT", "WHEAT", 1]],
            money=0, shed={"CARROT": 1})
        self.assertFalse(result["resolved"])
        self.assertIn("buy_product_quote_unknown", result["reason"])
        self.assertEqual(farm["money"], 0)
        self.assertEqual(private["shed"].get("WHEAT", 0), 0)

    def test_prior_unmodeled_purchase_does_not_authorize_hire(self):
        result, farm, _, _ = run(
            [["BUY_SEED", "WHEAT", 1], ["HIRE"]], money=10)
        self.assertFalse(result["resolved"])
        self.assertIn("hire_funding_unknown", result["reason"])
        self.assertEqual(farm["money"], 0)
        self.assertEqual(farm["hands"], [])

    def test_non_first_buy_product_quote_fails_closed(self):
        # Empty slot 0 can pair with a rival market order, so slot 1's public
        # inventory quote is not derivable from the one-player prestate.
        result, _, private, _ = run(
            [[], ["BUY_PRODUCT", "WHEAT", 1]], money=1000)
        self.assertFalse(result["resolved"])
        self.assertIn("buy_product_quote_unknown", result["reason"])
        self.assertEqual(private["shed"].get("WHEAT", 0), 0)

    def test_type_coerced_quantity_fails_closed(self):
        result, _, private, _ = run(
            [["BUY_PRODUCT", "WHEAT", "1"]], money=1000)
        self.assertFalse(result["resolved"])
        self.assertIn("coerced_buy_product_qty", result["reason"])
        self.assertEqual(private["shed"].get("WHEAT", 0), 0)

    def test_bad_config_type_fails_closed(self):
        farm, private, market = world(money=1000)
        result = transition(
            farm, private, market, [["BUY_ANIMAL", "GOOSE", 1]],
            {"shedCapacity": "100", "farmHandCostMult": 1}, "CARROT",
            {"funding_exact": True, "market_exact": True})
        self.assertFalse(result["resolved"])
        self.assertEqual(result["reason"], "bad_shed_capacity")

    def test_unresolved_transition_is_wired_to_feasibility_rejection(self):
        self.assertIn("if not physical.get('resolved',False):\n                return lambda _plan: False",
                      carrier.PHYSICAL_BLOCK_NEW)

    def test_materializer_keeps_prefix_as_upstream_authority(self):
        self.assertIn("orders=_engine_market_prefix(market_action,config)",
                      carrier.PHYSICAL_BLOCK_NEW)
        self.assertNotIn("orders=base['market']", carrier.PHYSICAL_BLOCK_NEW)


if __name__ == "__main__":
    unittest.main(verbosity=2)