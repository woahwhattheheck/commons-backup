#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Composition tests on exact scheduler methods, not full-engine episodes.

Reuses the unchanged, Git-verified RIVET fixture. Future unit execution is
PASS-only. Cash quotes/costs and hand spawning are explicit test doubles.
No production imports, arbitrary unit simulation, or strength claims.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch as mock_patch

import repair_scheduler_prefix as repair
import repair_receipt_prefix as donor
import test_receipt_prefix as original

SOURCE = original.SOURCE
PASS = {"farmer": ["PASS"], "hands": [], "market": []}


class CashDependencies:
    LAND_ORDER = ("NE", "SW", "SE")
    LAND_PRICES = (200, 400, 800)
    CROPS = {"CARROT": {"seed": 2}}
    ANIMALS = {"GOOSE": {"cost": 40}}

    @staticmethod
    def _hire_cost(hires, multiplier):
        return (50 + 5 * hires) * multiplier

    @staticmethod
    def market_price(item, inventory, params):
        return 7


def extract_cash(source):
    tree = ast.parse(source)
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                 and n.name in ("_receipt_market_prefix", "_order_spend")]
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "SellScheduler")
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "cash_reserve")
    namespace = {"m": CashDependencies(), "parent": SimpleNamespace(PASS=PASS)}
    exec(compile(ast.Module(body=functions + [method], type_ignores=[]), "<exact-cash-functions>", "exec"), namespace)
    return namespace["cash_reserve"]


def cash(source, *, market=None, future_market=None, now=22, end=22, limit=1, hires=0, short=False):
    farm = {"unlocked_quadrants": ["NW"], "hires_today": hires}
    obs = {"step": now, "player": 0, "farms": [farm, {}],
           "market": {"inventory": {"WHEAT": 0}, "params": {}}}
    base = dict(PASS, market=[] if market is None else market)
    route = [copy.deepcopy(PASS) for _ in range(0 if short else end + 1)]
    if future_market is not None:
        route[end]["market"] = future_market
    owner = SimpleNamespace(controller=SimpleNamespace(R=[route], cur=0))
    config = {"maxMarketOrdersPerTurn": limit}
    state = obs, base, route, config
    before = copy.deepcopy(state)
    result = extract_cash(source)(owner, obs, config, base, end)
    if state != before:
        raise AssertionError("cash_reserve mutated its inputs")
    return result


class ThreeConsumerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SOURCE.read_bytes()
        cls.fixed_bytes, cls.report = repair.repair(cls.source)
        cls.old = cls.source.decode()
        cls.fixed = cls.fixed_bytes.decode()
        cls.receipt_only = donor.repair(cls.source)[0].decode()
        # Semantic reconstruction of 5e8f's two consumers, sharing donor naming.
        cls.cash_and_loop_only = cls.old.replace(donor.HELPER_ANCHOR, donor.HELPER, 1)
        cls.cash_and_loop_only = cls.cash_and_loop_only.replace(donor.FUTURE_OLD, donor.FUTURE_NEW, 1)
        cls.cash_and_loop_only = cls.cash_and_loop_only.replace(repair.CASH_OLD, repair.CASH_NEW, 1)

    def test_exact_inputs_and_intermediate(self):
        self.assertEqual(repair.git_blob(self.source), "da1b6fb571e79ba7dab54c8d816e45afb934e4d2")
        self.assertEqual(repair.git_blob(Path(donor.__file__).read_bytes()), repair.RECEIPT_DONOR_BLOB)
        self.assertEqual(repair.git_blob(Path(original.__file__).read_bytes()), "45fb76c8de4f4bf1a370bbc76225cbae500ed40d")
        self.assertEqual(self.report["intermediate_receipt_git_blob"], "81ec33c9e0f0a8045edff86c4a4095679c391476")
        self.assertEqual(self.report["total_prefix_consumers"], 3)
        self.assertEqual(self.report["candidate_sha256"], hashlib.sha256(self.fixed_bytes).hexdigest())

    def test_cash_and_loop_donor_still_fabricates_current_capacity(self):
        witness = {"market": [[], ["SELL", "MELON", 1]]}
        self.assertTrue(original.evaluate(self.old, **witness)[0])
        self.assertTrue(original.evaluate(self.cash_and_loop_only, **witness)[0])
        self.assertFalse(original.evaluate(self.fixed, **witness)[0])

    def test_receipt_only_donor_still_reserves_unexecutable_cash(self):
        for source in (self.old, self.receipt_only):
            self.assertEqual(cash(source, market=[[], ["HIRE"]]), 50)
        self.assertEqual(cash(self.fixed, market=[[], ["HIRE"]]), 0)

    def test_cash_current_and_future_suffixes_are_inert(self):
        orders = (["HIRE"], ["BUY_LAND"], ["BUY_PRODUCT", "WHEAT", 2],
                  ["BUY_SEED", "CARROT", 2], ["BUY_ANIMAL", "GOOSE", 1])
        for order in orders:
            for future in (False, True):
                kwargs = {"future_market": [[], order], "end": 23} if future else {"market": [[], order]}
                with self.subTest(order=order, future=future):
                    self.assertGreater(cash(self.old, **kwargs), 0)
                    self.assertEqual(cash(self.fixed, **kwargs), 0)

    def test_cash_active_prefix_is_unchanged(self):
        orders = (["HIRE"], ["BUY_LAND"], ["BUY_PRODUCT", "WHEAT", 2],
                  ["BUY_SEED", "CARROT", 2], ["BUY_ANIMAL", "GOOSE", 1], [])
        for order in orders:
            for future in (False, True):
                kwargs = {"future_market": [order], "end": 23} if future else {"market": [order]}
                self.assertEqual(cash(self.old, **kwargs), cash(self.fixed, **kwargs))

    def test_dead_hire_does_not_inflate_later_active_hire(self):
        kwargs = dict(market=[[], ["HIRE"]], future_market=[["HIRE"]], end=23)
        self.assertEqual(cash(self.old, **kwargs), 105)
        self.assertEqual(cash(self.fixed, **kwargs), 50)

    def test_dead_land_does_not_inflate_later_active_land(self):
        kwargs = dict(market=[[], ["BUY_LAND"]], future_market=[["BUY_LAND"]], end=23)
        self.assertEqual(cash(self.old, **kwargs), 600)
        self.assertEqual(cash(self.fixed, **kwargs), 200)

    def test_existing_day_reset_behavior_preserved(self):
        kwargs = dict(now=23, end=24, market=[["HIRE"]], future_market=[["HIRE"]], hires=3)
        self.assertEqual(cash(self.old, **kwargs), 115)
        self.assertEqual(cash(self.fixed, **kwargs), 115)

    def test_cash_nonlist_queue_is_empty(self):
        for value in ("HIRE", 1, {}, (["HIRE"],)):
            self.assertEqual(cash(self.fixed, market=value), 0)
            self.assertEqual(cash(self.fixed, future_market=value, end=23), 0)

    def test_cash_short_route_fallback(self):
        self.assertEqual(cash(self.fixed, market=[["HIRE"]], now=22, end=26, short=True), 50)

    def test_cap_clamp_and_raw_slot_preservation(self):
        queue = [[], ["HIRE"], ["HIRE"]]
        for limit, expected in ((-2, 0), (0, 0), (1, 0), (2, 50), (3, 105), (10, 105)):
            self.assertEqual(cash(self.fixed, market=queue, limit=limit), expected)
            self.assertEqual(cash(self.fixed, future_market=queue, end=23, limit=limit), expected)

    def test_three_consumers_suffix_invariance_grid(self):
        # 6 caps x 4 prefixes x 5 suffixes x 2 times = 240 vectors.
        for limit in (-2, 0, 1, 2, 3, 10):
            for prefix in ([[]], [["HIRE"]], [["BUY_PRODUCT", "WHEAT", 1]], [["SELL", "MELON", 1]]):
                prefix = prefix + [[]] * (max(1, limit) - 1)
                for suffix in ([], [["HIRE"]], [["BUY_LAND"]], [["BUY_PRODUCT", "WHEAT", 2]], [["SELL", "MELON", 1]]):
                    for future in (False, True):
                        key = "future_market" if future else "market"
                        ckw = {"end": 23} if future else {}
                        rkw = {"now": 22, "end": 23} if future else {}
                        self.assertEqual(cash(self.fixed, **ckw, **{key: prefix + suffix}, limit=limit),
                                         cash(self.fixed, **ckw, **{key: prefix}, limit=limit))
                        self.assertEqual(original.evaluate(self.fixed, **rkw, **{key: prefix + suffix}, limit=limit),
                                         original.evaluate(self.fixed, **rkw, **{key: prefix}, limit=limit))

    def test_receipt_active_prefix_equivalence_to_donor(self):
        for queue in ([[]], [["HIRE"]], [["SELL", "MELON", 1]], [["BUY_PRODUCT", "WHEAT", 1]], [["BUY_ANIMAL", "GOOSE", 1]]):
            for future in (False, True):
                kwargs = dict(now=22, end=23, future_market=queue) if future else dict(market=queue)
                self.assertEqual(original.evaluate(self.fixed, **kwargs), original.evaluate(self.receipt_only, **kwargs))

    def test_unrelated_ast_and_source_unchanged(self):
        left, right = ast.parse(self.old), ast.parse(self.fixed)
        right.body = [n for n in right.body if not (isinstance(n, ast.FunctionDef) and n.name == "_receipt_market_prefix")]
        for tree in (left, right):
            cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "SellScheduler")
            cls.body = [n for n in cls.body if not (isinstance(n, ast.FunctionDef) and n.name in ("cash_reserve", "receipt_profile"))]
        self.assertEqual(ast.dump(left, include_attributes=False), ast.dump(right, include_attributes=False))
        # Undo exactly the three changes + insertion and recover every byte.
        undone = self.fixed.replace(repair.CASH_NEW, repair.CASH_OLD, 1)
        start, end, method = repair.method_range(undone, "receipt_profile")
        method = method.replace(donor.CURRENT_NEW, donor.CURRENT_OLD, 1).replace(donor.FUTURE_NEW, donor.FUTURE_OLD, 1)
        undone = (undone[:start] + method + undone[end:]).replace(donor.HELPER, donor.HELPER_ANCHOR, 1)
        self.assertEqual(undone.encode(), self.source)

    def test_repeat_source_drift_and_intermediate_rejected(self):
        for data in (self.fixed_bytes, self.source + b"\n", self.receipt_only.encode()):
            with self.assertRaises(ValueError):
                repair.repair(data)

    def test_donor_drift_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            other = Path(tmp) / "changed_donor.py"
            other.write_bytes(Path(donor.__file__).read_bytes() + b"\n")
            with mock_patch.object(donor, "__file__", str(other)):
                with self.assertRaisesRegex(ValueError, "donor drift"):
                    repair.repair(self.source)

    def test_cli_exclusive_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.py"
            output = Path(tmp) / "candidate.py"
            source.write_bytes(self.source)
            command = [sys.executable, str(Path(repair.__file__)), str(source), "--output", str(output)]
            run = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(json.loads(run.stdout)["candidate_git_blob"], repair.git_blob(output.read_bytes()))
            self.assertEqual(output.read_bytes(), self.fixed_bytes)
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.assertEqual(source.read_bytes(), self.source)
            alias_command = command[:-1] + [str(source)]
            self.assertNotEqual(subprocess.run(alias_command, capture_output=True).returncode, 0)
            self.assertEqual(source.read_bytes(), self.source)

    def test_cli_hardlink_and_symlink_outputs_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.py"
            source.write_bytes(self.source)
            for name in ("hard", "sym"):
                output = Path(tmp) / name
                if name == "hard":
                    output.hardlink_to(source)
                else:
                    output.symlink_to(source)
                command = [sys.executable, str(Path(repair.__file__)), str(source), "--output", str(output)]
                self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
                self.assertEqual(source.read_bytes(), self.source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
