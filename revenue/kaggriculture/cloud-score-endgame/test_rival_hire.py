# SPDX-License-Identifier: Apache-2.0
"""Explicit-rival-HIRE integration on a supplied local native-engine context.

All states are constructed; no game or held data is consumed. Existing PORT,
POLY, LARCH and PRISM code performs the actual table/selection operations.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import sys
import unittest
from unittest.mock import patch

DEPS = None
TI = None
CASES = None
ORIGINAL = None
COUNTS = {'producer_cells': 0, 'original_comparison_cells': 0,
          'full_terminal_interpreter_comparisons': 0, 'unit_boundary_captures': 0}
WITNESSES = []


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture(player=0, rival_cash=59):
    farm = dict(money=0, tiles=[[None]*10 for _ in range(10)], farmer=[4, 4],
                hands=[], unlocked_quadrants=['NW'], hires_today=0)
    farms = [deepcopy(farm), deepcopy(farm)]
    farms[1-player].update(money=rival_cash, hands=[[4, 4] for _ in range(13)], hires_today=13)
    market = {'inventory': {p: 10000 for p in DEPS.engine.PRODUCTS}, 'prices': {}}
    DEPS.engine._refresh_prices(market)
    cfg = dict(episodeSteps=720, boardSize=10, turnsPerDay=24, shedCapacity=100,
               maxMarketOrdersPerTurn=10, farmHandCostMult=1)
    obs = dict(step=718, day=29, hour=22, player=player, farms=farms, market=market,
               town={'unlocked_shops': []},
               private={'shed': {'MILK': 1}, 'seeds': {}, 'inventories': [{}]})
    action = {'farmer': ['PASS'], 'hands': [], 'market': [[], ['SELL', 'MILK', 1]]}
    sales = {'id': 'sale-only', 'shed': {'MILK': 2}, 'market': [['SELL', 'MILK', 2]],
             'origin': {'kind': 'constructed whole-queue hypothesis, not observed rival action'}}
    hire = {**deepcopy(sales), 'id': 'sale-then-hire', 'market': [['SELL', 'MILK', 2], ['HIRE']]}
    return obs, cfg, action, [sales, hire]


def packet(obs, cfg, action, scenarios, *, runtime=None, post=None, **kwargs):
    runtime = TI if runtime is None else runtime
    result = runtime.build_terminal_inputs(DEPS.engine, obs, cfg, action,
        post_unit_observation=deepcopy(obs) if post is None else post,
        scenarios=scenarios, **kwargs)
    COUNTS['producer_cells' if runtime is TI else 'original_comparison_cells'] += result['native_market_calls']
    return result


def choose(obs, cfg, action, value, *, tie_break='cash_pareto'):
    obj = DEPS.score.make_score_selector(DEPS.selector.WholePlanSelector,
        DEPS.weighted.make_selector, DEPS.terminal.build_table,
        DEPS.core.solve_full_table, DEPS.core.verify_certificate,
        rng=random.Random(73009), tie_break=tie_break)
    plans = value['plans'] if value['complete'] else []
    out = obj.transform_terminal(obs, cfg, action, document=value['document'],
                                feasible=lambda candidate: any(p['action'] == candidate for p in plans))
    return out, obj


def native_check(test, obs, cfg, value):
    scenarios = {s['id']: s for s in value['scenarios']}
    for receipt in value['document']['receipts']:
        if not receipt['done']:
            continue
        state, env = CASES.make_state(obs, cfg, receipt['own_action'], scenarios[receipt['scenario']])
        DEPS.engine.interpreter(state, env)
        COUNTS['full_terminal_interpreter_comparisons'] += 1
        test.assertEqual([s.status for s in state], ['DONE', 'DONE'])
        p = obs['player']
        test.assertEqual([receipt['own_cash'], receipt['rival_cash']], [state[p].reward, state[1-p].reward])
        test.assertEqual(receipt['own_shed_after'], state[p].observation.private['shed'])
        test.assertEqual(receipt['own_seeds_after'], state[p].observation.private['seeds'])
        test.assertEqual(receipt['own_hands_after'], len(state[p].observation.farms[p]['hands']))
        if 'rival_hands_after' in receipt:
            test.assertEqual(receipt['rival_hands_after'], len(state[p].observation.farms[1-p]['hands']))
            test.assertEqual(receipt['rival_hires_today_after'], state[p].observation.farms[1-p]['hires_today'])


class RivalHireTests(unittest.TestCase):
    def test_native_hire_reverses_cash_dominance_in_both_positions(self):
        for player in (0, 1):
            obs, cfg, action, scenarios = fixture(player)
            value = packet(obs, cfg, action, scenarios, allow_rival_hire=True)
            native_check(self, obs, cfg, value)
            rows = value['document']['receipts']
            self.assertEqual(len(value['plans']), 2)
            self.assertEqual([[r['own_cash'], r['rival_cash']] for r in rows],
                             [[156, 377], [156, 0], [160, 375], [160, 375]])
            self.assertEqual([r['rival_hands_after'] for r in rows], [13, 14, 13, 13])
            self.assertEqual(rows[0]['scenario_sha256'], rows[2]['scenario_sha256'])
            self.assertEqual(rows[1]['scenario_sha256'], rows[3]['scenario_sha256'])
            WITNESSES.append({'player': player, 'packet': value})

    def test_actual_cash_tie_selector_consumes_added_hire_column(self):
        for player in (0, 1):
            obs, cfg, action, scenarios = fixture(player)
            only_sales = packet(obs, cfg, action, scenarios[:1])
            complete = packet(obs, cfg, action, scenarios, allow_rival_hire=True)
            old_action, old_actor = choose(obs, cfg, action, only_sales)
            new_action, new_actor = choose(obs, cfg, action, complete)
            self.assertNotEqual(old_action, action)
            self.assertEqual(old_actor.draws, 1)
            self.assertEqual(new_action, action)
            self.assertEqual(new_actor.draws, 0)
            self.assertEqual(new_actor.last_objective['value'], '0')
            self.assertEqual(new_actor.last_objective['status'], 'baseline_optimal')
            self.assertEqual(DEPS.terminal.build_table(complete['document'])['win_points'],
                             [['0', '1'], ['0', '0']])
            # This is a conditional decision with both hypotheses retained, not
            # prediction that the rival will choose the HIRE column.
            self.assertEqual(len(new_actor.last_objective['scenario_ids']), 2)
            WITNESSES.append({'kind': 'actual_selector', 'player': player,
                'sale_only_action': old_action, 'with_hire_action': new_action,
                'sale_only_objective': old_actor.last_objective,
                'with_hire_objective': new_actor.last_objective})

    def test_native_affordability_threshold_is_recomputed_per_plan(self):
        for player in (0, 1):
            for cash, hires in ((58, [13, 13]), (59, [14, 13]), (60, [14, 13]), (61, [14, 14])):
                obs, cfg, action, scenarios = fixture(player, cash)
                result = packet(obs, cfg, action, scenarios[1:], allow_rival_hire=True)
                native_check(self, obs, cfg, result)
                self.assertEqual([r['rival_hands_after'] for r in result['document']['receipts']], hires)

    def test_multiple_native_hires_keep_fibonacci_costs(self):
        obs, cfg, action, _ = fixture()
        obs['farms'][1].update(money=3, hires_today=0, hands=[])
        scenarios = [{'id': 'three-requests', 'shed': {}, 'market': [['HIRE']]*3, 'origin': 'test'}]
        value = packet(obs, cfg, action, scenarios, max_plans=1, allow_rival_hire=True)
        native_check(self, obs, cfg, value)
        receipt = value['document']['receipts'][0]
        self.assertEqual((receipt['rival_cash'], receipt['rival_hands_after'], receipt['rival_hires_today_after']), (1, 2, 2))

    def test_zero_multiplier_is_native_and_still_bounded_by_queue(self):
        obs, cfg, action, _ = fixture()
        obs['farms'][1].update(money=0, hires_today=0, hands=[])
        cfg['farmHandCostMult'] = 0
        scenario = [{'id': 'free-native', 'shed': {}, 'market': [['HIRE']]*10}]
        value = packet(obs, cfg, action, scenario, max_plans=1, allow_rival_hire=True)
        native_check(self, obs, cfg, value)
        self.assertEqual(value['document']['receipts'][0]['rival_hands_after'], 10)

    def test_default_still_rejects_hire(self):
        obs, cfg, action, scenarios = fixture()
        for options in ({}, {'allow_rival_hire': False}):
            with self.assertRaisesRegex(ValueError, 'SELL slots only'):
                packet(obs, cfg, action, scenarios, **options)

    def test_opt_in_needs_boolean_and_explicit_whole_scenarios(self):
        obs, cfg, action, scenarios = fixture()
        for flag in (None, 1, 0, 'true', []):
            with self.assertRaises(ValueError):
                packet(obs, cfg, action, scenarios, allow_rival_hire=flag)
        with self.assertRaises(ValueError):
            packet(obs, cfg, action, None, allow_rival_hire=True)

    def test_unmodeled_rival_operations_stay_rejected(self):
        obs, cfg, action, scenarios = fixture()
        for order in (['BUY_PRODUCT', 'WHEAT', 1], ['BUY_SEED', 'CARROT', 1],
                      ['BUY_ANIMAL', 'GOOSE', 1], ['BUY_LAND'], ['HIRE', 2], ['UNKNOWN']):
            bad = deepcopy(scenarios[1:]); bad[0]['market'][-1] = order
            with self.assertRaises(ValueError):
                packet(obs, cfg, action, bad, allow_rival_hire=True)

    def test_hiring_uses_bounded_public_count(self):
        for count in (-1, None, True, 13.0, 14, 10**6):
            obs, cfg, action, scenarios = fixture()
            obs['farms'][1]['hires_today'] = count
            with patch.object(DEPS.engine, '_process_market', side_effect=AssertionError('native call on invalid input')):
                with self.assertRaises(ValueError):
                    packet(obs, cfg, action, scenarios, allow_rival_hire=True)

    def test_capacity_and_full_sale_stock_contract_is_unchanged(self):
        obs, cfg, action, scenarios = fixture()
        for mutate in ('capacity', 'stock', 'unknown_product'):
            bad = deepcopy(scenarios[1:])
            if mutate == 'capacity': bad[0]['shed'] = {'MILK': 100, 'WOOL': 1}
            if mutate == 'stock': bad[0]['shed']['MILK'] = 1
            if mutate == 'unknown_product': bad[0]['shed']['UNKNOWN'] = 1
            with self.assertRaises(ValueError):
                packet(obs, cfg, action, bad, allow_rival_hire=True)

    def test_slots_are_preserved_and_inactive_tail_is_not_modeled(self):
        obs, cfg, action, scenarios = fixture()
        delayed = deepcopy(scenarios[1:])
        delayed[0]['market'] = [['SELL', 'MILK', 2]] + [[]]*8 + [['HIRE']]
        value = packet(obs, cfg, action, delayed, allow_rival_hire=True)
        native_check(self, obs, cfg, value)
        self.assertEqual(value['scenarios'][0]['market'], delayed[0]['market'])
        delayed[0]['market'].append(['HIRE'])
        with self.assertRaises(ValueError):
            packet(obs, cfg, action, delayed, allow_rival_hire=True)

    def test_duplicate_scenario_ids_are_not_coalesced(self):
        obs, cfg, action, scenarios = fixture()
        scenarios[1]['id'] = scenarios[0]['id']
        with self.assertRaises(ValueError):
            packet(obs, cfg, action, scenarios, allow_rival_hire=True)

    def test_missing_cells_preserve_all_columns_and_fallback(self):
        obs, cfg, action, scenarios = fixture()
        value = packet(obs, cfg, action, scenarios, allow_rival_hire=True, max_cells=1)
        self.assertFalse(value['complete'])
        self.assertEqual(value['native_market_calls'], 1)
        self.assertEqual(len(value['document']['receipts']), 4)
        self.assertEqual(sum(r['done'] for r in value['document']['receipts']), 1)
        out, actor = choose(obs, cfg, action, value)
        self.assertEqual(out, action)
        self.assertEqual(actor.provider_calls, 0)
        self.assertEqual(actor.draws, 0)

    def test_expired_deadline_does_not_enter_native_market(self):
        obs, cfg, action, scenarios = fixture()
        with patch.object(DEPS.engine, '_process_market', side_effect=AssertionError('native entered')):
            value = packet(obs, cfg, action, scenarios, allow_rival_hire=True, deadline=-1)
        self.assertEqual(value['status'], 'deadline')
        self.assertEqual(value['native_market_calls'], 0)
        self.assertTrue(all(r['own_cash'] is None for r in value['document']['receipts']))

    def test_baseexception_cancellation_propagates_once(self):
        class Stop(BaseException): pass
        stop = Stop()
        obs, cfg, action, scenarios = fixture()
        before = deepcopy((obs, cfg, action, scenarios))
        with patch.object(DEPS.engine, '_process_market', side_effect=stop) as native:
            with self.assertRaises(Stop) as caught:
                packet(obs, cfg, action, scenarios, allow_rival_hire=True)
        self.assertIs(caught.exception, stop)
        self.assertEqual(native.call_count, 1)
        self.assertEqual(before, (obs, cfg, action, scenarios))

    def test_input_provenance_and_detachment(self):
        obs, cfg, action, scenarios = fixture()
        before = deepcopy((obs, cfg, action, scenarios))
        value = packet(obs, cfg, action, scenarios, allow_rival_hire=True)
        self.assertEqual(before, (obs, cfg, action, scenarios))
        self.assertEqual(value['scenarios'][1]['origin'], scenarios[1]['origin'])
        self.assertEqual(value['source']['hypothesis_family'], 'caller-supplied-sale-and-hire-hypotheses')
        self.assertIsNone(value['source']['scenario_probabilities'])
        value['scenarios'][1]['market'].clear()
        self.assertEqual(before, (obs, cfg, action, scenarios))

    def test_same_post_unit_snapshot_is_not_reexecuted(self):
        obs, cfg, action, scenarios = fixture()
        obs['private']['shed'] = {}
        obs['private']['inventories'] = [{'MILK': 1}]
        action['farmer'] = ['DROP']
        post = CASES.own_unit_snapshot(DEPS.engine, obs, cfg, action)
        COUNTS['unit_boundary_captures'] += 1
        with patch.object(DEPS.engine, '_apply_unit_action', side_effect=AssertionError('duplicate unit call')):
            value = packet(obs, cfg, action, scenarios, post=post, allow_rival_hire=True)
        native_check(self, obs, cfg, value)
        self.assertEqual(value['plans'][0]['action']['farmer'], ['DROP'])

    def test_original_default_packets_match_exactly(self):
        for player in (0, 1):
            for mode in ('normal', 'quiet', 'own_hire', 'empty'):
                obs, cfg, action, scenarios = fixture(player)
                if mode == 'quiet': scenarios = [{'id': 'quiet', 'shed': {}, 'market': []}]
                else: scenarios = scenarios[:1]
                if mode == 'own_hire': action['market'] = [[], ['HIRE'], ['SELL', 'MILK', 1]]
                if mode == 'empty': obs['private']['shed'] = {}; action['market'] = []
                before = packet(obs, cfg, action, scenarios, runtime=ORIGINAL)
                after = packet(obs, cfg, action, scenarios)
                self.assertEqual(before, after)


def main():
    global DEPS, TI, CASES, ORIGINAL
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--context', type=Path, required=True, help='Extracted existing POLY source/dependencies/engine package')
    parser.add_argument('--runtime-file', type=Path, default=Path(__file__).with_name('terminal_inputs.py'))
    parser.add_argument('--score-file', type=Path, required=True, help='Existing LARCH score consumer with cash_pareto API')
    parser.add_argument('--original-file', type=Path, required=True, help='Unchanged PORT/POLY producer2eae54ea for default correspondence')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists(): parser.error('use a new output path to retain prior results')
    root = args.context.resolve()
    TI = load(args.runtime_file.resolve(), 'terminal_inputs')
    sys.modules['terminal_inputs'] = TI
    CASES = load(root/'source/terminal_input_cases.py', 'rival_hire_existing_cases')
    DEPS = CASES.dependencies(root/'dependencies/engine_loader.py', root/'engine',
                             root/'dependencies', root/'dependencies/full_support.py')
    DEPS.score = load(args.score_file.resolve(), 'rival_hire_score')
    ORIGINAL = load(args.original_file.resolve(), 'rival_hire_original_producer')
    paths = [args.runtime_file, args.score_file, args.original_file,
             root/'source/terminal_input_cases.py', root/'dependencies/engine_loader.py',
             *[root/'dependencies'/n for n in ('terminal_utility.py', 'full_support.py', 'selector.py', 'solver.py', 'weighted_selector.py')],
             *[root/'engine'/n for n in ('kaggriculture.py', 'kaggriculture.json', 'utils.py')], Path(__file__)]
    def identities():
        return {str(p.resolve()): {'bytes': len(p.read_bytes()), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest(),
                    'git_blob': hashlib.sha1(b'blob '+str(len(p.read_bytes())).encode()+b'\0'+p.read_bytes()).hexdigest()}
                for p in paths}
    sources = identities()
    tests = unittest.defaultTestLoader.loadTestsFromTestCase(RivalHireTests)
    result = unittest.TextTestRunner(verbosity=2).run(tests)
    if identities() != sources: raise AssertionError('source changed during execution')
    report = {'schema': 'titan.rival-hire-consumer.v1', 'tests': result.testsRun,
              'failures': len(result.failures), 'errors': len(result.errors), 'skips': len(result.skipped),
              'passed': result.wasSuccessful(), 'counts': COUNTS, 'sources': sources,
              'witnesses': WITNESSES, 'new_full_games': 0, 'seed_uses': 0,
              'scope': 'Constructed terminal native-market and actual-component tests; no occurrence/strength estimate or default change.'}
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__': raise SystemExit(main())
