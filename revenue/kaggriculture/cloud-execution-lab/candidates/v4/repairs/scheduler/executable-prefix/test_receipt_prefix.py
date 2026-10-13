#!/usr/bin/env python3
"""Differential unit tests, not full-engine episodes or economic promotion.

Executes receipt_profile AST extracted from the exact Git-blob-verified source.
EOD drop is the verbatim pinned engine function; future-unit dependency is a
PASS-only test double that rejects every other action. No production module is
imported. Pass the fetched scheduler source as the first positional argument.
"""
from __future__ import annotations

import ast
import copy
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest

import repair_receipt_prefix as patch

SOURCE = Path(__file__).with_name("scheduler_source.py")
if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
    SOURCE = Path(sys.argv.pop(1))

# Verbatim function from engine blob 3c202c7e..., lines 845-860.
def _drop_inventories_to_shed(private, capacity):
    """Drop every per-farmer inventory into the shed up to `capacity`; overflow is discarded.
    Seeds are tracked separately in private["seeds"] and don't pass through the shed."""
    shed = private["shed"]
    for inv in private["inventories"]:
        for item, n in list(inv.items()):
            if n <= 0:
                del inv[item]
                continue
            current = sum(v for k, v in shed.items())
            room = max(0, capacity - current)
            take = min(n, room)
            if take > 0:
                shed[item] = shed.get(item, 0) + take
            del inv[item]


class Dependencies:
    def __init__(self):
        self.spawn_count = 0

    def _apply_unit_action(self, farm, private, idx, action, *unused):
        if action != ["PASS"]:
            raise AssertionError("unit-test dependency permits literal PASS only")

    def _spawn_hand(self, farm, size):
        self.spawn_count += 1
        return [0, 0]

    _drop_inventories_to_shed = staticmethod(_drop_inventories_to_shed)


def extract(source, deps):
    tree = ast.parse(source)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "SellScheduler")
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "receipt_profile")
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_receipt_market_prefix"]
    namespace = {"copy": copy, "m": deps, "parent": SimpleNamespace(PASS={"farmer": ["PASS"], "hands": [], "market": []})}
    exec(compile(ast.Module(body=functions + [method], type_ignores=[]), "<exact-selected-functions>", "exec"), namespace)
    return namespace["receipt_profile"], namespace.get("_receipt_market_prefix")


def evaluate(source, *, shed=99, cargo=1, now=23, end=23, market=None,
             future_market=None, limit=1, plan=()):
    deps = Dependencies()
    method, _ = extract(source, deps)
    farm = {"tiles": [[None]], "farmer": [0, 0], "hands": []}
    private = {"shed": {"CARROT": 1, "MELON": shed - 1}, "inventories": [{"WHEAT": cargo}]}
    base = {"farmer": ["PASS"], "hands": [], "market": [] if market is None else market}
    route = [{"farmer": ["PASS"], "hands": [], "market": []} for _ in range(end + 1)]
    if future_market is not None:
        route[end]["market"] = future_market
    owner = SimpleNamespace(controller=SimpleNamespace(R=[route], cur=0))
    config = {"shedCapacity": 100, "maxMarketOrdersPerTurn": limit}
    inputs = (farm, private, base, route, config)
    snapshot = copy.deepcopy(inputs)
    feasible = method(owner, {"step": now}, base, farm, private, end, "CARROT", config)
    value = feasible(plan)
    if inputs != snapshot:
        raise AssertionError("source function mutated input")
    return value, deps.spawn_count


class PrefixRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source_bytes = SOURCE.read_bytes()
        cls.fixed_bytes, cls.receipt = patch.repair(cls.source_bytes)
        cls.legacy = cls.source_bytes.decode()
        cls.fixed = cls.fixed_bytes.decode()
        # This deliberately applies the old one-site idea to the NEW source.
        # It is not a claim that original #12018 failed on its different pin.
        cls.naive = cls.legacy.replace(patch.HELPER_ANCHOR, patch.HELPER, 1).replace(patch.FUTURE_OLD, patch.FUTURE_NEW, 1)

    def test_exact_source_pin_and_compile(self):
        self.assertEqual(patch.git_blob(self.source_bytes), patch.SOURCE_BLOB)
        compile(self.fixed, "<candidate>", "exec")
        self.assertEqual(self.receipt["current_predebit_consumers_repaired"], 1)
        self.assertEqual(self.receipt["turn_loop_consumers_repaired"], 1)

    def test_current_suffix_sell_naive_port_still_fabricates_capacity(self):
        witness = {"market": [[], ["SELL", "MELON", 1]]}
        self.assertTrue(evaluate(self.legacy, **witness)[0])
        self.assertTrue(evaluate(self.naive, **witness)[0])
        self.assertFalse(evaluate(self.fixed, **witness)[0])

    def test_current_no_sale_matches_exact_engine_eod_drop(self):
        state = {"shed": {"CARROT": 1, "MELON": 98}, "inventories": [{"WHEAT": 1}]}
        _drop_inventories_to_shed(state, 100)
        self.assertEqual(sum(state["shed"].values()), 100)
        self.assertFalse(evaluate(self.fixed, market=[[], ["SELL", "MELON", 1]])[0])

    def test_future_suffix_sell_is_ignored(self):
        witness = {"now": 22, "end": 23, "future_market": [[], ["SELL", "MELON", 1]]}
        self.assertTrue(evaluate(self.legacy, **witness)[0])
        self.assertFalse(evaluate(self.fixed, **witness)[0])

    def test_current_and_future_suffix_buys_do_not_create_stock(self):
        for op, item in (("BUY_PRODUCT", "WHEAT"), ("BUY_ANIMAL", "GOOSE")):
            for future in (False, True):
                kwargs = {"shed": 99, "cargo": 0}
                kwargs.update({"now": 22, "end": 23, "future_market": [[], [op, item, 1]]} if future else {"market": [[], [op, item, 1]]})
                with self.subTest(op=op, future=future):
                    self.assertFalse(evaluate(self.legacy, **kwargs)[0])
                    self.assertTrue(evaluate(self.fixed, **kwargs)[0])

    def test_current_and_future_suffix_hires_do_not_spawn(self):
        for future in (False, True):
            kwargs = {"shed": 1, "cargo": 0}
            kwargs.update({"now": 22, "end": 23, "future_market": [[], ["HIRE"]]} if future else {"market": [[], ["HIRE"]]})
            with self.subTest(future=future):
                self.assertEqual(evaluate(self.legacy, **kwargs)[1], 1)
                self.assertEqual(evaluate(self.fixed, **kwargs)[1], 0)

    def test_active_prefix_behavior_preserved(self):
        for market in ([['SELL', 'MELON', 1]], [['BUY_PRODUCT', 'WHEAT', 1]], [['BUY_ANIMAL', 'GOOSE', 1]], [['HIRE']], [[]]):
            for future in (False, True):
                kwargs = {"shed": 99, "cargo": 1}
                kwargs.update({"now": 22, "end": 23, "future_market": market} if future else {"market": market})
                with self.subTest(market=market, future=future):
                    self.assertEqual(evaluate(self.legacy, **kwargs), evaluate(self.fixed, **kwargs))

    def test_raw_slots_and_min_one_cap(self):
        _, prefix = extract(self.fixed, Dependencies())
        market = [[], ["SELL", "MELON", 1], ["HIRE"]]
        for limit in (-5, 0, 1, 2, 10):
            with self.subTest(limit=limit):
                value = prefix({"market": market}, {"maxMarketOrdersPerTurn": limit})
                self.assertEqual(value, market[:max(1, limit)])
                self.assertIsNot(value, market)
                if len(value) > 1:
                    self.assertIs(value[1], market[1])
                self.assertEqual(evaluate(self.fixed, market=market, limit=limit)[0], limit >= 2)
        self.assertEqual(prefix({"market": tuple(market)}, {}), [])
        self.assertEqual(prefix(None, {}), [])

    def test_empty_tuple_market_no_executable_forecast(self):
        self.assertTrue(evaluate(self.fixed, market=(['BUY_PRODUCT', 'WHEAT', 1],), shed=99, cargo=0)[0])

    def test_other_functions_and_class_methods_unchanged(self):
        left = ast.parse(self.legacy)
        right = ast.parse(self.fixed)
        right.body = [n for n in right.body if not (isinstance(n, ast.FunctionDef) and n.name == '_receipt_market_prefix')]
        for tree in (left, right):
            cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'SellScheduler')
            cls.body = [n for n in cls.body if not (isinstance(n, ast.FunctionDef) and n.name == 'receipt_profile')]
        self.assertEqual(ast.dump(left, include_attributes=False), ast.dump(right, include_attributes=False))
        a, b, _ = patch.selected_method(self.legacy)
        x, y, _ = patch.selected_method(self.fixed)
        self.assertEqual(self.legacy[:a].replace(patch.HELPER_ANCHOR, patch.HELPER, 1), self.fixed[:x])
        self.assertEqual(self.legacy[b:], self.fixed[y:])

    def test_drift_and_repeat_fail_closed(self):
        for data in (self.source_bytes + b'\n', self.fixed_bytes, self.source_bytes.replace(b'cap-1', b'cap-2', 1)):
            with self.assertRaises(ValueError):
                patch.repair(data)

    def test_input_data_identity_grid(self):
        for shed in (1, 98, 99, 100):
            for cargo in (0, 1, 3):
                for future in (False, True):
                    for suffix in ([], [['SELL', 'MELON', 1]], [['BUY_PRODUCT', 'WHEAT', 1]], [['HIRE']]):
                        prefix = [[]]
                        kwargs = {'shed': shed, 'cargo': cargo}
                        key = 'future_market' if future else 'market'
                        if future:
                            kwargs.update(now=22, end=23)
                        full = evaluate(self.fixed, **kwargs, **{key: prefix + suffix})
                        clipped = evaluate(self.fixed, **kwargs, **{key: prefix})
                        self.assertEqual(full, clipped)

    def test_cli_no_overwrite_or_input_edit(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'source.py'
            target = Path(tmp) / 'candidate.py'
            source.write_bytes(self.source_bytes)
            command = [sys.executable, str(Path(patch.__file__)), str(source), '--output', str(target)]
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.assertEqual(target.read_bytes(), self.fixed_bytes)
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.assertEqual(source.read_bytes(), self.source_bytes)


if __name__ == '__main__':
    unittest.main(verbosity=2)
