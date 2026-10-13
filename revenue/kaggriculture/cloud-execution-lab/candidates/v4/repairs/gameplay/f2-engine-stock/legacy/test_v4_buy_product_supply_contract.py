# SPDX-License-Identifier: Apache-2.0
"""Interpreter-level companion to F2's stock-independent admission regression.

Run inside the materialized candidate package:
    python -B -m unittest checks.test_v4_buy_product_supply_contract

The complete engine bytes must match the pinned source before its unchanged
market dependency closure is compiled. This avoids importing unrelated Kaggle
initialization dependencies; it does not replace the market implementation or
pricing formula. These tests cover the market phase, not full-episode economics.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import itertools
import math
from pathlib import Path
from types import SimpleNamespace
import unittest

ENGINE_GIT = "3c202c7ee921da239356789e266b694635103fc4"
ENGINE_PATH = Path(__file__).resolve().parent / "reference" / "engine" / "kaggriculture.py"
CONSTANTS = {"CROPS", "ANIMALS", "PRODUCTS", "MARKET_I0", "PRICE_FLOOR",
             "MARKET_PARAMS", "HINGE_GAIN", "FARM_HAND_COST_MULT"}
FUNCTIONS = {"_shape", "market_price", "get", "_process_market", "_parse_order",
             "_commit_unit", "_refresh_prices"}
CONFIG = {"boardSize": 10, "maxMarketOrdersPerTurn": 10,
          "farmHandCostMult": 1, "shedCapacity": 100}


def _load_market(engine_path):
    source = engine_path.read_bytes()
    digest = hashlib.sha1(b"blob " + str(len(source)).encode() + b"\0" + source).hexdigest()
    if digest != ENGINE_GIT:
        raise AssertionError("engine changed: revalidate the market contract before updating its pin")
    tree = ast.parse(source, filename=str(engine_path))
    body = []
    found = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in FUNCTIONS:
            body.append(node)
            found.add(node.name)
        elif isinstance(node, ast.Assign) and all(isinstance(t, ast.Name) for t in node.targets):
            names = {target.id for target in node.targets}
            if names <= CONSTANTS:
                body.append(node)
                found.update(names)
    if found != CONSTANTS | FUNCTIONS:
        raise AssertionError("incomplete pinned market dependency closure")
    namespace = {"math": math}
    exec(compile(ast.Module(body=body, type_ignores=[]), str(engine_path), "exec"), namespace)
    return namespace


def _run_orders(engine, product, inventory, orders, money=(100000.0, 100000.0), stock=(0, 0)):
    farms = [{"money": amount} for amount in money]
    privates = [{"shed": {product: count}, "seeds": {}} for count in stock]
    market = {"inventory": {p: 10000 for p in engine["PRODUCTS"]}, "params": None, "prices": {}}
    market["inventory"][product] = inventory
    state = [SimpleNamespace(
        observation=SimpleNamespace(market=market, farms=farms, private=privates[seat]),
        action={"market": copy.deepcopy(orders[seat])}) for seat in (0, 1)]
    engine["_process_market"](state, SimpleNamespace(configuration=dict(CONFIG)))
    return farms, privates, market


class BuyProductSupplyContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = _load_market(ENGINE_PATH)

    def test_simultaneous_buys_fill_even_at_negative_zero_or_short_public_stock(self):
        cases = 0
        negative_endings = 0
        for product, inventory, q0, q1 in itertools.product(
                ("WHEAT", "FERTILIZER"), (-10, 0, 1, 10000), (1, 2), (1, 2)):
            with self.subTest(product=product, inventory=inventory, quantities=(q0, q1)):
                orders = [[["BUY_PRODUCT", product, q0]], [["BUY_PRODUCT", product, q1]]]
                farms, privates, market = _run_orders(self.engine, product, inventory, orders)
                self.assertEqual([p["shed"][product] for p in privates], [q0, q1])
                self.assertEqual(market["inventory"][product], inventory - q0 - q1)
                expected_cash = [100000.0, 100000.0]
                expected_inventory = inventory
                for unit in range(max(q0, q1)):
                    # Both actors quote from the same pre-commit stock each
                    # unit round, using the unmodified native pricing function.
                    quote = self.engine["market_price"](product, expected_inventory - 1, None)
                    for seat, quantity in enumerate((q0, q1)):
                        if unit < quantity:
                            expected_cash[seat] -= quote
                            expected_inventory -= 1
                self.assertEqual([f["money"] for f in farms], expected_cash)
                negative_endings += market["inventory"][product] < 0
                cases += 1
        self.assertEqual(cases, 32)
        self.assertEqual(negative_endings, 24)

    def test_cash_capacity_and_raw_prefix_constraints_still_apply(self):
        cases = 0
        for product, seat in itertools.product(("WHEAT", "FERTILIZER"), (0, 1)):
            with self.subTest(product=product, seat=seat):
                quote = self.engine["market_price"](product, -1, None)
                orders = [[], []]
                orders[seat] = [["BUY_PRODUCT", product, 2]]
                cash = [100000.0, 100000.0]
                cash[seat] = quote - 1
                farms, privates, market = _run_orders(
                    self.engine, product, 0, orders, money=tuple(cash))
                self.assertEqual(privates[seat]["shed"][product], 0)
                self.assertEqual(market["inventory"][product], 0)
                self.assertEqual(farms[seat]["money"], cash[seat])
                cases += 1
                stock = [0, 0]
                stock[seat] = 99
                farms, privates, market = _run_orders(
                    self.engine, product, 0, orders, stock=tuple(stock))
                self.assertEqual(privates[seat]["shed"][product], 100)
                self.assertEqual(market["inventory"][product], -1)
                cases += 1
                orders[seat] = [[] for _ in range(10)] + [["BUY_PRODUCT", product, 2]]
                farms, privates, market = _run_orders(self.engine, product, 0, orders)
                self.assertEqual(privates[seat]["shed"][product], 0)
                self.assertEqual(market["inventory"][product], 0)
                self.assertEqual(farms[seat]["money"], 100000.0)
                cases += 1
        self.assertEqual(cases, 12)

    def test_source_pin_is_checked_before_compiling(self):
        class WrongSource:
            def read_bytes(self):
                return b"raise RuntimeError('must never execute mismatched engine source')\n"
        with self.assertRaisesRegex(AssertionError, "engine changed"):
            _load_market(WrongSource())


if __name__ == "__main__":
    unittest.main()
