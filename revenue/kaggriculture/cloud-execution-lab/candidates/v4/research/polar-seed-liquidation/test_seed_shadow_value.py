# SPDX-License-Identifier: Apache-2.0
"""Extracted-official-source differential tests; no episode/economics verdict.

Default oracle is the pinned interpreter's crop price functions and SELL branch.
Set TITAN_ENGINE_FILE to the complete official file to bind and extract those
functions from exact Git blob 3c202c7e instead. No kaggle package import is needed.
The default test run must not be described as complete-file/package execution.
"""
import ast
import dataclasses
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import unittest

import seed_shadow_value as s

# Literal crop entries and function statements from the pinned official engine.
MARKET_I0 = 10000
PRICE_FLOOR = 1
HINGE_GAIN = 8.0
MARKET_PARAMS = {
    "WHEAT": {"base":25, "I0":MARKET_I0, "T":400, "below_func":"sqrt", "below_target":0.80, "above_func":"log", "above_target":0.20},
    "CARROT": {"base":35, "I0":MARKET_I0, "T":450, "below_func":"hinge", "below_target":1.00, "above_func":"sqrt", "above_target":0.70},
    "TOMATO": {"base":60, "I0":MARKET_I0, "T":200, "below_func":"hinge", "below_target":0.40, "above_func":"sqrt", "above_target":0.60},
    "STRAWBERRY": {"base":120, "I0":MARKET_I0, "T":100, "below_func":"sqrt", "below_target":0.70, "above_func":"linear", "above_target":1.60},
    "MELON": {"base":250, "I0":MARKET_I0, "T":300, "below_func":"log", "below_target":0.20, "above_func":"sq", "above_target":3.60},
}


def _shape(func, x, T=None):
    x = max(0.0, x)
    if func == "linear": return x
    if func == "sq":     return x * x
    if func == "sqrt":   return math.sqrt(x)
    if func == "log":    return math.log(1.0 + x)
    if func == "log10":  return math.log10(1.0 + x)
    if func == "hinge":
        if not T or T <= 0:
            return x
        u = x / T
        return u + HINGE_GAIN * max(0.0, u - 1.0) ** 2
    return x


def market_price(item, inventory, params=None):
    p = (params or MARKET_PARAMS)[item]
    base = p["base"]
    I0 = p["I0"]
    T = p["T"]
    if inventory < I0:
        f = p["below_func"]
        amp = p["below_target"] * base / _shape(f, T, T)
        price = base + amp * _shape(f, I0 - inventory, T)
    else:
        f = p["above_func"]
        amp = p["above_target"] * base / _shape(f, T, T)
        price = base - amp * _shape(f, inventory - I0, T)
    return max(PRICE_FLOOR, int(round(price)))


def _commit_unit(op, item, price, farm, private, market, shed_capacity=100):
    # Only the official SELL branch is needed for this isolated scenario oracle.
    if op == "SELL":
        if private["shed"].get(item, 0) <= 0:
            return False
        private["shed"][item] -= 1
        farm["money"] += price
        if price > 1:
            market["inventory"][item] += 1
        return True
    raise ValueError("oracle supports SELL only")


def load_exact_engine(path):
    raw = Path(path).read_bytes()
    actual = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    if actual != s.ENGINE_BLOB:
        raise ValueError("official engine Git blob mismatch")
    names = {"MARKET_I0", "PRICE_FLOOR", "MARKET_PARAMS", "HINGE_GAIN",
             "_shape", "market_price", "_commit_unit"}
    nodes = []
    found = set()
    for node in ast.parse(raw).body:
        name = (node.name if isinstance(node, ast.FunctionDef) else
                node.targets[0].id if isinstance(node, ast.Assign)
                and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                else None)
        if name in names:
            nodes.append(node)
            found.add(name)
    if found != names or len(nodes) != len(names):
        raise ValueError("official oracle definition set mismatch")
    namespace = {"math": math}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
    return namespace["market_price"], namespace["_commit_unit"]


if os.environ.get("TITAN_ENGINE_FILE"):
    market_price, _commit_unit = load_exact_engine(os.environ["TITAN_ENGINE_FILE"])

CROPS = tuple(s._PARAMS)
STOCKS = (-1000, 9000, 9599, 9600, 9799, 9800, 9999, 10000,
          10048, 10049, 10061, 10062, 10151, 10152, 10347, 10653, 20000)


