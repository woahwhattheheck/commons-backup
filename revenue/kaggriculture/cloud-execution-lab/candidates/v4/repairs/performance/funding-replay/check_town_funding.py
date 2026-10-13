# SPDX-License-Identifier: Apache-2.0
"""Authenticated, full-official-interpreter acceptance for town-aware funding.

Use --runtime pointing to the extracted b567 checked archive. No network,
source replacement, alternate interpreter, or production activation occurs.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
import unittest

import apply_town_funding as composer

MANIFEST_SHA256 = 'e87d70dd3bcf5aea1e929f1a5dbdc86f3cc33d8a0b3492986f2970fc8e774be2'
BASE_SHA256 = '5ca1bc39efed756de71207f46926744ea69f9d2f300dd7b9c1a8cc4dbefeb9ef'
STATS = {'official_interpreter_calls': 0, 'oracle_cases': 0,
         'candidate_trace_comparisons': 0, 'legacy_trace_mismatches': 0,
         'semantic_mutants': {}, 'witnesses': {}}
ROOT = None
BASE = None
CANDIDATE = None
SOURCE = None
COMPOSED = None
ENGINE = None
EV = None


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def authenticate(root: Path) -> dict:
    manifest_bytes = (root / 'SOURCE.json').read_bytes()
    if sha(manifest_bytes) != MANIFEST_SHA256:
        raise ValueError('SOURCE.json identity mismatch')
    manifest = json.loads(manifest_bytes)
    if len(manifest['runtime']) != 109:
        raise ValueError('unexpected runtime member count')
    for name, identity in manifest['runtime'].items():
        data = (root / name).read_bytes()
        if len(data) != identity['bytes'] or sha(data) != identity['sha256']:
            raise ValueError('runtime identity mismatch: ' + name)
    return manifest


def module_from_source(source: str, name: str):
    module = types.ModuleType(name)
    module.__file__ = str(ROOT / 'frozen_selected.py')
    exec(compile(source, module.__file__, 'exec'), module.__dict__)
    return module


def fixture(*, now=648, seat=0, shops=(), cash=2000, stock=None,
            inventory=None, configuration=None, params=None):
    e, S = ENGINE, EV.Struct
    cfg = S({k: v.get('default') if isinstance(v, dict) else v
             for k, v in e.specification['configuration'].items()})
    cfg.weedSpawnChance = 0
    cfg.update(configuration or {})
    farms = [e._new_farm(10, cash), e._new_farm(10, cash)]
    market = e._new_market()
    market['inventory'].update(inventory or {})
    if params is not None:
        market['params'] = copy.deepcopy(params)
    e._refresh_prices(market)
    town = {'unlocked_shops': list(shops)}
    state = []
    for player in range(2):
        private = e._new_private()
        if player == seat:
            private['shed'].update(stock or {})
        state.append(S(observation=S(player=player, step=now, day=now // 24,
                                     hour=now % 24, farms=farms, private=private,
                                     market=market, town=town),
                       action={'farmer': ['PASS'], 'hands': [], 'market': []},
                       status='ACTIVE', reward=0))
    return state, S(configuration=cfg, done=False, info={'seed': 17})


def route_for(end, dated_orders):
    route = [{} for _ in range(end + 1)]
    for date, orders in dated_orders.items():
        route[date] = {'farmer': ['PASS'], 'hands': [], 'market': copy.deepcopy(orders)}
    return route


def oracle(state, env, seat, route, end, current_market, stress=0):
    """Read fills from actual before/after state, not a second market simulator.

    Acceptance fixtures use at most one nonempty executable row per callback,
    passive units, and no rival market row. This makes per-row state deltas
    unambiguous. Both complete interpreter seats still execute every callback.
    The optional initial draw reproduces the trace's declared stress world; it
    is not claimed as the timing of a real opponent's hidden orders.
    """
    state, env = copy.deepcopy((state, env))
    now = state[seat].observation.step
    max_orders = max(1, int(env.configuration.maxMarketOrdersPerTurn))
    if stress:
        items = {o[1] for t in range(now, end + 1)
                 for o in (current_market if t == now else route[t].get('market', []))[:max_orders]
                 if o and len(o) > 2 and o[0] == 'BUY_PRODUCT' and o[1] in ('WHEAT', 'FERTILIZER')}
        for item in items:
            state[0].observation.market['inventory'][item] -= stress
        ENGINE._refresh_prices(state[0].observation.market)
    result = {'cash': 0, 'acquisitions': [], 'executed_sales': []}
    for date in range(now, end + 1):
        for row in state:
            row.observation.step = date
            row.observation.day, row.observation.hour = divmod(date, 24)
        orders = current_market if date == now else route[date].get('market', [])
        active = [(i, o) for i, o in enumerate(orders[:max_orders]) if o]
        if len(active) > 1:
            raise ValueError('oracle requires unambiguous one-row fixtures')
        before = copy.deepcopy(state[seat].observation)
        state[seat].action = {'farmer': ['PASS'], 'hands': [], 'market': copy.deepcopy(orders)}
        ENGINE.interpreter(state, env)
        STATS['official_interpreter_calls'] += 1
        after = state[seat].observation
        if active:
            index, order = active[0]
            op = order[0]
            item = order[1] if len(order) > 1 else ''
            if op == 'BUY_PRODUCT' or op == 'BUY_ANIMAL':
                count = after.private['shed'][item] - before.private['shed'][item]
                result['acquisitions'].append(((date, index, op, item), count))
            elif op == 'BUY_SEED':
                count = after.private['seeds'][item] - before.private['seeds'][item]
                result['acquisitions'].append(((date, index, op, item), count))
            elif op == 'HIRE':
                count = after.farms[seat]['hires_today'] - before.farms[seat]['hires_today']
                result['acquisitions'].append(((date, index, op, ''), count))
            elif op == 'SELL' and date > now:
                count = before.private['shed'][item] - after.private['shed'][item]
                cash = after.farms[seat]['money'] - before.farms[seat]['money']
                result['executed_sales'].append((date, item, count, int(cash)))
        result['cash'] = int(after.farms[seat]['money'])
    STATS['oracle_cases'] += 1
    return result, state


def trace(module, state, env, seat, route, end, current_market, stress=0):
    obs = state[seat].observation
    return module._funding_trace(obs, env.configuration, obs.farms[seat], obs.private,
                                 route, obs.step, end, current_market, stress)


def minimum(module, state, env, seat, route, end, stock):
    obs = state[seat].observation
    return module.funded_minimum_now(
        obs, env.configuration, {'market': [['SELL', 'FERTILIZER', stock]]},
        obs.farms[seat], obs.private, route, end,
        {'FERTILIZER': stock}, {'FERTILIZER': stock}, 'FERTILIZER')


class TownFundingTests(unittest.TestCase):
    def compare(self, state, env, seat, route, end, orders, stress=0):
        before = copy.deepcopy((state, env, route, orders))
        expected, final = oracle(state, env, seat, route, end, orders, stress)
        actual = trace(CANDIDATE, state, env, seat, route, end, orders, stress)
        self.assertEqual(actual, expected)
        STATS['candidate_trace_comparisons'] += 1
        if trace(BASE, state, env, seat, route, end, orders, stress) != expected:
            STATS['legacy_trace_mismatches'] += 1
        self.assertEqual((state, env, route, orders), before)
        return expected, final

    def test_01_source_identity_and_idempotence(self):
        self.assertEqual(sha(SOURCE.encode()), BASE_SHA256)
        self.assertEqual(composer.apply(COMPOSED), COMPOSED)
        a, b = composer.span(SOURCE)
        x, y = composer.span(COMPOSED)
        self.assertEqual((SOURCE[:a], SOURCE[b:]), (COMPOSED[:x], COMPOSED[y:]))
        peer = '# unrelated peer note: λ\n' + SOURCE + '\nPEER_SENTINEL = 19\n'
        self.assertEqual(composer.apply(peer), '# unrelated peer note: λ\n' + COMPOSED + '\nPEER_SENTINEL = 19\n')

    def test_02_drift_missing_duplicate_and_decorator_rejected(self):
        for bad in (SOURCE.replace('    buy_items = set()', '    buy_items = set() # drift'),
                    SOURCE.replace('def _funding_trace(', 'def _missing_funding_trace('),
                    SOURCE + '\ndef _funding_trace():\n    return None\n',
                    SOURCE.replace('def _funding_trace(', '@staticmethod\ndef _funding_trace('),
                    COMPOSED.replace('inventory[product] -= amount', 'inventory[product] -= 0')):
            with self.subTest(digest=sha(bad.encode())), self.assertRaises(ValueError):
                composer.apply(bad)

    def test_03_manifest_fail_closed(self):
        authenticate(ROOT)
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'runtime'
            shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns('__pycache__'))
            (root / 'mechanics.py').write_bytes(b'# substituted dependency\n')
            with self.assertRaisesRegex(ValueError, 'runtime identity mismatch'):
                authenticate(root)
            (root / 'mechanics.py').unlink()
            with self.assertRaises(FileNotFoundError):
                authenticate(root)
            (root / 'SOURCE.json').write_bytes(b'{}')
            with self.assertRaisesRegex(ValueError, 'SOURCE.json'):
                authenticate(root)

    def test_04_real_cli_output_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            src, out = Path(d) / 'source.py', Path(d) / 'out.py'
            src.write_bytes(SOURCE.encode())
            command = [sys.executable] + (['-O'] if sys.flags.optimize else []) + [str(Path(composer.__file__).resolve())]
            completed = subprocess.run(command + [str(src), str(out)], capture_output=True, timeout=10)
            self.assertEqual(completed.returncode, 0, completed.stderr.decode())
            self.assertEqual(out.read_bytes(), COMPOSED.encode())
            out.write_bytes(b'precious existing output')
            self.assertNotEqual(subprocess.run(command + [str(src), str(out)], capture_output=True, timeout=10).returncode, 0)
            self.assertEqual(out.read_bytes(), b'precious existing output')
            self.assertNotEqual(subprocess.run(command + [str(src), str(src)], capture_output=True, timeout=10).returncode, 0)
            self.assertEqual(src.read_bytes(), SOURCE.encode())
            src.write_text(SOURCE.replace('    buy_items = set()', '    buy_items = set() # unknown'))
            out.unlink()
            self.assertNotEqual(subprocess.run(command + [str(src), str(out)], capture_output=True, timeout=10).returncode, 0)
            self.assertFalse(out.exists())

    def test_05_nonbuyable_products_have_no_invented_funding_demand(self):
        for seat in range(2):
            for item in ENGINE.PRODUCTS:
                if item in ('WHEAT', 'FERTILIZER'):
                    continue
                state, env = fixture(seat=seat, shops=['YARN_STORE'] * 8, cash=0,
                                     stock={'FERTILIZER': 100},
                                     inventory={'FERTILIZER': 20000, item: 10077})
                end = 656
                route = route_for(end, {end: [['BUY_PRODUCT', item, 1]]})
                old_q, old_cert = minimum(BASE, state, env, seat, route, end, 100)
                new_q, new_cert = minimum(CANDIDATE, state, env, seat, route, end, 100)
                self.assertEqual(new_q, 0)
                self.assertEqual(new_cert['reference_acquisitions'], 0)
                parent_live, _ = self.compare(state, env, seat, route, end, [['SELL', 'FERTILIZER', 100]])
                self.assertEqual(parent_live['acquisitions'][0][1], 0)
                if item == 'WOOL':
                    self.assertEqual(old_q, 88)
                    self.assertEqual(old_cert['reference_acquisitions'], 1)
                    STATS['witnesses'][f'nonbuyable_wool_seat_{seat}'] = {
                        'old_minimum': old_q, 'new_minimum': new_q,
                        'parent_live': parent_live,
                        'old_certificate': old_cert, 'new_certificate': new_cert,
                        'correction': 'WOOL cannot be bought; NOT a town-only preservation witness'}

    def test_06_seventeen_turn_underfunding_both_seats(self):
        for seat in range(2):
            state, env = fixture(seat=seat, shops=['BAKERY'] * 8, cash=0,
                                 stock={'FERTILIZER': 90}, inventory={'FERTILIZER': 20000})
            end = 665
            route = route_for(end, {end: [['BUY_PRODUCT', 'WHEAT', 2]]})
            old_q, old_cert = minimum(BASE, state, env, seat, route, end, 90)
            new_q, new_cert = minimum(CANDIDATE, state, env, seat, route, end, 90)
            self.assertEqual((old_q, new_q), (62, 68))
            self.assertFalse(new_cert['fallback'])
            old_live, _ = oracle(state, env, seat, route, end, [['SELL', 'FERTILIZER', old_q]])
            new_live, _ = self.compare(state, env, seat, route, end, [['SELL', 'FERTILIZER', new_q]])
            parent_live, _ = oracle(state, env, seat, route, end, [['SELL', 'FERTILIZER', 90]])
            self.assertEqual((old_live['acquisitions'][0][1], new_live['acquisitions'][0][1],
                              parent_live['acquisitions'][0][1]), (1, 2, 2))
            STATS['witnesses'][f'seventeen_turn_seat_{seat}'] = {
                'old_minimum': old_q, 'new_minimum': new_q,
                'old_live': old_live, 'new_live': new_live, 'parent_live': parent_live,
                'old_certificate': old_cert, 'new_certificate': new_cert}

    def test_07_all_product_market_town_matrix(self):
        # 9 products x 2 dates x 3 shop sets x 3 price regimes x 2 seats x 2 stresses.
        count = 0
        shop_sets = [[], ['YARN_STORE'] * 8,
                     ['BAKERY', 'PIZZA_SHOP', 'BRUNCH_SPOT', 'YARN_STORE',
                      'ICE_CREAM_SHOP', 'PET_CAFE', 'SMOOTHIE_SHOP', 'FARMERS_MARKET']]
        for item in ENGINE.PRODUCTS:
            for now in (648, 650):
                for shops in shop_sets:
                    for inv in (9987, 10000, 10041):
                        for seat in range(2):
                            for stress in (0, 32):
                                state, env = fixture(now=now, seat=seat, shops=shops,
                                                     stock={item: 4}, inventory={item: inv})
                                end = now + 4
                                route = route_for(end, {
                                    now + 1: [[], ['BUY_PRODUCT', item, 3]],
                                    now + 3: [['SELL', item, 2]], end: [['HIRE']]})
                                with self.subTest(item=item, now=now, shops=shops, inv=inv, seat=seat, stress=stress):
                                    self.compare(state, env, seat, route, end, [['SELL', item, 2]], stress)
                                count += 1
        self.assertEqual(count, 648)
        STATS['matrix_cases'] = count

    def test_08_intervals_are_engine_coerced_and_clamped(self):
        for interval in (0, -2, 1, 2, '3', 2.9):
            for seat in range(2):
                state, env = fixture(seat=seat, shops=['BAKERY', 'YARN_STORE'] * 4,
                                     configuration={'townShopSellInterval': interval,
                                                    'townCenterSellInterval': interval})
                route = route_for(651, {649: [['BUY_PRODUCT', 'WOOL', 2]],
                                       651: [['BUY_PRODUCT', 'WHEAT', 3]]})
                self.compare(state, env, seat, route, 651, [])

    def test_09_market_before_town_and_center_excludes_fertilizer(self):
        for seat in range(2):
            state, env = fixture(seat=seat, shops=['BAKERY'] * 8, stock={'MILK': 10})
            route = route_for(649, {649: [['BUY_PRODUCT', 'FERTILIZER', 3]]})
            expected, _ = self.compare(state, env, seat, route, 649, [['SELL', 'MILK', 3]])
            self.assertEqual(expected['executed_sales'], [])
            # Current market quote uses the observation, not post-town prices.
            one, _ = oracle(state, env, seat, route, 648, [['SELL', 'MILK', 3]])
            self.assertEqual(trace(CANDIDATE, state, env, seat, route, 648, [['SELL', 'MILK', 3]]), one)

    def test_10_floors_clipping_cash_and_raw_slots(self):
        for seat in range(2):
            for cap in (1, 2, 10):
                for cash in (0, 25, 26, 99, 100):
                    state, env = fixture(seat=seat, cash=cash, shops=['BAKERY'] * 8,
                                         stock={'MILK': 2, 'CARROT': 96},
                                         inventory={'MILK': 10076},
                                         configuration={'maxMarketOrdersPerTurn': cap})
                    route = route_for(649, {649: [[], ['BUY_PRODUCT', 'WHEAT', 5]]})
                    self.compare(state, env, seat, route, 649, [['SELL', 'MILK', 4]])

    def test_11_empty_town_legacy_fixture_and_final_interval(self):
        state, env = fixture(now=650, stock={'MILK': 3})
        route = route_for(651, {651: [['BUY_ANIMAL', 'COW', 1]]})
        self.compare(state, env, 0, route, 651, [])
        state[0].observation.pop('town')
        # Historical native unit tests omit town. An absent field means no observed shops.
        self.assertEqual(trace(BASE, state, env, 0, route, 651, []),
                         trace(CANDIDATE, state, env, 0, route, 651, []))
        env.configuration['townShopSellInterval'] = 'invalid'
        self.assertEqual(trace(BASE, state, env, 0, route, 650, []),
                         trace(CANDIDATE, state, env, 0, route, 650, []))
        with self.assertRaises(ValueError):
            trace(CANDIDATE, state, env, 0, route, 651, [])

    def test_12_unknown_dawn_fails_into_baseline_sale(self):
        state, env = fixture(now=671, stock={'FERTILIZER': 10})
        route = route_for(672, {672: [['BUY_PRODUCT', 'WHEAT', 1]]})
        before = copy.deepcopy((state, env, route))
        with self.assertRaisesRegex(ValueError, 'dawn'):
            trace(CANDIDATE, state, env, 0, route, 672, [])
        quantity, certificate = minimum(CANDIDATE, state, env, 0, route, 672, 10)
        self.assertEqual(quantity, 10)
        self.assertTrue(certificate['fallback'])
        self.assertIn('dawn', certificate['error'])
        self.assertEqual((state, env, route), before)

    def test_13_invalid_shop_fails_without_mutation(self):
        state, env = fixture(shops=['UNKNOWN'], stock={'FERTILIZER': 4})
        route = route_for(649, {649: [['BUY_PRODUCT', 'WHEAT', 2]]})
        before = copy.deepcopy((state, env, route))
        quantity, certificate = minimum(CANDIDATE, state, env, 0, route, 649, 4)
        self.assertEqual(quantity, 4)
        self.assertTrue(certificate['fallback'])
        self.assertIn('KeyError', certificate['error'])
        self.assertEqual((state, env, route), before)

    def test_14_future_sale_receipts_and_prefix_cut(self):
        state, env = fixture(shops=['YARN_STORE'] * 8, stock={'WOOL': 3})
        route = route_for(652, {649: [['SELL', 'WOOL', 2]], 652: [['BUY_ANIMAL', 'COW', 1]]})
        expected, _ = self.compare(state, env, 0, route, 652, [])
        self.assertEqual(CANDIDATE._funding_prefix_end(expected, 648, 652), (648, 649))
        self.assertGreater(expected['executed_sales'][0][3],
                           trace(BASE, state, env, 0, route, 652, [])['executed_sales'][0][3])

    def test_15_native_funded_prefix_regressions(self):
        path = ROOT / 'checks/test_funded_prefix.py'
        spec = importlib.util.spec_from_file_location('town_inherited_prefix', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.fs = CANDIDATE
        suite = unittest.defaultTestLoader.loadTestsFromModule(module)
        result = unittest.TestResult()
        suite.run(result)
        self.assertEqual(result.testsRun, 8)
        self.assertFalse(result.errors + result.failures + result.skipped)
        STATS['inherited_prefix_tests'] = result.testsRun

    def test_16_semantic_mutants_are_assertion_rejected(self):
        # Each mutant is executable and evaluated against fresh full-engine receipts.
        # Exceptions are infrastructure errors, never credited as semantic kills.
        faults = {
            'omit_town': COMPOSED.replace(composer.TOWN, ''),
            'invent_nonbuyable_products': COMPOSED.replace(composer.BUY_GUARD, ''),
            'stress_invalid_product': COMPOSED.replace(composer.BUY_SCAN_FIXED, composer.BUY_SCAN),
            'deduplicate_shops': COMPOSED.replace("obs.get('town', {}).get('unlocked_shops', [])", "set(obs.get('town', {}).get('unlocked_shops', []))"),
            'omit_center': COMPOSED.replace('for product in m.TOWN_CENTER_PRODUCTS:', 'for product in ():'),
            'consume_fertilizer': COMPOSED.replace('for product in m.TOWN_CENTER_PRODUCTS:', 'for product in m.PRODUCTS:'),
            'miss_current_town': COMPOSED.replace('if t < end:', 'if now < t < end:'),
            'shift_shop_clock': COMPOSED.replace('if t % shop_interval == 0:', 'if (t + 1) % shop_interval == 0:'),
            'single_product_multiplier': COMPOSED.replace('amount = 2 if len(products) == 1 else 1', 'amount = 1'),
        }
        cases = []
        for item, inv, shops in [('WOOL', 10077, ['YARN_STORE'] * 8),
                                  ('WHEAT', 10000, ['BAKERY'] * 8),
                                  ('FERTILIZER', 10000, []), ('MILK', 10030, [])]:
            state, env = fixture(stock={item: 3}, inventory={item: inv}, shops=shops)
            route = route_for(653, {649: [['BUY_PRODUCT', item, 3]], 653: [['SELL', item, 2]]})
            expected, _ = oracle(state, env, 0, route, 653, [['SELL', item, 1]], 32)
            cases.append((state, env, route, [['SELL', item, 1]], expected))
        for name, source in faults.items():
            self.assertNotEqual(source, COMPOSED)
            mutated = module_from_source(source, 'broken_' + name)
            failures = 0
            for state, env, route, orders, expected in cases:
                actual = trace(mutated, state, env, 0, route, 653, orders, 32)
                try:
                    self.assertEqual(actual, expected)
                except AssertionError:
                    failures += 1
            self.assertGreater(failures, 0, name)
            STATS['semantic_mutants'][name] = {'assertion_failures': failures, 'errors': 0}


def initialize(root: Path):
    global ROOT, BASE, CANDIDATE, SOURCE, COMPOSED, ENGINE, EV
    ROOT = root.resolve()
    authenticate(ROOT)  # No native code imports before custody succeeds.
    sys.path.insert(0, str(ROOT))
    SOURCE = (ROOT / 'frozen_selected.py').read_bytes().decode()
    COMPOSED = composer.apply(SOURCE)
    BASE = module_from_source(SOURCE, 'town_funding_baseline')
    CANDIDATE = module_from_source(COMPOSED, 'town_funding_candidate')
    path = ROOT / 'checks/reference/evaluator/evaluate.py'
    spec = importlib.util.spec_from_file_location('town_official_evaluator', path)
    EV = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(EV)
    ENGINE, identities = EV.get_engine(ROOT / 'checks/reference/engine',
                                      ROOT / 'checks/reference/evaluator/loader.py')
    STATS['official_source_identities'] = identities
    STATS['manifest_sha256'] = MANIFEST_SHA256
    STATS['runtime_members_authenticated'] = 109
    STATS['candidate_sha256'] = sha(COMPOSED.encode())
    STATS['base_sha256'] = sha(SOURCE.encode())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    initialize(args.runtime)
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(TownFundingTests))
    authenticate(ROOT)
    report = dict(STATS, python=sys.version, optimized=sys.flags.optimize,
                  tests_run=result.testsRun, failures=len(result.failures),
                  errors=len(result.errors), skips=len(result.skipped),
                  success=result.wasSuccessful() and not result.skipped)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    if not report['success']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
