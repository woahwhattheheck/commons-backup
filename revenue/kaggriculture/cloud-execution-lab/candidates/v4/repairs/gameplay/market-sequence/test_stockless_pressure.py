# SPDX-License-Identifier: Apache-2.0
"""Source-pinned native/official-engine contracts; no gameplay score inference.

Usage: python test_stockless_pressure.py --runtime /path/to/extracted/runtime
Run the same command with python -O. No files in the runtime are modified.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import itertools
import json
import random
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

import stockless_pressure as candidate

ROOT = None
PINNED = {
    'titan_runtime.py': 'b952c9c228ecbde592bf3d2df01638677abb0d24',
    'pressure_priority.py': '7261674962d10fc8bc6af5ff73ff9212c40f61ad',
    'sell_priority.py': 'd832174e26451d2bbe326991cc206a212cfebc12',
    'scheduler.py': 'a483b24dd72b580d7d8811636b54d2d44f391575',
    'mechanics.py': '044a4f9c0a4a44dde10ada57563238bcaf82075d',
    'observed_clone.py': 'f810d53193d3035655a36c21021e18ba1d415916',
    'checks/reference/engine/kaggriculture.py': '3c202c7ee921da239356789e266b694635103fc4',
    'checks/reference/engine/kaggriculture.json': 'b354d06b742fe48402513792253f1a5c29366b20',
    'checks/reference/engine/utils.py': '91c8822ee6201ba4a5a8416c7dbe34f95dd61c87',
    'checks/reference/evaluator/evaluate.py': '1fb6b655bb4ca1e1684be165a8ef513e2e6c2325',
    'checks/reference/evaluator/loader.py': '23948e10cfc3d32f46c9abb1321b0d8fc8db21d5',
    'reference/next-panel/vendor/arlene.py': 'bdb9cf58148a3c7961c085f4902759537decabf6',
    'reference/decision/decision.py': '2931aa55831204fbb473ab85a6f5b81ec947fcf7',
    'reference/titan-current/deadline_adapter.py': '664aa4f8a21368c388dfa6714406519b6535ef7f',
}
COUNTS = {'official_market_calls': 0, 'official_interpreter_calls': 0,
          'market_pair_cases': 0, 'strict_margin_improvements': 0,
          'full_unit_stage_cases': 0, 'source_regression_witnesses': []}


def git_blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def action(rows=(), farmer=('PASS',), hands=()):
    return {'farmer': list(farmer), 'hands': copy.deepcopy(list(hands)),
            'market': copy.deepcopy(list(rows))}


class Contracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if ROOT is None:
            raise RuntimeError('Pass --runtime with the exact existing source fixture')
        for relative, expected in PINNED.items():
            path = ROOT / relative
            actual = git_blob(path.read_bytes())
            if actual != expected:
                raise RuntimeError(f'SOURCE MISMATCH {relative}: {actual} != {expected}')
        sys.path.insert(0, str(ROOT))
        cls.pressure = load('pressure_priority', ROOT/'pressure_priority.py')
        cls.scheduler = load('scheduler', ROOT/'scheduler.py')
        cls.runtime = load('titan_runtime', ROOT/'titan_runtime.py')
        cls.ev = load('_stockless_evaluator', ROOT/'checks/reference/evaluator/evaluate.py')
        cls.engine, cls.engine_hashes = cls.ev.get_engine(
            ROOT/'checks/reference/engine', ROOT/'checks/reference/evaluator/loader.py')
        cls._runtime_source = (ROOT/'titan_runtime.py').read_text()
        # Apply only the prospective call-site edit in memory to the WHOLE
        # authenticated native module; never rewrite the runtime on disk.
        old = '        result = pressure.transform(selected, obs, cfg, quote=mechanics.market_price)'
        new = ('        from stockless_pressure import transform as stockless_transform\n'
               '        from scheduler import post_units\n'
               '        result = stockless_transform(selected, obs, cfg, pressure=pressure,\n'
               '                                     post_units=post_units, quote=mechanics.market_price)')
        if cls._runtime_source.count(old) != 1:
            raise RuntimeError('native pressure call-site no longer unique')
        cls.native = types.ModuleType('_stockless_native_candidate')
        cls.native.__file__ = str(ROOT/'titan_runtime.py')
        sys.modules[cls.native.__name__] = cls.native
        exec(compile(cls._runtime_source.replace(old, new), cls.native.__file__, 'exec'),
             cls.native.__dict__)

    def fixture(self, *, seat=0, shed=None, rival=None, inventory=10000, step=1, limit=10):
        e, S = self.engine, self.ev.Struct
        cfg = S({key: val.get('default') if isinstance(val, dict) else val
                 for key, val in e.specification['configuration'].items()})
        cfg.weedSpawnChance = 0
        cfg.maxMarketOrdersPerTurn = limit
        farms = [e._new_farm(10, 0), e._new_farm(10, 0)]
        market = e._new_market()
        for item in market['inventory']:
            market['inventory'][item] = inventory
        e._refresh_prices(market)
        town = {'unlocked_shops': []}
        state = []
        for player in (0, 1):
            private = e._new_private()
            private['shed'] = copy.deepcopy((shed if player == seat else rival) or {})
            state.append(S(observation=S(player=player, step=step, day=step//24, hour=step%24,
                                         farms=farms, private=private, market=market, town=town),
                           action=action(), status='ACTIVE', reward=0))
        return state, S(configuration=cfg, done=False, info={'seed': 9600803})

    def compact(self, rows, shed=None, market=None, cfg=None, quote=None):
        state, env = self.fixture(shed=shed or {'MILK': 10})
        return candidate.compact_stockless_sales(
            rows, state[0].observation.private['shed'], market or state[0].observation.market,
            env.configuration if cfg is None else cfg, quote=quote or self.engine.market_price)

    def adapted(self, a, obs, cfg, **kwargs):
        return candidate.transform(a, obs, cfg, pressure=self.pressure,
                                   post_units=kwargs.get('post_units', self.scheduler.post_units),
                                   quote=kwargs.get('quote', self.engine.market_price))

    def execute(self, state, env, a, rival_action, seat, full=False):
        s, e = copy.deepcopy(state), copy.deepcopy(env)
        s[seat].action = copy.deepcopy(a)
        s[1-seat].action = copy.deepcopy(rival_action)
        if full:
            self.engine.interpreter(s, e)
            COUNTS['official_interpreter_calls'] += 1
        else:
            self.engine._process_market(s, e)
            COUNTS['official_market_calls'] += 1
        money = [farm['money'] for farm in s[0].observation.farms]
        return s, money[seat], money[1-seat]

    def test_01_exact_baseline_counterexample_both_seats(self):
        for seat in (0, 1):
            state, env = self.fixture(seat=seat, shed={'MILK': 10}, rival={'MILK': 10})
            a = action([['SELL', 'MILK', 10], ['SELL', 'WOOL', 100]])
            rival = action([['SELL', 'MILK', 10]])
            old = self.pressure.transform(a, state[seat].observation, env.configuration,
                                          quote=self.engine.market_price)
            new = self.adapted(a, state[seat].observation, env.configuration)
            self.assertEqual(old['market'], list(reversed(a['market'])))
            self.assertEqual(new, a)
            b, bc, br = self.execute(state, env, old, rival, seat)
            n, nc, nr = self.execute(state, env, new, rival, seat)
            self.assertEqual((bc, br, nc, nr), (1296, 1506, 1411, 1411))
            self.assertEqual(nc-nr-(bc-br), 210)
            for who in (0, 1):
                self.assertEqual(b[who].observation.private, n[who].observation.private)
            COUNTS['source_regression_witnesses'].append(
                {'seat': seat, 'old_cash': bc, 'old_rival_cash': br,
                 'new_cash': nc, 'new_rival_cash': nr, 'margin_delta': 210})

    def test_02_duplicate_exhaustion_and_partial_lots_keep_rows(self):
        rows = [['SELL', 'MILK', 3], ['SELL', 'MILK', 8], ['SELL', 'MILK', 7],
                ['SELL', 'WOOL', 2], []]
        out = self.compact(rows, {'MILK': 5, 'WOOL': 2})
        self.assertEqual(out, [rows[0], rows[1], rows[3], rows[2], rows[4]])
        self.assertTrue(all(any(row is original for original in rows) for row in out))
        self.assertEqual(sorted(map(repr, out)), sorted(map(repr, rows)))
        self.assertEqual(rows[1][2], 8)  # Partial fill does not trim the request.

    def test_03_dead_raw_suffix_and_minimum_one_cap(self):
        for cap in (-2, 0, 1, 2, 5, 10, 12):
            with self.subTest(cap=cap):
                live = max(1, cap)
                rows = [['SELL', 'WOOL', 100], ['SELL', 'MILK', 10]] + [[] for _ in range(live)]
                rows += [['BUY_PRODUCT', 'WHEAT', 90], ['SELL', 'MILK', 999]]
                out = self.compact(rows, {'MILK': 10}, cfg={'maxMarketOrdersPerTurn': cap})
                self.assertEqual(out[live:], rows[live:])
                self.assertEqual(out[:2], rows[:2] if live == 1 else [rows[1], rows[0]])

    def test_04_economic_input_unknown_and_malformed_barriers(self):
        for row in (['HIRE'], ['BUY_LAND'], ['BUY_SEED', 'WHEAT', 1],
                    ['BUY_PRODUCT', 'WHEAT', 1], ['BUY_ANIMAL', 'COW', 1],
                    ['SELL', 'WHEAT', 1], ['SELL', 'FERTILIZER', 1], ['SELL', 'X', 0],
                    ['SELL', 'MILK', True], ['SELL', 'MILK', -1], ['SELL', 'MILK', '2'],
                    ['SELL', 'MILK', 1.5], ['SELL', 'MILK', 257], None, ['PASS'],
                    ['SELL', [], 1], ['SELL', 'MILK', 1, 'EXTRA']):
            rows = [['SELL', 'WOOL', 100], ['SELL', 'MILK', 10], row]
            with self.subTest(row=row):
                self.assertIs(self.compact(rows), rows)

    def test_05_invalid_physical_evidence_fails_closed(self):
        state, env = self.fixture()
        rows = [['SELL', 'WOOL', 100], ['SELL', 'MILK', 10]]
        for shed in (None, [], {'MILK': True}, {'MILK': -1}, {'MILK': 101},
                     {'MILK': '1'}, {'MILK': 2.0}, {1: 2}, {'MILK': float('nan')}):
            with self.subTest(shed=shed):
                self.assertIs(candidate.compact_stockless_sales(
                    rows, shed, state[0].observation.market, env.configuration,
                    quote=self.engine.market_price), rows)

    def test_06_bad_configuration_and_quote_fail_closed(self):
        rows = [['SELL', 'WOOL', 100], ['SELL', 'MILK', 10]]
        for cfg in ({'shedCapacity': 99}, {'shedCapacity': True}, {'shedCapacity': 100.0},
                    {'maxMarketOrdersPerTurn': True}, {'maxMarketOrdersPerTurn': '10'}):
            self.assertIs(self.compact(rows, cfg=cfg), rows)
        for quote in (lambda p, i, params: 0, lambda p, i, params: float('nan'),
                      lambda p, i, params: float('inf'), lambda p, i, params: True,
                      lambda p, i, params: 160+i-10000, lambda p, i, params: 159):
            self.assertIs(self.compact(rows, quote=quote), rows)
        big = [rows[0]] * 65 + [rows[1]]
        self.assertIs(self.compact(big, cfg={'maxMarketOrdersPerTurn': 66}), big)

    def test_07_identity_flat_floor_and_no_productive_stock(self):
        rows = [['SELL', 'WOOL', 100], ['SELL', 'MILK', 10]]
        floor = {'prices': {'MILK': 1}, 'inventory': {'MILK': 11000}}
        self.assertIs(self.compact(rows, market=floor), rows)
        state, env = self.fixture()
        self.assertIs(candidate.compact_stockless_sales(rows, {}, state[0].observation.market,
                                                       env.configuration, quote=self.engine.market_price), rows)
        complete = [rows[1], rows[0]]
        self.assertIs(self.compact(complete), complete)

    def test_08_input_immutability_and_exact_delegate_count(self):
        state, env = self.fixture(shed={'MILK': 10})
        a = action([['SELL', 'WOOL', 100], ['SELL', 'MILK', 10]])
        before = copy.deepcopy((state, a, env.configuration))
        calls = []
        def delegate(*args, **kwargs):
            calls.append('pressure')
            return self.pressure.transform(*args, **kwargs)
        def projector(*args, **kwargs):
            calls.append('units')
            return self.scheduler.post_units(*args, **kwargs)
        out = candidate.transform(a, state[0].observation, env.configuration,
                                  pressure=types.SimpleNamespace(transform=delegate),
                                  post_units=projector, quote=self.engine.market_price)
        self.assertEqual(calls, ['pressure', 'units'])
        self.assertEqual((state, a, env.configuration), before)
        self.assertEqual(out['farmer'], a['farmer'])
        self.assertEqual(out['hands'], a['hands'])

    def test_09_invalid_player_and_projection_decline_not_swallow_deadline(self):
        state, env = self.fixture(shed={'MILK': 10})
        a = action([['SELL', 'WOOL', 100], ['SELL', 'MILK', 10]])
        old = self.pressure.transform(a, state[0].observation, env.configuration, quote=self.engine.market_price)
        for player in (True, -1, 2, '0', None):
            obs = copy.deepcopy(state[0].observation); obs['player'] = player
            self.assertEqual(self.adapted(a, obs, env.configuration), old)
        def broken(*args):
            raise ValueError('bad projection')
        self.assertEqual(self.adapted(a, state[0].observation, env.configuration, post_units=broken), old)
        sentinel = self.runtime.deadline.DeadlineExceeded('guard')
        def cancelled(*args):
            raise sentinel
        with self.assertRaises(self.runtime.deadline.DeadlineExceeded) as caught:
            self.adapted(a, state[0].observation, env.configuration, post_units=cancelled)
        self.assertIs(caught.exception, sentinel)

    def test_10_actual_native_method_prospective_port_and_disabled_identity(self):
        for seat in (0, 1):
            state, env = self.fixture(seat=seat, shed={'MILK': 10})
            a = action([['SELL', 'MILK', 10], ['SELL', 'WOOL', 100]])
            for enabled in (False, True):
                agent = self.native.TitanAgent(self.native.Features(market_pressure=enabled))
                out = agent._market_pressure_selected(state[seat].observation, env.configuration, a)
                self.assertEqual(out, a)
                if not enabled:
                    self.assertIs(out, a)
                else:
                    self.assertEqual(agent.diagnostics['market_pressure'], {'enabled': True, 'changed': False})

    def test_11_full_interpreter_drop_pickup_and_actor_order(self):
        # Capture the exact official market-entry private to reject stale
        # pre-unit and unbounded-capacity projections. Invoke FULL interpreter.
        cases = [
            ({'MILK': 10}, [{'WOOL': 20}], ['DROP'], [], []),
            ({'MILK': 10, 'WOOL': 20}, [{}], ['PICKUP', 'WOOL', 20], [], []),
            ({'MILK': 10, 'WOOL': 20}, [{}, {'WOOL': 20}], ['PICKUP', 'WOOL', 20], [[4, 4]], [['DROP']]),
            ({'MILK': 10, 'WOOL': 20}, [{'WOOL': 20}, {}], ['DROP'], [[4, 4]], [['PICKUP', 'WOOL', 40]]),
            ({'MILK': 10, 'WHEAT': 90}, [{'WOOL': 20}], ['DROP'], [], []),
            ({'MILK': 10, 'WHEAT': 80}, [{'WOOL': 20}], ['DROP'], [], []),
            ({'MILK': 10}, [{'WOOL': 20}], ['EAST'], [], []),
            ({'MILK': 10}, [{}, {'WOOL': 20}], ['PASS'], [], [['DROP']]),
        ]
        for seat, step, access, case in itertools.product((0, 1), (1, 22, 23, 718),
                                                          ((4, 4), (5, 4), (4, 5), (5, 5)), cases):
            shed, invs, farmer, handpos, hands = case
            with self.subTest(seat=seat, step=step, access=access, farmer=farmer):
                state, env = self.fixture(seat=seat, shed=shed, rival={'MILK': 10}, step=step)
                farm = state[0].observation.farms[seat]
                farm['farmer'] = list(access)
                farm['hands'] = [list(access) for _ in handpos]
                state[seat].observation.private['inventories'] = copy.deepcopy(invs)
                a = action([['SELL', 'WOOL', 100], ['SELL', 'MILK', 10]], farmer, hands)
                _, predicted = self.scheduler.post_units(state[seat].observation, a, env.configuration)
                captured = []
                real_market = self.engine._process_market
                def capture(s, e):
                    captured.append(copy.deepcopy(s[seat].observation.private))
                    return real_market(s, e)
                with patch.object(self.engine, '_process_market', capture):
                    self.execute(state, env, a, action(), seat, full=True)
                self.assertEqual(captured, [predicted])
                out = self.adapted(a, state[seat].observation, env.configuration)
                live = predicted['shed'].get('WOOL', 0) > 0
                self.assertEqual(out['market'][0][1], 'WOOL' if live else 'MILK')
                self.assertEqual(out['farmer'], a['farmer']); self.assertEqual(out['hands'], a['hands'])
                # Compare baseline/candidate through full unit-market-EOD, not
                # just a fabricated post-unit shed or reimplemented transition.
                old = self.pressure.transform(a, state[seat].observation, env.configuration,
                                              quote=self.engine.market_price)
                b, bc, br = self.execute(state, env, old, action([['SELL', 'MILK', 10]]), seat, full=True)
                n, nc, nr = self.execute(state, env, out, action([['SELL', 'MILK', 10]]), seat, full=True)
                self.assertGreaterEqual(nc-nr, bc-br)
                for who in (0, 1):
                    self.assertEqual(b[who].observation.private, n[who].observation.private)
                COUNTS['full_unit_stage_cases'] += 1

    def test_12_paired_official_market_stable_compaction_grid(self):
        rng = random.Random(9600912)
        products = sorted(candidate.SALE_ONLY)
        for cell in range(2400):
            seat = cell % 2
            first, second = rng.sample(products, 2)
            stock1, stock2 = rng.choice((1, 2, 5, 12)), rng.choice((0, 1, 4))
            inv = rng.choice((9990, 10000, 10055, 10075, 10090))
            shed = {first: stock1, second: stock2}
            rival_shed = {first: rng.choice((0, 1, 10, 30)), second: rng.choice((0, 4, 20))}
            rows = [['SELL', 'WOOL' if 'WOOL' not in shed else 'EGG', 80],
                    ['SELL', first, 2], ['SELL', first, 12], ['SELL', first, 5],
                    ['SELL', second, 6], []]
            # Ensure the leading decoy is physically zero, without aliasing a
            # productive item chosen in this cell.
            rows[0][1] = next(p for p in products if p not in shed)
            rival_rows = [rng.choice(([], ['SELL', first, 5], ['SELL', second, 8],
                                     ['SELL', first, 30])) for _ in rows]
            state, env = self.fixture(seat=seat, shed=shed, rival=rival_shed, inventory=inv)
            new_rows = candidate.compact_stockless_sales(rows, shed, state[seat].observation.market,
                                                          env.configuration, quote=self.engine.market_price)
            b, bc, br = self.execute(state, env, action(rows), action(rival_rows), seat)
            n, nc, nr = self.execute(state, env, action(new_rows), action(rival_rows), seat)
            with self.subTest(cell=cell):
                self.assertGreaterEqual(nc, bc)
                self.assertGreaterEqual(nc-nr, bc-br)
                self.assertLessEqual(nr, br)
                self.assertEqual(len(new_rows), len(rows))
                self.assertEqual(sorted(map(repr, new_rows)), sorted(map(repr, rows)))
                for who in (0, 1):
                    self.assertEqual(b[who].observation.private, n[who].observation.private)
            COUNTS['market_pair_cases'] += 1
            COUNTS['strict_margin_improvements'] += int(nc-nr > bc-br)

    def test_13_adapter_uses_selected_unit_vector_not_cached_snapshot(self):
        state, env = self.fixture(shed={'MILK': 10})
        state[0].observation.farms[0]['farmer'] = [4, 4]
        state[0].observation.private['inventories'] = [{'WOOL': 20}]
        rows = [['SELL', 'WOOL', 100], ['SELL', 'MILK', 10]]
        self.assertEqual(self.adapted(action(rows), state[0].observation, env.configuration)['market'][0][1], 'MILK')
        self.assertEqual(self.adapted(action(rows, ['DROP']), state[0].observation, env.configuration)['market'][0][1], 'WOOL')
        self.assertEqual(state[0].observation.private['shed'], {'MILK': 10})

    def test_14_existing_baseline_is_exact_when_no_physical_change(self):
        for cell in range(100):
            state, env = self.fixture(shed={'MILK': 20, 'WOOL': 20})
            a = action([['SELL', 'WOOL', 1+cell%20], ['SELL', 'MILK', 1+cell%20]])
            expected = self.pressure.transform(a, state[0].observation, env.configuration,
                                               quote=self.engine.market_price)
            self.assertEqual(self.adapted(a, state[0].observation, env.configuration), expected)

    def test_15_turns_per_day_minimum_one_uses_official_normalization(self):
        state, env = self.fixture(shed={'MILK': 10})
        env.configuration.turnsPerDay = 0
        a = action([['SELL', 'WOOL', 100], ['SELL', 'MILK', 10]])
        out = self.adapted(a, state[0].observation, env.configuration)
        self.assertEqual(out['market'][0][1], 'MILK')
        self.assertEqual(env.configuration.turnsPerDay, 0)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--receipt', type=Path)
    args, rest = parser.parse_known_args()
    ROOT = args.runtime.resolve()
    program = unittest.main(argv=[sys.argv[0]] + rest, exit=False, verbosity=2)
    report = {'optimized': not __debug__, 'tests_run': program.result.testsRun,
              'successful': program.result.wasSuccessful(), 'source_git_blobs': PINNED,
              'counts': COUNTS, 'scope': 'component/native-call-site/official-engine, not field economics'}
    if args.receipt:
        args.receipt.write_text(json.dumps(report, sort_keys=True, indent=2)+'\n')
    print(json.dumps(report, sort_keys=True))
    raise SystemExit(0 if report['successful'] else 1)
