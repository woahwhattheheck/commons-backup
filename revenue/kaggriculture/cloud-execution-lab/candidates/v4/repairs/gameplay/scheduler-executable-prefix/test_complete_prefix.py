#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exact-source differential unit tests; no full-engine game/economics claim.

The two authentic source fixtures are hashed before compilation. Future units
use a literal-PASS-only test double; HIRE cost/spawn is instrumented. EOD drop
below is the verbatim pinned official engine function. No live agent is loaded.
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
import complete_prefix as completion

HERE = Path(__file__).resolve().parent
DONOR_BLOB = "5e8f54ca20fa755bc6ced55decdcdf0193cda812"
SOURCE_BLOB = "da1b6fb571e79ba7dab54c8d816e45afb934e4d2"


# Verbatim from official engine blob 3c202c7ee921da239356789e266b694635103fc4.
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


class Mechanics:
    def __init__(self):
        self.spawns = 0

    def _apply_unit_action(self, farm, private, idx, action, *args):
        if action != ['PASS']:
            raise AssertionError('fixture permits literal PASS only')

    def _spawn_hand(self, farm, size):
        self.spawns += 1
        return [0, 0]

    def _hire_cost(self, hires, mult):
        if hires != 0:
            raise AssertionError('fixture exercises first HIRE only')
        return mult

    _drop_inventories_to_shed = staticmethod(_drop_inventories_to_shed)


def extract(text, mechanics):
    tree = ast.parse(text)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'SellScheduler')
    body = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ('_engine_market_prefix', '_order_spend')]
    body += [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in ('receipt_profile', 'cash_reserve')]
    ns = {'copy': copy, 'm': mechanics, 'parent': SimpleNamespace(PASS={'farmer': ['PASS'], 'hands': [], 'market': []})}
    exec(compile(ast.Module(body=body, type_ignores=[]), '<authenticated-selected-functions>', 'exec'), ns)
    return ns


def witness(text, *, now=23, end=23, market=None, future=None, cap=1, shed=99, cargo=1):
    m = Mechanics()
    ns = extract(text, m)
    farm = {'farmer': [0, 0], 'hands': [], 'tiles': [[None]], 'unlocked_quadrants': ['NW'], 'hires_today': 0}
    private = {'shed': {'CARROT': 1, 'MELON': shed - 1}, 'inventories': [{'WHEAT': cargo}]}
    base = {'farmer': ['PASS'], 'hands': [], 'market': [] if market is None else market}
    route = [{'farmer': ['PASS'], 'hands': [], 'market': []} for _ in range(end + 1)]
    if future is not None:
        route[end]['market'] = future
    owner = SimpleNamespace(controller=SimpleNamespace(R=[route], cur=0))
    obs = {'step': now, 'player': 0, 'farms': [farm], 'market': {'inventory': {}}}
    cfg = {'shedCapacity': 100, 'maxMarketOrdersPerTurn': cap}
    inputs = (farm, private, base, route, obs, cfg)
    frozen = copy.deepcopy(inputs)
    feasible = ns['receipt_profile'](owner, obs, base, farm, private, end, 'CARROT', cfg)(())
    if inputs != frozen:
        raise AssertionError('input mutation')
    return feasible, m.spawns


class CompletionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.donor = (HERE / 'legacy/peer_prefix_donor.py').read_bytes()
        cls.source = (HERE / 'legacy/scheduler_source.py').read_bytes()
        if completion.git_blob(cls.donor) != DONOR_BLOB or completion.git_blob(cls.source) != SOURCE_BLOB:
            raise ValueError('fixture source custody mismatch')
        ns = {'__name__': '_authenticated_peer_donor'}
        exec(compile(cls.donor, '<exact-peer-donor>', 'exec'), ns)
        ns['self_test']()
        cls.parent_bytes = ns['transform'](cls.source.decode()).encode()
        cls.fixed_bytes = completion.complete(cls.parent_bytes)
        cls.parent = cls.parent_bytes.decode()
        cls.fixed = cls.fixed_bytes.decode()

    def test_exact_parent_and_postimage(self):
        self.assertEqual(completion.git_blob(self.parent_bytes), completion.PARENT_BLOB)
        self.assertEqual(completion.git_blob(self.fixed_bytes), completion.RESULT_BLOB)
        compile(self.fixed, '<complete>', 'exec')

    def test_real_peer_postimage_fails_current_sell_witness(self):
        market = [[], ['SELL', 'MELON', 1]]
        self.assertEqual(witness(self.parent, market=market), (True, 0))
        self.assertEqual(witness(self.fixed, market=market), (False, 0))
        private = {'shed': {'CARROT': 1, 'MELON': 98}, 'inventories': [{'WHEAT': 1}]}
        _drop_inventories_to_shed(private, 100)
        self.assertEqual(sum(private['shed'].values()), 100)

    def test_standard_ten_order_limit(self):
        market = [[] for _ in range(10)] + [['SELL', 'MELON', 1]]
        self.assertTrue(witness(self.parent, market=market, cap=10)[0])
        self.assertFalse(witness(self.fixed, market=market, cap=10)[0])

    def test_min_one_and_active_prefix_controls(self):
        market = [[], ['SELL', 'MELON', 1]]
        for cap in (-8, 0, 1, 2, 10):
            self.assertEqual(witness(self.fixed, market=market, cap=cap)[0], cap >= 2)
        for row in (['SELL', 'MELON', 1], ['BUY_PRODUCT', 'WHEAT', 1], ['BUY_ANIMAL', 'GOOSE', 1], ['HIRE'], []):
            self.assertEqual(witness(self.parent, market=[row]), witness(self.fixed, market=[row]))

    def test_inherited_future_prefix_preserved(self):
        for row in (['SELL', 'MELON', 1], ['BUY_PRODUCT', 'WHEAT', 1], ['HIRE']):
            kwargs = {'now': 22, 'end': 23, 'future': [[], row]}
            self.assertEqual(witness(self.parent, **kwargs), witness(self.fixed, **kwargs))
            self.assertEqual(witness(self.fixed, **kwargs), witness(self.fixed, now=22, end=23, future=[[]]))

    def test_inherited_cash_reserve_prefix_preserved(self):
        for text in (self.parent, self.fixed):
            ns = extract(text, Mechanics())
            for future in (False, True):
                for executable in (False, True):
                    rows = [['HIRE']] if executable else [[], ['HIRE']]
                    route = [{'market': []}, {'market': rows if future else []}]
                    owner = SimpleNamespace(controller=SimpleNamespace(R=[route], cur=0))
                    farm = {'unlocked_quadrants': ['NW'], 'hires_today': 0}
                    obs = {'step': 0, 'farms': [farm], 'player': 0, 'market': {'inventory': {}}}
                    value = ns['cash_reserve'](owner, obs, {'maxMarketOrdersPerTurn': 1}, {'market': [] if future else rows}, 1)
                    self.assertEqual(value, int(executable))

    def test_one_helper_three_sites_and_only_one_delta(self):
        self.assertEqual(self.fixed.count('def _engine_market_prefix('), 1)
        self.assertEqual(self.fixed.count('orders=_engine_market_prefix(market_action,config)'), 2)
        self.assertEqual(self.fixed.count('for o in _engine_market_prefix(base,config):'), 1)
        self.assertEqual(self.fixed.replace(completion.AFTER, completion.BEFORE, 1), self.parent)

    def test_96_suffix_invariance_cases_and_nonmutation(self):
        for shed in (1, 98, 99, 100):
            for cargo in (0, 1, 3):
                for future in (False, True):
                    for row in ([], ['SELL', 'MELON', 1], ['BUY_PRODUCT', 'WHEAT', 1], ['HIRE']):
                        kwargs = {'shed': shed, 'cargo': cargo}
                        key = 'future' if future else 'market'
                        if future:
                            kwargs.update(now=22, end=23)
                        self.assertEqual(witness(self.fixed, **kwargs, **{key: [[], row]}), witness(self.fixed, **kwargs, **{key: [[]]}))

    def test_drift_and_double_apply_rejected(self):
        for data in (self.source, self.parent_bytes + b'\n', self.fixed_bytes):
            with self.assertRaises(ValueError):
                completion.complete(data)

    def test_cli_exclusive_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent, output = Path(tmp) / 'parent.py', Path(tmp) / 'output.py'
            parent.write_bytes(self.parent_bytes)
            command = [sys.executable, str(HERE / 'complete_prefix.py'), str(parent), str(output)]
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.assertEqual(output.read_bytes(), self.fixed_bytes)
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.assertEqual(parent.read_bytes(), self.parent_bytes)


if __name__ == '__main__':
    unittest.main(verbosity=2)