def official_sale(crop, stock, units):
    farm = {"money": 0.0}
    private = {"shed": {crop: units}}
    market = {"inventory": {crop: stock}}
    floors = 0
    for _ in range(units):
        price = market_price(crop, market["inventory"][crop])
        if not _commit_unit("SELL", crop, price, farm, private, market):
            raise RuntimeError("available-unit official SELL unexpectedly failed")
        floors += price == 1
    return int(farm["money"]), market["inventory"][crop], floors


class SeedShadowTests(unittest.TestCase):
    def test_quote_official_dense_grid(self):
        for crop in CROPS:
            for stock in (*range(9400, 11201), *STOCKS):
                self.assertEqual(s.quote(crop, stock), market_price(crop, stock))

    def test_liquidation_official_unit_commits(self):
        for crop in CROPS:
            for stock in STOCKS:
                for units in (0, 1, 4, 6, 50, 100):
                    with self.subTest(crop=crop, stock=stock, units=units):
                        r = s.liquidate(crop, stock, units)
                        self.assertEqual((r.cash, r.inventory_after, r.floor_units),
                                         official_sale(crop, stock, units))

    def test_split_combine_exact(self):
        for crop in CROPS:
            for stock in STOCKS:
                for committed, extra in ((0, 0), (0, 4), (7, 6), (50, 4), (97, 3)):
                    v = s.seed_value(crop, stock, extra, committed_units=committed)
                    base = official_sale(crop, stock, committed)
                    total = official_sale(crop, stock, committed + extra)
                    self.assertEqual(v.baseline_cash, base[0])
                    self.assertEqual(v.combined_cash, total[0])
                    self.assertEqual(v.marginal_cash, total[0] - base[0])
                    self.assertEqual(v.combined_inventory_after, total[1])

    def test_quote_times_yield_sign_flip(self):
        v = s.seed_value("STRAWBERRY", 10049, 4)
        self.assertEqual(v.current_quote, 26)
        self.assertEqual(v.quote_times_extra_yield - v.seed_cash_cost, 4)
        self.assertEqual(v.marginal_cash, 92)
        self.assertEqual(v.net_incremental_cash, -8)

    def test_committed_output_reprices_next_seed(self):
        empty = s.seed_value("STRAWBERRY", 10000, 4)
        full = s.seed_value("STRAWBERRY", 10000, 4, committed_units=50)
        self.assertGreater(empty.net_incremental_cash, 0)
        self.assertEqual(full.quote_times_extra_yield, 480)
        self.assertEqual(full.marginal_cash, 84)
        self.assertEqual(full.net_incremental_cash, -16)

    def test_owned_seed_is_sunk_not_negative_purchase(self):
        new = s.seed_value("STRAWBERRY", 10049, 4)
        owned = s.seed_value("STRAWBERRY", 10049, 4, seed_already_owned=True)
        self.assertEqual(owned.seed_cash_cost, 0)
        self.assertEqual(owned.marginal_cash, new.marginal_cash)
        self.assertEqual(owned.net_incremental_cash, 92)

    def test_avoidable_extra_cash_only(self):
        v = s.seed_value("STRAWBERRY", 10049, 4, seed_already_owned=True,
                         extra_cash_cost=100)
        self.assertEqual(v.net_incremental_cash, -8)

    def test_zero_yield_still_charges_new_seed(self):
        self.assertEqual(s.seed_value("MELON", 10000, 0).net_incremental_cash, -80)
        self.assertEqual(s.seed_value("MELON", 10000, 0,
                                     seed_already_owned=True).net_incremental_cash, 0)

    def test_floor_pays_without_stock_increment(self):
        v = s.liquidate("STRAWBERRY", 20000, 99999)
        self.assertEqual((v.cash, v.inventory_after, v.floor_units), (99999, 20000, 99999))
        v = s.liquidate("STRAWBERRY", 10061, 5)
        self.assertEqual((v.cash, v.inventory_after, v.floor_units), (7, 10062, 4))

    def test_bounded_breakpoints(self):
        cases = (("CARROT", 4, 10653), ("TOMATO", 4, 10347),
                 ("STRAWBERRY", 4, 10048), ("MELON", 6, 10152))
        for crop, units, expected in cases:
            found = s.first_nonpositive_inventory(crop, units, low=10000, high=11200)
            brute = next(i for i in range(10000, 11201)
                         if s.seed_value(crop, i, units).net_incremental_cash <= 0)
            self.assertEqual(found, brute)
            self.assertEqual(found, expected)
            self.assertGreater(s.seed_value(crop, found - 1, units).net_incremental_cash, 0)

    def test_no_threshold_is_not_universal_profit(self):
        self.assertIsNone(s.first_nonpositive_inventory("WHEAT", 6, low=9000, high=20000))
        self.assertIsNone(s.first_nonpositive_inventory("STRAWBERRY", 4,
                          low=10000, high=20000, seed_already_owned=True))

    def test_threshold_interval_edges(self):
        self.assertEqual(s.first_nonpositive_inventory("MELON", 0, low=9000, high=9000), 9000)
        self.assertIsNone(s.first_nonpositive_inventory("MELON", 6, low=9000, high=9000))
        with self.assertRaises(ValueError):
            s.first_nonpositive_inventory("MELON", 6, low=2, high=1)

    def test_reject_nonplain_scalars(self):
        class IntChild(int):
            pass
        for bad in (None, True, False, 1.0, "1", [], {}, IntChild(1),
                    math.nan, math.inf, 10**10000):
            for name in ("inventory", "extra_yield_units", "committed_units", "extra_cash_cost"):
                kw = dict(crop="WHEAT", inventory=10000, extra_yield_units=4)
                kw[name] = bad
                with self.assertRaises(ValueError, msg=name):
                    s.seed_value(**kw)

    def test_reject_invalid_crop_and_owned_flag(self):
        class StrChild(str):
            pass
        for bad in (None, [], 1, "MILK", "wheat", StrChild("WHEAT")):
            with self.assertRaises(ValueError):
                s.seed_value(bad, 10000, 4)
        for bad in (None, 0, 1, "false", [], {}):
            with self.assertRaises(ValueError):
                s.seed_value("WHEAT", 10000, 4, seed_already_owned=bad)

    def test_negative_quantity_and_order_budget(self):
        for kw in ({"extra_yield_units": -1}, {"committed_units": -1},
                   {"extra_cash_cost": -1}, {"extra_yield_units": 100000},
                   {"extra_yield_units": 50000, "committed_units": 50000}):
            args = dict(crop="WHEAT", inventory=10000, extra_yield_units=4)
            args.update(kw)
            with self.assertRaises(ValueError):
                s.seed_value(**args)

    def test_stock_domain_composes_at_boundary(self):
        self.assertEqual(s.liquidate("WHEAT", s._MAX_STOCK, 0).inventory_after, s._MAX_STOCK)
        s.seed_value("WHEAT", s._MAX_STOCK - 100, 50, committed_units=50)
        with self.assertRaises(ValueError):
            s.seed_value("WHEAT", s._MAX_STOCK - 99, 50, committed_units=50)

    def test_frozen_result(self):
        with self.assertRaises(dataclasses.FrozenInstanceError):
            s.seed_value("MELON", 10000, 6).marginal_cash = 1

    def test_full_engine_pin_rejects_wrong_file(self):
        with self.assertRaises(ValueError):
            load_exact_engine(__file__)

    def test_cli_normal_optimized_identical(self):
        args = [str(Path(s.__file__)), "--crop", "STRAWBERRY", "--inventory", "10049",
                "--yield-units", "4", "--inventory-deltas", "-50", "0", "50"]
        normal = subprocess.check_output([sys.executable, *args])
        optimized = subprocess.check_output([sys.executable, "-O", *args])
        self.assertEqual(normal, optimized)
        report = json.loads(normal)
        self.assertIs(report["policy_authorized"], False)
        self.assertEqual(report["engine_blob"], s.ENGINE_BLOB)
        self.assertEqual(report["scenarios"][1]["net_incremental_cash"], -8)

    def test_cli_invalid_input_nonzero(self):
        p = subprocess.run([sys.executable, str(Path(s.__file__)), "--crop", "WHEAT",
                            "--inventory", "10000", "--yield-units", "-1"],
                           capture_output=True)
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual(p.stdout, b"")


if __name__ == "__main__":
    unittest.main()
