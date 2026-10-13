"""Offline checks using the existing pinned engine and standalone mechanics."""
from __future__ import annotations
import argparse
import ast
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
import unittest
from concurrent.futures import ThreadPoolExecutor

from guard import SeedExecutionGuard, Struct
import market_kernel

HERE = Path(__file__).resolve().parent
ENGINE = MECHANICS = None
ENGINE_CALLS = 0


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def fixture(seat=0, cash=233, hires=12):
    farms = [ENGINE._new_farm(10, 1000) for _ in range(2)]
    farm = farms[seat]
    farm['money'], farm['hires_today'] = cash, hires
    farm['hands'] = [[0, 0] for _ in range(hires)]
    private = ENGINE._new_private()
    private['inventories'] = [{} for _ in range(hires+1)]
    obs = {'player': seat, 'step': 17, 'farms': farms,
           'private': deepcopy(private), 'market': ENGINE._new_market()}
    post = {'farm': deepcopy(farm), 'private': private}
    cfg = {'boardSize': 10, 'maxMarketOrdersPerTurn': 10,
           'farmHandCostMult': 1, 'shedCapacity': 100}
    return obs, cfg, post


def scenario(name='rival-pass', orders=None, shed=None, cash=1000):
    return {'name': name, 'rival_market': orders or [],
            'rival_shed_assumption': shed or {}, 'rival_cash_assumption': cash}


def actions(tail, n=9):
    a = {'farmer': ['PASS'], 'hands': [], 'market': [['BUY_SEED', 'WHEAT', n]] + tail}
    b = deepcopy(a)
    b['market'][0][2] = 0
    return a, b


