# SPDX-License-Identifier: Apache-2.0
"""Snapshot reuse: exact reports, detached state and unchanged market calls."""
from __future__ import annotations
import argparse
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import sys
import time
import types
from typing import Any, Callable
import unittest
from unittest.mock import patch

import queue_delta as candidate

HERE = Path(__file__).resolve().parent
ENGINE = BASELINE = None
COUNTS = {'complete_comparisons': 0, 'official_full_market_calls': 0,
          'baseline_report_matches': 0}
BASELINE_SHA256 = 'c57672b8ee431774c8bd6f2e3d264d716d3ced125eae0928f00be05e1bb1d2ad'


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_full_engine(root):
    """Use the unchanged complete source and its actual seed helper; no games."""
    root = Path(root)
    tree = ast.parse((root / 'utils.py').read_text())
    helper = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                  and n.name == 'resolve_episode_seed')
    ns = dict(Any=Any, Callable=Callable, random=random)
    exec(compile(ast.Module(body=[helper], type_ignores=[]), str(root / 'utils.py'), 'exec'), ns)
    names = ('kaggle_environments', 'kaggle_environments.utils')
    old = {name: sys.modules.get(name) for name in names}
    package, utils = types.ModuleType(names[0]), types.ModuleType(names[1])
    utils.resolve_episode_seed = ns['resolve_episode_seed']
    sys.modules[names[0]], sys.modules[names[1]] = package, utils
    try:
        return load_module('snapshot_official_engine', root / 'kaggriculture.py')
    finally:
        for name, value in old.items():
            if value is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value


def fixture(*, seat=0, scenarios=1, hands=6, slots=10):
    farm = ENGINE._new_farm(10, 5000)
    farm['hands'] = [[4, 4] for _ in range(hands)]
    farm['hires_today'] = hands
    private = ENGINE._new_private()
    private['inventories'] = [{'MILK': 2, 'WHEAT': 1} for _ in range(hands + 1)]
    private['shed'].update(WHEAT=12, CARROT=12, MILK=10, WOOL=4, FERTILIZER=2)
    orders = [['SELL', 'WHEAT', 2], ['BUY_PRODUCT', 'FERTILIZER', 1],
              ['BUY_SEED', 'CARROT', 2], ['SELL', 'CARROT', 2], ['HIRE'],
              ['BUY_ANIMAL', 'GOOSE', 1], ['BUY_LAND'], [],
              ['SELL', 'WOOL', 2], ['BUY_PRODUCT', 'WHEAT', 2]][:slots]
    proposal = copy.deepcopy(orders)
    if len(proposal) > 2:
        proposal[2] = []
    if len(proposal) > 8:
        proposal[8] = ['SELL', 'WOOL', 3]
    rival = []
    for i in range(scenarios):
        rf, rp = copy.deepcopy((farm, private))
        rf['money'] += i * 50
        rp['shed']['MILK'] += i % 4
        q = copy.deepcopy(orders)
        if q:
            q[0] = ['SELL', 'MILK', 1 + i % 3]
        rival.append(dict(id=str(i), provenance='constructed benchmark input, not hidden truth',
                          farm=rf, private=rp, action=dict(market=q)))
    return dict(step=241, seat=seat, own_farm=farm, own_private=private,
                market=ENGINE._new_market(),
                baseline_action=dict(farmer=['PASS'], hands=[], market=orders),
                proposed_action=dict(farmer=['PASS'], hands=[], market=proposal),
                scenarios=rival, configuration=dict(boardSize=10,
                    maxMarketOrdersPerTurn=max(1, slots), farmHandCostMult=1, shedCapacity=100))


def without_time(report):
    result = copy.deepcopy(report)
    result.pop('elapsed_seconds', None)
    return result


def reference(payload, action, scenario):
    seat = payload['seat']
    farms, privates = [None, None], [None, None]
    farms[seat], privates[seat] = copy.deepcopy((payload['own_farm'], payload['own_private']))
    farms[1-seat], privates[1-seat] = copy.deepcopy((scenario['farm'], scenario['private']))
    market = copy.deepcopy(payload['market'])
    actions = [None, None]
    actions[seat], actions[1-seat] = copy.deepcopy((action, scenario['action']))
    state = [candidate.Struct(observation=candidate.Struct(
        farms=farms, private=privates[i], market=market), action=actions[i]) for i in (0, 1)]
    ENGINE._process_market(state, candidate.Struct(configuration=candidate.Struct(payload['configuration'])))
    COUNTS['official_full_market_calls'] += 1
    return farms, privates, market


