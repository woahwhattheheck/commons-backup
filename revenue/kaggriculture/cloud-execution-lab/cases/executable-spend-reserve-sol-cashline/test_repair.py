#!/usr/bin/env python3
from __future__ import annotations

import ast
import copy
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import repair


def repository_root() -> Path:
    for candidate in (HERE, *HERE.parents):
        if (candidate / repair.SCHEDULER_REL).is_file():
            return candidate
    raise RuntimeError("repository root not found")


REPO = repository_root()


class MechanicsStub:
    LAND_PRICES = [1000, 2000, 4000]
    LAND_ORDER = ["NE", "SW", "SE"]
    CROPS = {"WHEAT": {"seed": 10}, "CARROT": {"seed": 20}}
    ANIMALS = {"COW": {"cost": 400}, "SHEEP": {"cost": 500}}

    @staticmethod
    def _hire_cost(n: int, mult: int = 1) -> int:
        a, b = 1, 1
        for _ in range(n):
            a, b = b, a + b
        return mult * a

    @staticmethod
    def market_price(item, inventory, params=None):
        del item, inventory, params
        return 100


def candidate_functions():
    source = repair.build(REPO)[2].decode("utf-8")
    tree = ast.parse(source)
    order_spend = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_order_spend"
    )
    scheduler = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "SellScheduler"
    )
    cash_reserve = next(
        node for node in scheduler.body
        if isinstance(node, ast.FunctionDef) and node.name == "cash_reserve"
    )
    module = ast.Module(body=[copy.deepcopy(order_spend), copy.deepcopy(cash_reserve)], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {"m": MechanicsStub}
    exec(compile(module, "candidate-cash-reserve", "exec"), namespace)
    return namespace["_order_spend"], namespace["cash_reserve"]


class Controller:
    def __init__(self, rows):
        self.cur = "MAIN"
        self.R = {self.cur: rows}


class Subject:
    def __init__(self, rows):
        self.controller = Controller(rows)


def observation(*, step=0, money=0, hires=0, unlocked=None):
    inventory = {
        "WHEAT": 10000,
        "CARROT": 10000,
        "COW": 0,
        "SHEEP": 0,
        "MILK": 10000,
    }
    farm = {
        "money": money,
        "hires_today": hires,
        "unlocked_quadrants": list(unlocked or ["NW"]),
    }
    return {
        "step": step,
        "player": 0,
        "farms": [farm, copy.deepcopy(farm)],
        "market": {"inventory": inventory},
    }


def rows_through(end, mapping=None):
    rows = [{"market": []} for _ in range(end + 1)]
    for step, market in (mapping or {}).items():
        rows[step] = {"market": copy.deepcopy(market)}
    return rows


class ExecutableSpendReserveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.order_spend, cls.cash_reserve = candidate_functions()

    def legacy(self, subject, obs, config, base, end):
        now = int(obs["step"])
        farm = dict(obs["farms"][obs["player"]])
        farm["unlocked_quadrants"] = list(farm["unlocked_quadrants"])
        hires = int(farm["hires_today"])
        cost = 0
        route = subject.controller.R[subject.controller.cur]
        for t in range(now, end + 1):
            if t > now and t % 24 == 0:
                hires = 0
            orders = base["market"] if t == now else (
                route[t].get("market", []) if t < len(route) else []
            )
            for order in orders:
                n, hires = self.order_spend(
                    order,
                    farm,
                    obs["market"]["inventory"],
                    obs["market"].get("params"),
                    hires,
                    config,
                )
                cost += n
                if (
                    order
                    and order[0] == "BUY_LAND"
                    and len(farm["unlocked_quadrants"]) <= len(MechanicsStub.LAND_ORDER)
                ):
                    farm["unlocked_quadrants"].append(
                        MechanicsStub.LAND_ORDER[len(farm["unlocked_quadrants"]) - 1]
                    )
        return cost

    def patched(self, subject, obs, config, base, end):
        return self.cash_reserve(subject, obs, config, base, end)

    def test_exact_sources_and_engine_raw_prefix_are_bound(self):
        record = repair.receipt(REPO)
        self.assertEqual(record["scheduler"]["git_blob"], repair.EXPECTED_SCHEDULER_GIT_BLOB)
        self.assertEqual(record["engine"]["git_blob"], repair.EXPECTED_ENGINE_GIT_BLOB)
        self.assertTrue(record["engine"]["raw_prefix_contract"])
        self.assertFalse(record["canonical_mutated"])

    def test_patch_is_single_exact_reversible_hunk(self):
        scheduler, _, candidate, patch = repair.build(REPO)
        self.assertEqual(candidate.decode().replace(repair.NEW, repair.OLD, 1), scheduler.decode())
        self.assertEqual(patch.count("@@"), 2)
        self.assertIn("active=orders[:max_orders] if isinstance(orders,list) else ()", patch)
        ast.parse(candidate.decode())

    def test_active_prefix_sell_with_suffix_hire_has_no_hire_reserve(self):
        base = {"market": [["SELL", "MILK", 10], ["HIRE"]]}
        subject = Subject(rows_through(0))
        obs = observation(money=0)
        config = {"maxMarketOrdersPerTurn": 1}
        self.assertEqual(self.legacy(subject, obs, config, base, 0), 1)
        self.assertEqual(self.patched(subject, obs, config, base, 0), 0)

    def test_every_spend_class_is_ignored_in_capped_suffix(self):
        cases = (
            (["HIRE"], 1),
            (["BUY_LAND"], 1000),
            (["BUY_SEED", "WHEAT", 3], 30),
            (["BUY_ANIMAL", "COW", 2], 800),
            (["BUY_PRODUCT", "WHEAT", 2], 200),
        )
        config = {"maxMarketOrdersPerTurn": 1}
        obs = observation()
        for suffix, legacy_cost in cases:
            with self.subTest(suffix=suffix):
                base = {"market": [["SELL", "MILK", 1], suffix]}
                subject = Subject(rows_through(0))
                self.assertEqual(self.legacy(subject, obs, config, base, 0), legacy_cost)
                self.assertEqual(self.patched(subject, obs, config, base, 0), 0)

    def test_active_spend_rows_preserve_predecessor_budget(self):
        cases = (
            ["HIRE"],
            ["BUY_LAND"],
            ["BUY_SEED", "WHEAT", 3],
            ["BUY_ANIMAL", "COW", 2],
            ["BUY_PRODUCT", "WHEAT", 2],
        )
        obs = observation()
        config = {"maxMarketOrdersPerTurn": 1}
        for order in cases:
            with self.subTest(order=order):
                base = {"market": [order]}
                subject = Subject(rows_through(0))
                self.assertEqual(
                    self.patched(subject, obs, config, base, 0),
                    self.legacy(subject, obs, config, base, 0),
                )

    def test_nonpositive_limit_matches_engine_minimum_one(self):
        base = {"market": [["HIRE"], ["BUY_LAND"]]}
        subject = Subject(rows_through(0))
        obs = observation()
        for limit in (0, -1, -99):
            with self.subTest(limit=limit):
                self.assertEqual(
                    self.patched(subject, obs, {"maxMarketOrdersPerTurn": limit}, base, 0),
                    1,
                )

    def test_suffix_hire_does_not_advance_later_fibonacci_cursor(self):
        base = {"market": [["HIRE"], ["HIRE"]]}
        rows = rows_through(1, {1: [["HIRE"]]})
        subject = Subject(rows)
        obs = observation()
        config = {"maxMarketOrdersPerTurn": 1}
        self.assertEqual(self.legacy(subject, obs, config, base, 1), 4)
        self.assertEqual(self.patched(subject, obs, config, base, 1), 2)

    def test_suffix_land_does_not_advance_later_land_cursor(self):
        base = {"market": [["BUY_LAND"], ["BUY_LAND"]]}
        rows = rows_through(1, {1: [["BUY_LAND"]]})
        subject = Subject(rows)
        obs = observation()
        config = {"maxMarketOrdersPerTurn": 1}
        self.assertEqual(self.legacy(subject, obs, config, base, 1), 7000)
        self.assertEqual(self.patched(subject, obs, config, base, 1), 3000)

    def test_future_route_suffix_is_not_reserved(self):
        base = {"market": []}
        rows = rows_through(2, {1: [["SELL", "MILK", 1], ["BUY_LAND"]], 2: []})
        subject = Subject(rows)
        obs = observation()
        config = {"maxMarketOrdersPerTurn": 1}
        self.assertEqual(self.legacy(subject, obs, config, base, 2), 1000)
        self.assertEqual(self.patched(subject, obs, config, base, 2), 0)

    def test_full_prefix_is_behavior_identical(self):
        base = {
            "market": [
                ["HIRE"],
                ["BUY_SEED", "WHEAT", 2],
                ["BUY_ANIMAL", "COW", 1],
                ["BUY_LAND"],
            ]
        }
        subject = Subject(rows_through(0))
        obs = observation()
        config = {"maxMarketOrdersPerTurn": 10}
        self.assertEqual(
            self.patched(subject, obs, config, base, 0),
            self.legacy(subject, obs, config, base, 0),
        )

    def test_nonlist_market_matches_engine_empty_queue(self):
        base = {"market": (["HIRE"],)}
        subject = Subject(rows_through(0))
        obs = observation()
        config = {"maxMarketOrdersPerTurn": 10}
        self.assertEqual(self.legacy(subject, obs, config, base, 0), 1)
        self.assertEqual(self.patched(subject, obs, config, base, 0), 0)

    def test_false_suffix_deficit_directly_changes_minimum_now(self):
        base = {"market": [["SELL", "MILK", 10], ["BUY_LAND"]]}
        subject = Subject(rows_through(0))
        obs = observation(money=500)
        config = {"maxMarketOrdersPerTurn": 1}
        legacy_budget = self.legacy(subject, obs, config, base, 0)
        patched_budget = self.patched(subject, obs, config, base, 0)
        current = 10
        legacy_minimum = current if obs["farms"][0]["money"] < legacy_budget else 0
        patched_minimum = current if obs["farms"][0]["money"] < patched_budget else 0
        self.assertEqual((legacy_budget, legacy_minimum), (1000, 10))
        self.assertEqual((patched_budget, patched_minimum), (0, 0))

    def test_malformed_limit_fails_closed(self):
        base = {"market": [["HIRE"]]}
        subject = Subject(rows_through(0))
        with self.assertRaises((TypeError, ValueError)):
            self.patched(
                subject,
                observation(),
                {"maxMarketOrdersPerTurn": "not-an-integer"},
                base,
                0,
            )

    def test_receipt_is_deterministic_and_json_roundtrippable(self):
        first = repair.receipt(REPO)
        second = repair.receipt(REPO)
        self.assertEqual(first, second)
        self.assertEqual(json.loads(json.dumps(first, sort_keys=True)), first)
        self.assertEqual(first["candidate"]["replacement_count"], 1)
        self.assertEqual(first["candidate"]["unified_diff_hunks"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