class GuardTests(unittest.TestCase):
    def run_guard(self, seat, cash, hires, tail, *, scenarios=None):
        obs, cfg, post = fixture(seat, cash, hires)
        a, b = actions(tail)
        guard = SeedExecutionGuard(MECHANICS)
        result = guard.transform(obs, cfg, a, b, post_units=post,
                                 scenarios=scenarios or [scenario()])
        return guard, result, a, b

    def test_new_hire_rejected_both_seats(self):
        for seat in (0, 1):
            g, result, a, _ = self.run_guard(seat, 233, 12, [['HIRE']])
            self.assertEqual(result, a)
            row = g.last_report['scenarios'][0]
            self.assertEqual((row['baseline_cash'], row['proposal_cash']), (143, 0))
            self.assertEqual(g.last_report['status'], 'fallback_changed_execution')

    def test_already_funded_hire_keeps_saving(self):
        for seat in (0, 1):
            g, result, _, b = self.run_guard(seat, 1000, 12, [['HIRE']])
            self.assertEqual(result, b)
            self.assertEqual(g.last_report['scenarios'][0]['cash_delta'], 90)

    def test_new_land_rejected(self):
        for seat in (0, 1):
            _, result, a, _ = self.run_guard(seat, 1000, 0, [['BUY_LAND']])
            self.assertEqual(result, a)

    def test_already_funded_land_preserved(self):
        for seat in (0, 1):
            _, result, _, b = self.run_guard(seat, 1100, 0, [['BUY_LAND']])
            self.assertEqual(result, b)

    def test_partial_product_buy_rejected(self):
        for seat in (0, 1):
            g, result, a, _ = self.run_guard(seat, 90, 0, [['BUY_PRODUCT', 'WHEAT', 5]])
            self.assertEqual(result, a)
            self.assertTrue(g.last_report['scenarios'][0]['mismatches'])

    def test_animal_fill_changes_rejected(self):
        for seat in (0, 1):
            _, result, a, _ = self.run_guard(seat, 400, 0, [['BUY_ANIMAL', 'COW', 1]])
            self.assertEqual(result, a)
            _, result, _, b = self.run_guard(seat, 500, 0, [['BUY_ANIMAL', 'COW', 1]])
            self.assertEqual(result, b)

    def test_repeated_hires_preserve_fibonacci_sequence(self):
        for seat in (0, 1):
            _, result, a, _ = self.run_guard(seat, 610, 12, [['HIRE'], ['HIRE']])
            self.assertEqual(result, a)
            _, result, _, b = self.run_guard(seat, 1000, 12, [['HIRE'], ['HIRE']])
            self.assertEqual(result, b)

    def test_sell_funded_action_preserved(self):
        for seat in (0, 1):
            obs, cfg, post = fixture(seat, 100, 0)
            post['private']['shed']['WOOL'] = 2
            a, b = actions([['SELL', 'WOOL', 2], ['BUY_ANIMAL', 'GOOSE', 1]])
            g = SeedExecutionGuard(MECHANICS)
            self.assertEqual(g.transform(obs, cfg, a, b, post_units=post,
                             scenarios=[scenario()]), b)
            self.assertEqual(g.last_report['scenarios'][0]['cash_delta'], 90)

    def test_all_supplied_scenarios_required(self):
        for seat in (0, 1):
            obs, cfg, post = fixture(seat, 32, 0)
            cfg['shedCapacity'] = 400
            a, b = actions([['BUY_PRODUCT', 'WHEAT', 1]], n=1)
            supply = scenario('supply', [['SELL', 'WHEAT', 300]], {'WHEAT': 300})
            g = SeedExecutionGuard(MECHANICS)
            self.assertEqual(g.transform(obs, cfg, a, b, post_units=post, scenarios=[supply]), b)
            self.assertEqual(g.transform(obs, cfg, a, b, post_units=post,
                             scenarios=[supply, scenario()]), a)
            self.assertEqual(len(g.last_report['scenarios']), 2)

    def test_full_shed_buy_does_not_invent_fill(self):
        obs, cfg, post = fixture(cash=400, hires=0)
        post['private']['shed']['WHEAT'] = 100
        a, b = actions([['BUY_ANIMAL', 'COW', 1], ['BUY_PRODUCT', 'WHEAT', 2]])
        g = SeedExecutionGuard(MECHANICS)
        self.assertEqual(g.transform(obs, cfg, a, b, post_units=post,
                                     scenarios=[scenario()]), b)

    def test_missing_empty_and_duplicate_scenarios_fall_back(self):
        obs, cfg, post = fixture()
        a, b = actions([])
        g = SeedExecutionGuard(MECHANICS)
        for cases in (None, [], [scenario(), scenario()], [{'name': 'incomplete'}]):
            self.assertEqual(g.transform(obs, cfg, a, b, post_units=post, scenarios=cases), a)
            self.assertEqual(g.last_report['status'], 'fallback_unknown')

    def test_shape_and_unit_changes_fall_back(self):
        obs, cfg, post = fixture()
        a, good = actions([['HIRE']])
        g = SeedExecutionGuard(MECHANICS)
        changes = []
        for queue in ([['HIRE']], [['BUY_SEED', 'WHEAT', 10], ['HIRE']],
                      [['PASS'], ['PASS']], [['BUY_SEED', 'CARROT', 1], ['HIRE']],
                      [['BUY_SEED', 'WHEAT', -1], ['HIRE']]):
            b = deepcopy(good); b['market'] = queue; changes.append(b)
        b = deepcopy(good); b['farmer'] = ['PLANT', 'WHEAT']; changes.append(b)
        for b in changes:
            self.assertEqual(g.transform(obs, cfg, a, b, post_units=post,
                                         scenarios=[scenario()]), a)
            self.assertEqual(g.last_report['status'], 'fallback_unknown')

    def test_noop_seed_slot_is_not_removed(self):
        obs, cfg, post = fixture(cash=1000, hires=0)
        a, b = actions([['HIRE']]); b['market'][0] = ['PASS']
        g = SeedExecutionGuard(MECHANICS)
        self.assertEqual(g.transform(obs, cfg, a, b, post_units=post,
                                     scenarios=[scenario()]), b)
        self.assertEqual(len(b['market']), 2)

    def test_order_limit_keeps_original_slot_semantics(self):
        obs, cfg, post = fixture()
        cfg['maxMarketOrdersPerTurn'] = 1
        a, b = actions([['HIRE']])
        g = SeedExecutionGuard(MECHANICS)
        self.assertEqual(g.transform(obs, cfg, a, b, post_units=post,
                                     scenarios=[scenario()]), b)
        self.assertEqual(g.last_report['scenarios'][0]['cash_delta'], 90)

    def test_input_and_return_nonmutation(self):
        obs, cfg, post = fixture(cash=1000)
        a, b = actions([['HIRE']]); cases = [scenario()]
        before = deepcopy((obs, cfg, post, a, b, cases))
        g = SeedExecutionGuard(MECHANICS)
        result = g.transform(obs, cfg, a, b, post_units=post, scenarios=cases)
        result['market'][0][2] = 123
        self.assertEqual((obs, cfg, post, a, b, cases), before)

    def test_unknown_cash_and_bad_shed_are_not_private_observations(self):
        obs, cfg, post = fixture()
        a, b = actions([]); g = SeedExecutionGuard(MECHANICS)
        cases = [scenario(cash=float('nan')), scenario(cash=-1),
                 scenario(shed={'WHEAT': -1}), scenario(shed={'unknown': 1})]
        for case in cases:
            self.assertEqual(g.transform(obs, cfg, a, b, post_units=post, scenarios=[case]), a)
            self.assertEqual(g.last_report['status'], 'fallback_unknown')

    def test_bounded_projection_falls_back_without_large_market_loop(self):
        obs, cfg, post = fixture()
        a, b = actions([])
        g = SeedExecutionGuard(MECHANICS, max_order_units=2)
        self.assertEqual(g.transform(obs, cfg, a, b, post_units=post, scenarios=[scenario()]), a)
        self.assertEqual(g.last_report['status'], 'fallback_unknown')

    def test_current_units_are_not_executed_twice(self):
        obs, cfg, post = fixture(cash=100, hires=0)
        post['farm']['farmer'] = [0, 0]
        post['private']['seeds']['WHEAT'] = 1
        ENGINE._apply_unit_action(post['farm'], post['private'], 0,
                                 ['PLANT', 'WHEAT'], 10, 0, 24, 100)
        self.assertEqual(post['private']['seeds']['WHEAT'], 0)
        a, b = actions([], n=1)
        a['farmer'] = b['farmer'] = ['PLANT', 'WHEAT']
        g = SeedExecutionGuard(MECHANICS)
        result = g.project(obs, cfg, b, post_units=post, scenario=scenario())
        self.assertEqual(result['farms'][0], post['farm'])
        self.assertEqual(result['privates'][0]['seeds']['WHEAT'], 0)

    def test_kernel_functions_exact_source(self):
        source = ENGINE_SOURCE.read_text()
        official = {n.name: ast.get_source_segment(source, n) for n in ast.parse(source).body
                    if isinstance(n, ast.FunctionDef)}
        ours = (HERE/'market_kernel.py').read_text()
        for node in ast.parse(ours).body:
            if isinstance(node, ast.FunctionDef) and node.name != 'bind_market':
                self.assertEqual(ast.get_source_segment(ours, node), official[node.name])

    def test_split_market_matches_unmodified_official_engine(self):
        global ENGINE_CALLS
        queues = [[], [['HIRE']], [['BUY_LAND'], ['HIRE']],
                  [['SELL', 'WHEAT', 7], ['BUY_PRODUCT', 'WHEAT', 8]],
                  [['BUY_SEED', 'WHEAT', 9], ['HIRE'], ['BUY_ANIMAL', 'COW', 1]],
                  [['BAD'], ['BUY_SEED', 'TOMATO', 2], ['SELL', 'WOOL', 3]],
                  [['BUY_PRODUCT', 'FERTILIZER', 2], ['HIRE'], ['HIRE']]]
        g = SeedExecutionGuard(MECHANICS)
        for seat in (0, 1):
            for i, queue in enumerate(queues):
                for money in (0, 90, 233, 1200):
                    obs, cfg, post = fixture(seat, money, 12)
                    post['private']['shed'].update(WHEAT=15, WOOL=3)
                    case = scenario(f'case-{i}', queues[(i+3) % len(queues)],
                                    {'WHEAT': 11, 'WOOL': 3}, cash=money+40)
                    action = {'market': queue}
                    actual = g.project(obs, cfg, action, post_units=post, scenario=case)
                    state, full_queues = g._state(obs, post, case, action)
                    for p in (0, 1): state[p].action = {'market': full_queues[p]}
                    ENGINE._process_market(state, Struct(configuration=cfg)); ENGINE_CALLS += 1
                    self.assertEqual(actual['farms'], state[0].observation.farms)
                    self.assertEqual(actual['privates'], [s.observation.private for s in state])
                    self.assertEqual(actual['market'], state[0].observation.market)

    def test_concurrent_instances_do_not_patch_mechanics(self):
        before = {key: id(value) for key, value in vars(MECHANICS).items()}
        def run(index):
            g, result, _, b = self.run_guard(index % 2, 1000, 12, [['HIRE']])
            return result == b
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertTrue(all(pool.map(run, range(16))))
        self.assertEqual(before, {key: id(value) for key, value in vars(MECHANICS).items()})

    def test_identical_proposal_needs_no_scenario(self):
        obs, cfg, post = fixture()
        a, _ = actions([]); g = SeedExecutionGuard(MECHANICS)
        result = g.transform(obs, cfg, a, a, post_units=post, scenarios=None)
        self.assertEqual(result, a)
        self.assertIsNot(result, a)
        self.assertEqual(g.last_report['status'], 'unchanged')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--engine-cache', type=Path, required=True)
    parser.add_argument('--evaluator', type=Path, default=HERE.parent/'cloud-eval/evaluate.py')
    parser.add_argument('--engine-loader', type=Path)
    parser.add_argument('--mechanics', type=Path, default=HERE.parent/'cloud-execution-lab/mechanics.py')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    evaluator = load(args.evaluator, 'seed_guard_existing_evaluator')
    options = {'prepare': False}
    if args.engine_loader: options['loader'] = args.engine_loader
    ENGINE, engine_hashes = evaluator.get_engine(args.engine_cache, **options)
    ENGINE_SOURCE = args.engine_cache/'kaggriculture.py'
    MECHANICS = load(args.mechanics, 'seed_guard_existing_mechanics')
    start = time.perf_counter()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(GuardTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {'python': sys.version, 'tests_run': result.testsRun,
              'failures': len(result.failures), 'errors': len(result.errors),
              'skipped': len(result.skipped), 'seconds': time.perf_counter()-start,
              'unmodified_official_market_comparisons': ENGINE_CALLS,
              'engine_ref': evaluator.ENGINE_REF, 'engine_hashes': engine_hashes,
              'source_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in [HERE/'guard.py', HERE/'market_kernel.py',
                                          HERE/'test_guard.py', args.mechanics]},
              'full_games': 0, 'scored_seeds': [], 'fixture_type': 'synthetic'}
    if args.report: args.report.write_text(json.dumps(report, indent=2)+'\n')
    sys.exit(not result.wasSuccessful())
