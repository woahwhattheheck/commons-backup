# SPDX-License-Identifier: Apache-2.0
"""Opt-in product funding against exact existing official market source.

No episode initialization or game seeds. The supplied old source is used only
for default-API differential comparisons, not for replaying old market panels.
"""
from __future__ import annotations
import argparse
import ast
from copy import deepcopy
import gzip
import hashlib
import importlib.util
import io
import itertools
import json
import platform
from pathlib import Path
import sys
import time
from types import ModuleType, SimpleNamespace
import unittest

from seed_funding import certify_seed_funding, select_seed_queue, select_public_seed_queue

ENGINE_SHA = 'bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e'
ORIGINAL_SHA = 'd40225f74f37c564dd5e099637defa9dfcf42941fddc5503b60f18fbd2de2302'
K = OLD = None
PAIRS, DEFAULTS = [], []
MARKET_CALLS = 0


def load_engine(path):
    data = Path(path).read_bytes()
    if hashlib.sha256(data).hexdigest() != ENGINE_SHA:
        raise ValueError('engine source differs from this discriminator target')
    tree = ast.parse(data, filename=str(path))
    tree.body = [n for n in tree.body if not (
        isinstance(n, ast.ImportFrom) and n.module == 'kaggle_environments.utils')]
    # Only an initialization import is omitted. Every market function and
    # constant remains unmodified; initialization and RNG are never invoked.
    module = ModuleType('cedar_product_market'); module.__file__ = str(Path(path).resolve())
    exec(compile(tree, str(path), 'exec'), module.__dict__)
    return module


