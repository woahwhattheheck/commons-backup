#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import importlib.util
import math
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "represented_integral_money_materializer",
    HERE / "materialize_integral_money_custody.py",
)
carrier = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(carrier)

UPSTREAM_PATH = HERE / "materialize_represented_physical_transition.py"
UPSTREAM_BYTES = UPSTREAM_PATH.read_bytes()
HELPER = carrier.patched_candidate_helper(UPSTREAM_BYTES)


class Mechanics:
    PRODUCTS = (
        "WHEAT",
        "CARROT",
        "TOMATO",
        "STRAWBERRY",
        "MELON",
        "EGG",
        "MILK",
        "WOOL",
        "FERTILIZER",
    )
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
exec(HELPER, HELPER_NS)
transition = HELPER_NS["_represented_market_physical_transition"]


def world(money):
    farm = {
        "money": money,
        "hires_today": 0,
        "hands": [],
        "tiles": [[None]],
    }
    private = {"shed": {}, "inventories": [{}]}
    market = {"inventory": {"WHEAT": 10000, "FERTILIZER": 10000}}
    return farm, private, market


def run(money, orders):
    farm, private, market = world(money)
    result = transition(
        farm,
        private,
        market,
        orders,
        {"shedCapacity": 100, "farmHandCostMult": 1},
        "CARROT",
        {"funding_exact": True, "market_exact": True},
    )
    return result, farm, private


class IntegralMoneyCustodyTests(unittest.TestCase):
    def test_upstream_blob_and_patch_cardinality_are_exact(self):
        self.assertEqual(
            carrier.git_blob_sha(UPSTREAM_BYTES),
            carrier.UPSTREAM_MATERIALIZER_GIT_BLOB,
        )
        self.assertEqual(HELPER.count(carrier._MONEY_GUARD_NEW), 2)
        self.assertNotIn(carrier._MONEY_GUARD_OLD, HELPER)

    def test_official_engine_constructs_money_from_integral_starting_money(self):
        lab = HERE.parents[4]
        engine = lab / "reference/engine/kaggriculture.py"
        engine_bytes = engine.read_bytes()
        upstream = carrier._upstream_namespace(UPSTREAM_BYTES)
        self.assertEqual(carrier.git_blob_sha(engine_bytes), upstream["ENGINE_GIT_BLOB"])
        source = engine_bytes.decode("utf-8")
        self.assertIn(
            'starting_money = int(get(configuration, "startingMoney", 3000))',
            source,
        )
        self.assertIn('"money": float(starting_money)', source)
        self.assertIn("max(PRICE_FLOOR, int(round(price)))", source)

    def test_fractional_money_cannot_spawn_hire(self):
        result, farm, private = run(1.5, [["HIRE"]])
        self.assertFalse(result["resolved"])
        self.assertEqual(result["reason"], "bad_money")
        self.assertEqual(farm["money"], 1.5)
        self.assertEqual(farm["hands"], [])
        self.assertEqual(private["inventories"], [{}])

    def test_fractional_money_cannot_buy_animal(self):
        result, farm, private = run(300.5, [["BUY_ANIMAL", "GOOSE", 1]])
        self.assertFalse(result["resolved"])
        self.assertEqual(result["reason"], "bad_money")
        self.assertEqual(farm["money"], 300.5)
        self.assertNotIn("GOOSE", private["shed"])

    def test_fractional_money_cannot_buy_product(self):
        result, farm, private = run(25.5, [["BUY_PRODUCT", "WHEAT", 1]])
        self.assertFalse(result["resolved"])
        self.assertEqual(result["reason"], "bad_money")
        self.assertEqual(farm["money"], 25.5)
        self.assertNotIn("WHEAT", private["shed"])

    def test_integral_float_hire_remains_live(self):
        result, farm, private = run(1.0, [["HIRE"]])
        self.assertTrue(result["resolved"])
        self.assertEqual(farm["money"], 0.0)
        self.assertEqual(len(farm["hands"]), 1)
        self.assertEqual(len(private["inventories"]), 2)

    def test_integral_float_animal_remains_live(self):
        result, farm, private = run(300.0, [["BUY_ANIMAL", "GOOSE", 1]])
        self.assertTrue(result["resolved"])
        self.assertEqual(farm["money"], 0.0)
        self.assertEqual(private["shed"]["GOOSE"], 1)

    def test_integral_float_product_remains_live(self):
        result, farm, private = run(25.0, [["BUY_PRODUCT", "WHEAT", 1]])
        self.assertTrue(result["resolved"])
        self.assertEqual(farm["money"], 0.0)
        self.assertEqual(private["shed"]["WHEAT"], 1)

    def test_exact_repository_composition_contains_only_strict_money_guards(self):
        lab = HERE.parents[4]
        source = (lab / "scheduler.py").read_bytes()
        engine = (lab / "reference/engine/kaggriculture.py").read_bytes()
        prefix = (
            lab
            / "candidates/v4/repairs/gameplay/scheduler-prefix/materialize_scheduler_prefix.py"
        ).read_bytes()
        candidate = carrier.materialize(source, engine, prefix, UPSTREAM_BYTES)
        text = candidate.decode("utf-8")
        self.assertEqual(text.count(carrier._MONEY_GUARD_NEW), 2)
        self.assertNotIn(carrier._MONEY_GUARD_OLD, text)
        compile(text, "<represented-integral-money-candidate>", "exec")


if __name__ == "__main__":
    unittest.main(verbosity=2)