class SnapshotTests(unittest.TestCase):
    def compare(self, payload):
        original = copy.deepcopy(payload)
        report = candidate.compare_queues(ENGINE, **payload)
        self.assertEqual(report['status'], 'complete_conditional', report['reason'])
        self.assertEqual(payload, original)
        for row, scenario in zip(report['scenario_results'], payload['scenarios']):
            for arm in ('baseline', 'proposed'):
                farms, private, market = reference(payload, payload[arm + '_action'], scenario)
                seat = payload['seat']
                self.assertEqual(row[arm]['own_farm'], farms[seat])
                self.assertEqual(row[arm]['rival_farm'], farms[1-seat])
                self.assertEqual(row[arm]['own_private'], private[seat])
                self.assertEqual(row[arm]['rival_private'], private[1-seat])
                self.assertEqual(row[arm]['market'], market)
                self.assertEqual(sum(v['own']['cash'] for v in row[arm]['trace']), row[arm]['own_effect']['cash'])
        if BASELINE is not None:
            self.assertEqual(without_time(report), without_time(BASELINE.compare_queues(ENGINE, **payload)))
            COUNTS['baseline_report_matches'] += 1
        COUNTS['complete_comparisons'] += 1
        return report

    def test_snapshot_count_halved_without_skipping_slots(self):
        for slots in (0, 1, 3, 10):
            payload = fixture(slots=slots)
            with patch.object(candidate, '_view', wraps=candidate._view) as views:
                with patch.object(ENGINE, '_process_market', wraps=ENGINE._process_market) as market:
                    report = candidate.compare_queues(ENGINE, **payload)
                    self.assertEqual(report['status'], 'complete_conditional')
                    self.assertEqual(views.call_count, 4 * (slots + 1))  # two arms, two parties
                    self.assertEqual(market.call_count, 2 * slots)

    def test_empty_queues_preserve_stale_prices_and_zero_effects(self):
        payload = fixture(slots=0)
        payload['market']['prices']['MILK'] = -999
        report = self.compare(payload)
        row = report['scenario_results'][0]
        self.assertEqual(row['baseline']['trace'], [])
        self.assertEqual(row['delta']['own_cash'], 0)
        self.assertEqual(row['baseline']['market']['prices']['MILK'], -999)

    def test_asymmetric_queues_and_slot_truncation(self):
        for limit in (0, 1, 3, 10):
            for seat in (0, 1):
                payload = fixture(seat=seat)
                payload['configuration']['maxMarketOrdersPerTurn'] = limit
                payload['baseline_action']['market'] = []
                payload['scenarios'][0]['action']['market'] = [['HIRE']]
                self.compare(payload)

    def test_final_views_do_not_alias_live_state_inputs_or_other_arms(self):
        for slots in (0, 10):
            payload = fixture(slots=slots, scenarios=2)
            report = self.compare(payload)
            saved = copy.deepcopy((payload, report['scenario_results'][1], report['scenario_results'][0]['baseline']))
            row = report['scenario_results'][0]['proposed']
            before = copy.deepcopy(row['own_private'])
            row['own']['shed']['WHEAT'] = -1
            row['own']['hands'][0][0] = -1
            row['own']['inventories'][0]['MILK'] = -1
            self.assertEqual(row['own_private'], before)
            self.assertEqual((payload, report['scenario_results'][1], report['scenario_results'][0]['baseline']), saved)
            self.assertNotEqual(row['own_farm']['hands'][0][0], -1)

    def test_prior_slot_effects_stay_detached_from_later_mutation(self):
        report = self.compare(fixture())
        arm = report['scenario_results'][0]['proposed']
        effect = copy.deepcopy(arm['trace'][4]['own'])
        self.assertEqual(effect['hires'], 1)
        arm['own_farm']['hands'][-1][0] = -1
        arm['own']['hands'][-1][0] = -2
        self.assertEqual(arm['trace'][4]['own'], effect)

    def test_partial_deadline_has_same_checks_and_no_bounds(self):
        payload = fixture(slots=0, scenarios=2)
        for module in [candidate] + ([BASELINE] if BASELINE else []):
            with patch.object(module.time, 'monotonic', side_effect=[0, 0, 0, 0, 2]):
                report = module.compare_queues(ENGINE, **payload, deadline=1)
            self.assertEqual(report['status'], 'unknown')
            self.assertEqual(report['reason'], 'deadline')
            self.assertIsNone(report['bounds'])
            self.assertEqual(len(report['scenario_results']), 1)

    def test_engine_failure_is_preserved_without_retry(self):
        payload = fixture(slots=3)
        for module in [candidate] + ([BASELINE] if BASELINE else []):
            calls = []
            def failing(state, env):
                calls.append(None)
                if len(calls) == 2:
                    raise RuntimeError('preserved-body-error')
                ENGINE._process_market(state, env)
            engine = types.SimpleNamespace(_parse_order=ENGINE._parse_order, _process_market=failing)
            report = module.compare_queues(engine, **payload)
            self.assertEqual(len(calls), 2)
            self.assertEqual(report['reason'], 'engine_error:RuntimeError')
            self.assertEqual(report['scenario_results'], [])
            self.assertIsNone(report['bounds'])

    def test_partial_second_scenario_failure_does_not_commit_partial_arm(self):
        payload = fixture(slots=1, scenarios=2)
        calls = []
        def failing(state, env):
            calls.append(None)
            if len(calls) == 4:
                raise ValueError('second-proposed')
            ENGINE._process_market(state, env)
        engine = types.SimpleNamespace(_parse_order=ENGINE._parse_order, _process_market=failing)
        report = candidate.compare_queues(engine, **payload)
        self.assertEqual(report['status'], 'unknown')
        self.assertEqual(len(report['scenario_results']), 1)
        self.assertIsNone(report['bounds'])

    def test_incomplete_and_work_budget_paths_match_old_reports(self):
        payloads = []
        p = fixture(); p['scenarios'] = []; payloads.append(p)
        p = fixture(); p['own_private']['inventories'] = []; payloads.append(p)
        p = fixture(); p['proposed_action']['farmer'] = ['WATER']; payloads.append(p)
        p = fixture(); p['proposed_action']['market'] = [['BUY_SEED','WHEAT',100000]]; payloads.append(p)
        for p in payloads:
            report = candidate.compare_queues(ENGINE, **p)
            self.assertEqual(report['status'], 'unknown')
            if BASELINE:
                self.assertEqual(without_time(report), without_time(BASELINE.compare_queues(ENGINE, **p)))

    def test_both_seats_crossed_queues_match_complete_market(self):
        queues = [[], [['SELL','MILK',3]], [['BUY_PRODUCT','WHEAT',4]],
                  [['BUY_SEED','CARROT',2],['HIRE']],
                  [['SELL','CARROT',2],['BUY_ANIMAL','COW',1]],
                  [[],['SELL','MILK',5]], [['BUY_LAND'],['HIRE']],
                  [['BUY_PRODUCT','FERTILIZER',2],['SELL','FERTILIZER',2]]]
        for seat in (0, 1):
            for capacity in (10, 100):
                for i, orders in enumerate(queues):
                    for j, rival in enumerate(queues):
                        with self.subTest(seat=seat, capacity=capacity, own=i, rival=j):
                            p = fixture(seat=seat)
                            p['own_farm']['money'] = 1100 if (i + j) % 2 else 200
                            p['configuration']['shedCapacity'] = capacity
                            p['own_private']['shed'] = dict(MILK=4,CARROT=3,WHEAT=2)
                            p['baseline_action']['market'] = copy.deepcopy(orders)
                            p['proposed_action']['market'] = copy.deepcopy(queues[(i+1)%len(queues)])
                            p['scenarios'][0]['private']['shed'] = dict(MILK=4,CARROT=3,WHEAT=2)
                            p['scenarios'][0]['action']['market'] = copy.deepcopy(rival)
                            self.compare(p)

    def test_large_scenario_bank_keeps_every_row(self):
        for count, hands in ((1,0), (8,6), (32,12)):
            report = self.compare(fixture(scenarios=count, hands=hands))
            self.assertEqual(len(report['scenario_results']), count)
            self.assertFalse(report['action_selected'])

    def test_invalid_noops_floor_and_custom_market_params(self):
        for seat in (0, 1):
            p = fixture(seat=seat)
            p['baseline_action']['market'] = [None, ['BOGUS'], ['SELL','MILK','bad']]
            p['proposed_action']['market'] = [[], ['SELL','MILK',3]]
            p['market']['inventory']['MILK'] = 100000
            p['market']['params'] = ENGINE._resolve_market_params({'WHEAT': {'base': 42}})
            self.compare(p)


def main():
    global ENGINE, BASELINE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine-cache', type=Path, required=True)
    parser.add_argument('--baseline-source', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    ENGINE = load_full_engine(args.engine_cache)
    if args.baseline_source:
        if hashlib.sha256(args.baseline_source.read_bytes()).hexdigest() != BASELINE_SHA256:
            parser.error('baseline-source must be the original PR9976 queue_delta.py')
        BASELINE = load_module('snapshot_baseline', args.baseline_source)
    started = time.perf_counter()
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(SnapshotTests))
    report = dict(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                  **COUNTS, game_panels=0, game_seeds=0,
                  source_sha256=hashlib.sha256(Path(candidate.__file__).read_bytes()).hexdigest(),
                  test_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  engine_sha256=hashlib.sha256((args.engine_cache/'kaggriculture.py').read_bytes()).hexdigest(),
                  baseline_sha256=BASELINE_SHA256 if BASELINE else None,
                  elapsed_seconds=time.perf_counter()-started)
    if args.report:
        args.report.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report))
    return 0 if result.wasSuccessful() else 1

if __name__ == '__main__':
    raise SystemExit(main())