def load_original(path):
    data = Path(path).read_bytes()
    if hashlib.sha256(data).hexdigest() != ORIGINAL_SHA:
        raise ValueError('original certificate does not match PR10000')
    spec = importlib.util.spec_from_file_location('cedar_old_funding', path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def action(orders):
    return {'farmer': ['PASS'], 'hands': [], 'market': deepcopy(orders)}


def fixture(money=10000, seat=0, stock=0, hires=12, inventory=10000):
    def farm(cash, hired):
        tiles = [[None if K._quadrant_of(x, y, 10) == 'NW' else 'LOCKED'
                  for x in range(10)] for y in range(10)]
        return {'money': cash, 'hires_today': hired,
                'farmer': list(K._default_spawn(10)),
                'hands': [list(K._default_spawn(10)) for _ in range(hired)],
                'unlocked_quadrants': ['NW'], 'tiles': tiles}
    def private(hired, count):
        return {'seeds': {}, 'shed': {'WHEAT': count},
                'inventories': [{} for _ in range(hired + 1)]}
    farms = [farm(10**9, 2), farm(10**9, 2)]
    privates = [private(2, 0), private(2, 0)]
    farms[seat], privates[seat] = farm(money, hires), private(hires, stock)
    market = {'inventory': {p: inventory for p in K.PRODUCTS}, 'prices': {}}
    K._refresh_prices(market)
    return {'farms': farms, 'privates': privates, 'market': market, 'seat': seat}


def observation(state):
    return {'player': state['seat'], 'farms': deepcopy(state['farms']),
            'private': deepcopy(state['privates'][state['seat']]),
            'market': deepcopy(state['market'])}


def execute(initial, own, rival, config=None, instrument=True):
    global MARKET_CALLS
    data = deepcopy(initial); seat = data['seat']
    actors = [SimpleNamespace(observation=SimpleNamespace(
        farms=data['farms'], market=data['market'], private=data['privates'][i]),
        action=deepcopy(own if i == seat else rival)) for i in (0, 1)]
    commits = []
    original_commit, original_parse = K._commit_unit, K._parse_order
    slots = {id(o): i for i, o in enumerate(actors[seat].action['market'])}
    current = {'slot': None}
    def parse(order):
        if id(order) in slots:
            current['slot'] = slots[id(order)]
        return original_parse(order)
    def commit(op, item, price, farm, private, market, shed_capacity=100):
        success = original_commit(op, item, price, farm, private, market, shed_capacity)
        if farm is data['farms'][seat] and op == 'BUY_PRODUCT':
            commits.append({'slot': current['slot'], 'product': item,
                            'price': price, 'succeeded': success})
        return success
    if instrument:
        K._parse_order, K._commit_unit = parse, commit
    try:
        K._process_market(actors, SimpleNamespace(configuration=dict(config or {})))
        MARKET_CALLS += 1
    finally:
        K._commit_unit, K._parse_order = original_commit, original_parse
    return data, commits


def without(mapping, key):
    return {k: v for k, v in mapping.items() if k != key}


class ProductFundingTests(unittest.TestCase):
    def pair(self, name, initial, base, proposed, rival=None, cfg=None):
        rival = action([]) if rival is None else rival
        original_inputs = deepcopy((initial, base, proposed, rival, cfg))
        chosen, report = select_public_seed_queue(K, observation(initial), base, proposed, cfg)
        self.assertEqual(report['status'], 'certified', report)
        self.assertEqual(chosen, proposed)
        old, old_buys = execute(initial, base, rival, cfg)
        new, new_buys = execute(initial, proposed, rival, cfg)
        seat, other = initial['seat'], 1-initial['seat']
        self.assertEqual(without(old['farms'][seat], 'money'), without(new['farms'][seat], 'money'))
        self.assertEqual(without(old['privates'][seat], 'seeds'), without(new['privates'][seat], 'seeds'))
        self.assertEqual(old['farms'][other], new['farms'][other])
        self.assertEqual(old['privates'][other], new['privates'][other])
        self.assertEqual(old['market'], new['market'])
        self.assertEqual(old_buys, new_buys)
        delta = new['farms'][seat]['money'] - old['farms'][seat]['money']
        self.assertEqual(delta, report['paired_current_market_cash_delta'])
        bounds = {b['slot']: b for b in report.get('public_product_bounds', [])}
        for buy in old_buys:
            self.assertLessEqual(buy['price'], bounds[buy['slot']]['quoted_unit_price_upper_bound'])
        self.assertEqual(original_inputs, (initial, base, proposed, rival, cfg))
        PAIRS.append({'case': name, 'initial': initial, 'baseline_action': base,
                      'proposed_action': proposed, 'rival_action': rival, 'configuration': cfg or {},
                      'baseline_result': old, 'proposed_result': new, 'product_commits': old_buys,
                      'certificate': report, 'non_seed_state_equal': True, 'cash_delta': delta})
        return report

    def test_funded_product_then_hire_both_seats(self):
        for seat in (0, 1):
            base = action([['BUY_SEED', 'WHEAT', 10], ['BUY_PRODUCT', 'WHEAT', 3], ['HIRE']])
            proposed = deepcopy(base); proposed['market'][0][2] = 3
            report = self.pair('funded-product-hire', fixture(seat=seat), base, proposed)
            self.assertEqual(report['paired_current_market_cash_delta'], 70)
            self.assertEqual(report['original_fixed_cost_upper_bound'], 333)
            self.assertEqual(report['original_total_cost_upper_bound'],
                             333 + report['product_cost_upper_bound'])

    def test_paired_price_grid(self):
        rivals = [[], [['BUY_PRODUCT', 'WHEAT', 100], ['BUY_PRODUCT', 'FERTILIZER', 100]],
                  [['BUY_PRODUCT', 'FERTILIZER', 100], ['BUY_PRODUCT', 'WHEAT', 100]],
                  [[], ['BUY_PRODUCT', 'WHEAT', 100]],
                  [[], ['BUY_PRODUCT', 'FERTILIZER', 100]],
                  [['SELL', 'WHEAT', 100], ['SELL', 'FERTILIZER', 100]],
                  [['BUY_PRODUCT', 'WHEAT', 100], ['SELL', 'WHEAT', 100], ['BUY_PRODUCT', 'WHEAT', 100]]]
        for item, seat, inv, orders in itertools.product(('WHEAT', 'FERTILIZER'), (0, 1),
                                                        (0, 9900, 10300), rivals):
            initial = fixture(money=10**9, seat=seat, inventory=inv)
            initial['privates'][1-seat]['shed'] = {'WHEAT': 20, 'FERTILIZER': 20}
            base = action([['BUY_SEED', 'CARROT', 12], ['BUY_PRODUCT', item, 4], ['HIRE']])
            proposed = deepcopy(base); proposed['market'][0][2] = 5
            self.pair(f'paired-{item}-{inv}', initial, base, proposed, action(orders))

    def test_negative_inventory_bound_is_not_zero_clamped(self):
        initial = fixture(money=4300, inventory=0)
        base = action([['BUY_SEED', 'WHEAT', 10], ['BUY_PRODUCT', 'FERTILIZER', 2]])
        proposed = deepcopy(base); proposed['market'][0] = []
        rival = action([['BUY_PRODUCT', 'FERTILIZER', 10]])
        cfg = {'shedCapacity': 10}
        chosen, report = select_public_seed_queue(K, observation(initial), base, proposed, cfg)
        self.assertEqual(report['status'], 'not_certified')
        self.assertEqual(chosen, base)
        self.assertEqual(report['public_product_bounds'][0]['quote_inventory_lower_bound'], -22)
        self.assertGreater(report['original_total_cost_upper_bound'], 4300)
        # Price(0) would incorrectly declare all original purchases funded.
        self.assertEqual(100 + 2*K.market_price('FERTILIZER', 0), 4300)
        old, commits = execute(initial, base, rival, cfg)
        new, _ = execute(initial, proposed, rival, cfg)
        self.assertEqual(old['privates'][0]['shed'].get('FERTILIZER'), 1)
        self.assertEqual(new['privates'][0]['shed'].get('FERTILIZER'), 2)
        PAIRS.append({'case': 'price-at-zero-negative', 'initial': initial,
                      'baseline_action': base, 'proposed_action': proposed, 'rival_action': rival,
                      'configuration': cfg, 'baseline_result': old, 'proposed_result': new,
                      'product_commits': commits, 'certificate': report,
                      'non_seed_state_equal': False, 'returned_original': True})

    def test_multiple_product_slots_and_capacity_reuse(self):
        base = action([['BUY_SEED', 'WHEAT', 10], ['BUY_PRODUCT', 'WHEAT', 100],
                       ['SELL', 'WHEAT', 100], ['BUY_PRODUCT', 'WHEAT', 100],
                       ['SELL', 'WHEAT', 100], ['BUY_PRODUCT', 'FERTILIZER', 2]])
        proposed = deepcopy(base); proposed['market'][0][2] = 3
        rival = action([['BUY_PRODUCT', 'WHEAT', 100], ['SELL', 'WHEAT', 100],
                        ['BUY_PRODUCT', 'WHEAT', 100], ['SELL', 'WHEAT', 100],
                        ['BUY_PRODUCT', 'WHEAT', 100]])
        for seat in (0, 1):
            r = self.pair('multiple-slots', fixture(money=10**9, seat=seat), base, proposed, rival)
            self.assertEqual(r['public_product_bounds'][1]['own_purchase_units_bound_through_slot'], 200)
            self.assertEqual(r['public_product_bounds'][1]['rival_purchase_units_bound_through_slot'], 400)

    def test_capacity_clips_requested_quantity(self):
        base = action([['BUY_SEED', 'WHEAT', 10], ['BUY_PRODUCT', 'WHEAT', 99998]])
        proposed = deepcopy(base); proposed['market'][0][2] = 3
        for seat in (0, 1):
            r = self.pair('capacity-clipped', fixture(seat=seat, stock=95), base, proposed)
            self.assertEqual(r['public_product_bounds'][0]['quantity_upper_bound'], 100)
            self.assertEqual(sum(p['succeeded'] for p in PAIRS[-1]['product_commits']), 5)

    def test_all_supported_price_shapes(self):
        for shape in ('linear', 'sq', 'sqrt', 'log', 'log10', 'hinge'):
            initial = fixture(money=10**9, inventory=-50)
            params = deepcopy(K.MARKET_PARAMS)
            params['FERTILIZER'].update(below_func=shape, above_func=shape, base=8,
                                         I0=25, T=3, below_target=0.4, above_target=0.2)
            initial['market']['params'] = params; K._refresh_prices(initial['market'])
            base = action([['BUY_SEED', 'WHEAT', 10], ['BUY_PRODUCT', 'FERTILIZER', 3]])
            proposed = deepcopy(base); proposed['market'][0][2] = 3
            self.pair(f'shape-{shape}', initial, base, proposed,
                      action([['BUY_PRODUCT', 'FERTILIZER', 100]]))

    def test_truncated_product_requires_no_market_input(self):
        base = action([['BUY_SEED', 'WHEAT', 10], ['BUY_PRODUCT', 'WHEAT', 8]])
        proposed = deepcopy(base); proposed['market'][0][2] = 3
        obs = observation(fixture()); del obs['market']
        chosen, r = select_public_seed_queue(K, obs, base, proposed, {'maxMarketOrdersPerTurn': 1})
        self.assertEqual(r['status'], 'certified'); self.assertEqual(chosen, proposed)
        self.assertNotIn('public_product_bounds', r)

    def test_underfunded_hire_still_preserves_fallback(self):
        base = action([['BUY_SEED', 'WHEAT', 10], ['HIRE']])
        proposed = deepcopy(base); proposed['market'][0] = []
        chosen, r = select_public_seed_queue(K, observation(fixture(money=300)), base, proposed)
        self.assertEqual(chosen, base); self.assertEqual(r['status'], 'not_certified')

    def test_no_sale_receipts_used_as_funding(self):
        base = action([['BUY_SEED', 'WHEAT', 10], ['SELL', 'WHEAT', 20],
                       ['BUY_PRODUCT', 'WHEAT', 3], ['HIRE']])
        proposed = deepcopy(base); proposed['market'][0] = []
        chosen, r = select_public_seed_queue(K, observation(fixture(money=100, stock=20)), base, proposed)
        self.assertEqual(chosen, base); self.assertEqual(r['status'], 'not_certified')
        self.assertGreater(r['original_total_cost_upper_bound'], r['observed_cash'])

    def test_nonmonotone_or_unknown_parameters_preserve_original(self):
        for key, value in (('below_target', -0.2), ('above_target', -0.2), ('base', -5),
                           ('T', 0), ('T', -1), ('below_func', 'unrecognized'),
                           ('above_func', 'unrecognized'), ('base', float('nan')),
                           ('I0', float('inf')), ('below_target', True)):
            initial = fixture(); params = deepcopy(K.MARKET_PARAMS)
            params['WHEAT'][key] = value; initial['market']['params'] = params
            base = action([['BUY_SEED', 'WHEAT', 10], ['BUY_PRODUCT', 'WHEAT', 1]])
            proposed = deepcopy(base); proposed['market'][0] = []
            chosen, report = select_public_seed_queue(K, observation(initial), base, proposed)
            self.assertEqual(chosen, base); self.assertEqual(report['status'], 'not_certified')

    def test_missing_inventory_and_malformed_bounds_inputs(self):
        base = action([['BUY_SEED', 'WHEAT', 10], ['BUY_PRODUCT', 'WHEAT', 1]])
        proposed = deepcopy(base); proposed['market'][0] = []
        obs = observation(fixture()); del obs['market']['inventory']['WHEAT']
        self.assertEqual(select_public_seed_queue(K, obs, base, proposed)[1]['status'], 'not_certified')
        for cap in (0, -1, True, '100', 1.5):
            chosen, report = select_public_seed_queue(K, observation(fixture()), base, proposed,
                                                       {'shedCapacity': cap})
            self.assertEqual(chosen, base); self.assertEqual(report['status'], 'not_certified')
        for inv in (True, 2.3, '10000'):
            obs = observation(fixture()); obs['market']['inventory']['WHEAT'] = inv
            self.assertEqual(select_public_seed_queue(K, obs, base, proposed)[1]['status'], 'not_certified')

    def test_unsupported_purchase_and_invalid_quantities(self):
        for item, quantity in (('MILK', 1), ('WHEAT', -1), ('WHEAT', '3'), ('WHEAT', True),
                               ('WHEAT', 3.5), ('WHEAT', 99999)):
            base = action([['BUY_SEED', 'WHEAT', 10], ['BUY_PRODUCT', item, quantity]])
            proposed = deepcopy(base); proposed['market'][0] = []
            chosen, report = select_public_seed_queue(K, observation(fixture()), base, proposed)
            self.assertEqual(chosen, base); self.assertEqual(report['status'], 'not_certified')

    def test_zero_product_and_no_seed_edit(self):
        base = action([['BUY_SEED', 'WHEAT', 10], ['BUY_PRODUCT', 'WHEAT', 0]])
        obs = observation(fixture()); del obs['market']
        proposed = deepcopy(base); proposed['market'][0] = []
        self.assertEqual(select_public_seed_queue(K, obs, base, proposed)[1]['status'], 'certified')
        self.assertEqual(select_public_seed_queue(K, obs, base, base)[1]['status'], 'no_seed_edit')

    def test_other_changes_are_never_seed_certified(self):
        base = action([['BUY_SEED', 'WHEAT', 10], ['BUY_PRODUCT', 'WHEAT', 2]])
        for changed in ('worker', 'product', 'quantity', 'slots', 'seed_increase'):
            proposed = deepcopy(base); proposed['market'][0][2] = 3
            if changed == 'worker': proposed['farmer'] = ['NORTH']
            elif changed == 'product': proposed['market'][1][1] = 'FERTILIZER'
            elif changed == 'quantity': proposed['market'][1][2] = 1
            elif changed == 'slots': proposed['market'].append([])
            else: proposed['market'][0][2] = 11
            self.assertEqual(select_public_seed_queue(K, observation(fixture()), base, proposed)[1]['status'],
                             'not_certified')

    def test_default_api_matches_old_source_exactly(self):
        tails = [[], [['HIRE']], [['HIRE'], ['HIRE']], [['BUY_LAND']],
                 [['BUY_ANIMAL', 'COW', 2]], [['SELL', 'WHEAT', 8], ['HIRE']],
                 [['BUY_PRODUCT', 'WHEAT', 2]], [['BUY_PRODUCT', 'FERTILIZER', 2]],
                 [['BUY_PRODUCT', 'WHEAT', 0]], [['BUY_SEED', 'CARROT', 3], ['HIRE']]]
        for money, seat, tail in itertools.product((0, 200, 1000, 10000), (0, 1), tails):
            obs = observation(fixture(money=money, seat=seat))
            base = action([['BUY_SEED', 'WHEAT', 10], *tail])
            proposed = deepcopy(base); proposed['market'][0][2] = 3
            for cfg in ({}, {'maxMarketOrdersPerTurn': 1}, {'farmHandCostMult': 3}):
                before = OLD.select_seed_queue(K, obs, base, proposed, cfg)
                after = select_seed_queue(K, obs, base, proposed, cfg)
                self.assertEqual(before, after)
                DEFAULTS.append({'money': money, 'seat': seat, 'tail': tail, 'config': cfg,
                                 'action_and_report_equal': True})

    def test_detached_outputs_and_explicit_fallback(self):
        base = action([['BUY_SEED', 'WHEAT', 10], ['BUY_PRODUCT', 'WHEAT', 2]])
        proposed = deepcopy(base); proposed['market'][0][2] = 3
        chosen, _ = select_public_seed_queue(K, observation(fixture()), base, proposed)
        chosen['market'][0][2] = 99; self.assertEqual(proposed['market'][0][2], 3)
        fallback = action([['PASS']])
        chosen, _ = select_seed_queue(K, observation(fixture(money=0)), base, proposed,
                                      fallback_action=fallback, public_product_bounds=True)
        self.assertEqual(chosen, fallback)
        chosen['market'].append([]); self.assertEqual(fallback['market'], [['PASS']])

    def test_instrumentation_matches_unmodified_market_call(self):
        initial = fixture(money=100000, seat=1, inventory=-20)
        base = action([['BUY_SEED', 'WHEAT', 10], ['BUY_PRODUCT', 'WHEAT', 6]])
        rival = action([['BUY_PRODUCT', 'WHEAT', 10]])
        self.assertEqual(execute(initial, base, rival, instrument=True)[0],
                         execute(initial, base, rival, instrument=False)[0])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine-source', type=Path, required=True)
    parser.add_argument('--original-source', type=Path, required=True)
    parser.add_argument('--result', type=Path, required=True)
    args = parser.parse_args()
    K = load_engine(args.engine_source); OLD = load_original(args.original_source)
    start = time.perf_counter()
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(ProductFundingTests))
    report = {'schema': 'cedar-public-product-funding-v1', 'engine_sha256': ENGINE_SHA,
              'original_sha256': ORIGINAL_SHA,
              'runtime_sha256': hashlib.sha256(Path(__file__).with_name('seed_funding.py').read_bytes()).hexdigest(),
              'test_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'python': sys.version, 'platform': platform.platform(),
              'tests_run': result.testsRun, 'failure_count': len(result.failures),
              'error_count': len(result.errors), 'failures': result.failures, 'errors': result.errors,
              'elapsed_s': time.perf_counter()-start, 'market_calls': MARKET_CALLS,
              'paired_cases': len(PAIRS), 'certified_pairs': sum(p.get('non_seed_state_equal', False) for p in PAIRS),
              'default_comparisons': len(DEFAULTS), 'full_games': 0, 'game_seeds': [],
              'pairs': PAIRS, 'default_results': DEFAULTS}
    args.result.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(report, sort_keys=True, indent=2, default=str)+'\n').encode()
    if args.result.suffix == '.gz':
        args.result.write_bytes(gzip.compress(data, mtime=0))
    else:
        args.result.write_bytes(data)
    print(json.dumps({k:v for k,v in report.items() if k not in ('pairs','default_results','failures','errors')}, indent=2))
    sys.exit(0 if result.wasSuccessful() else 1)
