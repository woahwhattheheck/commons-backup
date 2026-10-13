# SPDX-License-Identifier: Apache-2.0
"""Consumer tests against the unmodified complete official market function."""
from __future__ import annotations
import argparse
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import time
import types
from typing import Any, Callable
import unittest
from unittest.mock import patch

from queue_delta import Struct, compare_queues, load_market_engine

ENGINE = MARKET = None
ENGINE_DIR = None
FULL_MARKET_CALLS = 0
CASE_COUNT = 0


def load_full_engine(root):
    # Load the actual seed helper, as the existing artifact evaluator does; no
    # substitute seed behavior, network request or game initialization is used.
    root = Path(root)
    tree = ast.parse((root/'utils.py').read_text())
    helper = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                  and n.name == 'resolve_episode_seed')
    namespace = dict(Any=Any, Callable=Callable, random=random)
    exec(compile(ast.Module(body=[helper], type_ignores=[]), str(root/'utils.py'), 'exec'), namespace)
    old = {name: sys.modules.get(name) for name in ('kaggle_environments', 'kaggle_environments.utils')}
    package = types.ModuleType('kaggle_environments')
    utils = types.ModuleType('kaggle_environments.utils')
    utils.resolve_episode_seed = namespace['resolve_episode_seed']
    sys.modules['kaggle_environments'], sys.modules['kaggle_environments.utils'] = package, utils
    try:
        spec = importlib.util.spec_from_file_location('queue_test_official', root/'kaggriculture.py')
        engine = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(engine)
    finally:
        for name, value in old.items():
            if value is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value
    return engine


def fixture(seat=0, *, cash=300, stock=None, baseline=None, proposed=None,
            rival_cash=3000, rival_stock=None, rival_orders=None, hires=0, capacity=100):
    farm = ENGINE._new_farm(10, cash)
    farm['hires_today'] = hires
    farm['hands'] = [[4, 4] for _ in range(hires)]
    private = ENGINE._new_private()
    private['inventories'] = [{} for _ in range(hires + 1)]
    private['shed'].update(stock or {})
    rival_farm = ENGINE._new_farm(10, rival_cash)
    rival_private = ENGINE._new_private()
    rival_private['shed'].update(rival_stock or {})
    return dict(step=17, seat=seat, own_farm=farm, own_private=private,
        market=ENGINE._new_market(),
        baseline_action=dict(farmer=['PASS'], hands=[], market=copy.deepcopy(baseline or [])),
        proposed_action=dict(farmer=['PASS'], hands=[], market=copy.deepcopy(proposed or [])),
        scenarios=[dict(id='specified', provenance='constructed conditional input; not observed hidden state',
            farm=rival_farm, private=rival_private,
            action=dict(market=copy.deepcopy(rival_orders or [])))],
        configuration=dict(boardSize=10, maxMarketOrdersPerTurn=10,
                           farmHandCostMult=1, shedCapacity=capacity))


def full_market(payload, action, scenario):
    global FULL_MARKET_CALLS
    p = payload['seat']
    farms, private = [None, None], [None, None]
    farms[p], private[p] = copy.deepcopy((payload['own_farm'], payload['own_private']))
    farms[1-p], private[1-p] = copy.deepcopy((scenario['farm'], scenario['private']))
    market = copy.deepcopy(payload['market'])
    actions = [None, None]
    actions[p], actions[1-p] = copy.deepcopy((action, scenario['action']))
    state = [Struct(observation=Struct(farms=farms, private=private[i], market=market),
                    action=actions[i]) for i in (0, 1)]
    ENGINE._process_market(state, Struct(configuration=Struct(payload['configuration'])))
    FULL_MARKET_CALLS += 1
    return farms, private, market


class QueueTests(unittest.TestCase):
    def compare(self, payload):
        global CASE_COUNT
        before = copy.deepcopy(payload)
        result = compare_queues(MARKET, **payload)
        self.assertEqual(result['status'], 'complete_conditional', result.get('reason'))
        self.assertEqual(payload, before)
        for row, scenario in zip(result['scenario_results'], payload['scenarios']):
            for name in ('baseline', 'proposed'):
                farms, private, market = full_market(payload, payload[name+'_action'], scenario)
                p = payload['seat']
                self.assertEqual(row[name]['own_farm'], farms[p])
                self.assertEqual(row[name]['rival_farm'], farms[1-p])
                self.assertEqual(row[name]['own_private'], private[p])
                self.assertEqual(row[name]['rival_private'], private[1-p])
                self.assertEqual(row[name]['market'], market)
                self.assertEqual(sum(x['own']['cash'] for x in row[name]['trace']), row[name]['own_effect']['cash'])
                self.assertEqual(sum(x['rival']['cash'] for x in row[name]['trace']), row[name]['rival_effect']['cash'])
        CASE_COUNT += 1
        return result

    def test_sale_funds_inherited_hire(self):
        # Generic queue attribution, not a reconstruction of LOSS-DELTA's
        # separately retained seed-reduction counterexample.
        for p in (0, 1):
            result = self.compare(fixture(p, cash=0, hires=2, stock={'WHEAT':2},
                baseline=[[], ['HIRE']], proposed=[['SELL','WHEAT',2], ['HIRE']]))
            row = result['scenario_results'][0]
            self.assertEqual(row['delta']['own_cash'], 47)
            self.assertTrue(row['delta']['slots'][1]['inherited_execution_changed'])
            self.assertEqual(row['proposed']['trace'][1]['own']['cash'], -2)
            self.assertTrue(row['delta']['resource_changes']['hands'])
            self.assertFalse(result['action_selected'])

    def test_same_slot_uses_shared_precommit_quotes(self):
        for p in (0, 1):
            result = self.compare(fixture(p, cash=10000,
                baseline=[], proposed=[['BUY_PRODUCT','WHEAT',6]],
                rival_orders=[['BUY_PRODUCT','WHEAT',7]]))
            self.assertNotEqual(result['scenario_results'][0]['delta']['rival_cash'], 0)

    def test_sale_changes_rival_receipt(self):
        for p in (0, 1):
            result = self.compare(fixture(p, stock={'MILK':30},
                baseline=[['SELL','MILK',30]], proposed=[[], ['SELL','MILK',30]],
                rival_stock={'MILK':30}, rival_orders=[['SELL','MILK',30]]))
            self.assertNotEqual(result['scenario_results'][0]['delta']['rival_cash'], 0)

    def test_sales_fund_later_purchase(self):
        result = self.compare(fixture(cash=0, stock={'CARROT':3},
            baseline=[['BUY_SEED','TOMATO',2], ['SELL','CARROT',3]],
            proposed=[['SELL','CARROT',3], ['BUY_SEED','TOMATO',2]]))
        self.assertEqual(result['scenario_results'][0]['proposed']['own']['seeds']['TOMATO'], 2)
        self.assertEqual(result['scenario_results'][0]['baseline']['own']['seeds']['TOMATO'], 0)

    def test_shared_capacity_seed_and_animal(self):
        for p in (0, 1):
            result = self.compare(fixture(p, cash=1000, stock={'CARROT':1}, capacity=1,
                baseline=[['BUY_ANIMAL','COW',1], ['BUY_SEED','TOMATO',1]],
                proposed=[['SELL','CARROT',1], ['BUY_ANIMAL','COW',1], ['BUY_SEED','TOMATO',1]]))
            self.assertEqual(result['scenario_results'][0]['baseline']['own']['shed']['COW'], 0)
            self.assertEqual(result['scenario_results'][0]['proposed']['own']['shed']['COW'], 1)
            self.assertEqual(result['scenario_results'][0]['proposed']['own']['seeds']['TOMATO'], 1)

    def test_floor_sales_do_not_increase_supply(self):
        payload = fixture(stock={'MILK':3}, baseline=[], proposed=[['SELL','MILK',3]])
        payload['market']['inventory']['MILK'] = 100000
        result = self.compare(payload)
        self.assertEqual(result['scenario_results'][0]['delta']['own_cash'], 3)
        self.assertEqual(result['scenario_results'][0]['proposed']['market']['inventory']['MILK'],100000)

    def test_repeated_hires_and_land_are_attributed(self):
        result = self.compare(fixture(cash=8000, baseline=[],
            proposed=[['HIRE'], ['HIRE'], ['HIRE'], ['BUY_LAND'], ['BUY_LAND']]))
        row = result['scenario_results'][0]
        self.assertEqual(row['proposed']['own']['hires_today'],3)
        self.assertEqual(row['proposed']['own']['land'],['NW','NE','SW'])
        self.assertEqual(row['delta']['own_cash'],-3004)

    def test_slot_limit_respected_without_repacking(self):
        payload = fixture(baseline=[], proposed=[[], ['BUY_SEED','WHEAT',5]])
        payload['configuration']['maxMarketOrdersPerTurn'] = 1
        result = self.compare(payload)
        self.assertEqual(result['scenario_results'][0]['delta']['own_cash'],0)

    def test_zero_config_limit_matches_engine_minimum_one(self):
        payload = fixture(baseline=[], proposed=[['BUY_SEED','WHEAT',1],['HIRE']])
        payload['configuration']['maxMarketOrdersPerTurn'] = 0
        result = self.compare(payload)
        self.assertEqual(result['scenario_results'][0]['delta']['own_cash'],-10)

    def test_malformed_noops_keep_slot_positions(self):
        self.compare(fixture(baseline=[None, ['BOGUS'], ['SELL','MILK','bad']],
            proposed=[[], ['BUY_SEED','WHEAT',2], ['HIRE']], rival_orders=[['BUY_SEED','WHEAT',1]]))

    def test_no_queues_does_not_refresh_stale_prices(self):
        payload = fixture()
        payload['market']['prices']['MILK'] = -999
        result = self.compare(payload)
        self.assertEqual(result['scenario_results'][0]['baseline']['market']['prices']['MILK'],-999)
        self.assertEqual(result['scenario_results'][0]['baseline']['trace'],[])

    def test_custom_market_params(self):
        payload = fixture(stock={'WHEAT':5}, proposed=[['SELL','WHEAT',5]])
        payload['market']['params'] = ENGINE._resolve_market_params({'WHEAT':{'base':42}})
        self.compare(payload)

    def test_multiple_explicit_scenarios_bounds(self):
        payload = fixture(stock={'MILK':30}, baseline=[['SELL','MILK',30]],
                          proposed=[[], ['SELL','MILK',30]])
        second = copy.deepcopy(payload['scenarios'][0])
        second['id']='rival_sells'; second['private']['shed']['MILK']=30
        second['action']['market']=[['SELL','MILK',30]]
        payload['scenarios'].append(second)
        result = self.compare(payload)
        deltas=[r['delta']['relative_cash'] for r in result['scenario_results']]
        self.assertEqual(result['bounds']['relative_cash'],dict(min=min(deltas),max=max(deltas)))
        self.assertFalse(result['probabilistic'])

    def test_changed_units_unknown_without_execution(self):
        payload=fixture(); payload['proposed_action']['farmer']=['WATER']
        result=compare_queues(MARKET,**payload)
        self.assertEqual(result['status'],'unknown'); self.assertIsNone(result['bounds'])
        self.assertEqual(result['scenario_results'],[])

    def test_missing_scenario_is_unknown_not_zero_rival(self):
        payload=fixture(); payload['scenarios']=[]
        self.assertIn('explicit_rival',compare_queues(MARKET,**payload)['reason'])

    def test_incomplete_scenario_is_unknown(self):
        payload=fixture(); del payload['scenarios'][0]['private']
        result=compare_queues(MARKET,**payload)
        self.assertEqual(result['status'],'unknown'); self.assertEqual(result['scenario_results'],[])

    def test_duplicate_scenario_id_unknown(self):
        payload=fixture(); payload['scenarios'].append(copy.deepcopy(payload['scenarios'][0]))
        self.assertIn('scenario_ids',compare_queues(MARKET,**payload)['reason'])

    def test_resource_preflight_and_deadline(self):
        payload=fixture(proposed=[['BUY_SEED','WHEAT',100000]])
        self.assertEqual(compare_queues(MARKET,**payload)['reason'],'unit_work_budget')
        for kw, reason in [({'max_scenarios':0},'scenario_budget'),
                            ({'max_orders_budget':1},'order_budget'),
                            ({'deadline':time.monotonic()-1},'deadline')]:
            result=compare_queues(MARKET,**fixture(),**kw)
            self.assertEqual(result['reason'],reason)
            self.assertIsNone(result['bounds'])
            self.assertEqual(result['scenario_results'],[])

    def test_partial_deadline_never_returns_partial_bounds(self):
        payload = fixture()
        second = copy.deepcopy(payload['scenarios'][0]); second['id'] = 'second'
        payload['scenarios'].append(second)
        # Complete first scenario, then exhaust before the second starts.
        with patch('queue_delta.time.monotonic', side_effect=[0, 0, 0, 0, 2]):
            result = compare_queues(MARKET, **payload, deadline=1)
        self.assertEqual(result['status'], 'unknown')
        self.assertEqual(result['reason'], 'deadline')
        self.assertEqual(len(result['scenario_results']), 1)
        self.assertIsNone(result['bounds'])
        self.assertFalse(result['action_selected'])

    def test_worker_inventory_mismatch_stays_unknown(self):
        payload = fixture(); payload['own_farm']['hands'].append([4, 4])
        result = compare_queues(MARKET, **payload)
        self.assertIn('worker_inventory_count_mismatch', result['reason'])
        self.assertEqual(result['scenario_results'], [])

    def test_negative_private_and_nonfinite_cash_unknown(self):
        for key in ('negative_stock','cash'):
            payload=fixture()
            if key=='cash': payload['own_farm']['money']=float('nan')
            else: payload['own_private']['shed']['MILK']=-1
            self.assertEqual(compare_queues(MARKET,**payload)['status'],'unknown')

    def test_returned_report_does_not_alias_inputs(self):
        payload=fixture(proposed=[['BUY_SEED','WHEAT',1]])
        result=self.compare(payload)
        result['scenario_results'][0]['proposed']['own_farm']['money']=-1
        self.assertEqual(payload['own_farm']['money'],300)

    def test_order_grid_matches_full_market(self):
        # Deterministic crossed small queues, not game seeds or scored matches.
        queues=[[], [['SELL','MILK',3]], [['BUY_PRODUCT','WHEAT',4]],
            [['BUY_SEED','CARROT',2],['HIRE']], [['SELL','CARROT',2],['BUY_ANIMAL','COW',1]],
            [[],['SELL','MILK',5]], [['BUY_LAND'],['HIRE']],
            [['BUY_PRODUCT','FERTILIZER',2],['SELL','FERTILIZER',2]]]
        for p in (0,1):
            for i, own in enumerate(queues):
                for j, rival in enumerate(queues):
                    with self.subTest(seat=p,own=i,rival=j):
                        self.compare(fixture(p,cash=1100 if (i+j)%2 else 200,
                            stock={'MILK':4,'CARROT':3,'WHEAT':2},
                            baseline=own,proposed=queues[(i+1)%len(queues)],
                            rival_stock={'MILK':4,'CARROT':3,'WHEAT':2},
                            rival_orders=rival,capacity=10))

    def test_cli_uses_real_source_and_reports_unknown_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            inp=Path(directory)/'input.json'; out=Path(directory)/'output.json'
            inp.write_text(json.dumps(fixture(proposed=[['BUY_SEED','WHEAT',1]])))
            command=[sys.executable,str(Path(__file__).with_name('queue_delta.py')),
                '--engine-source',str(ENGINE_DIR/'kaggriculture.py'),
                '--input',str(inp),'--output',str(out)]
            run=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)
            result=json.loads(out.read_text()); self.assertEqual(result['status'],'complete_conditional')
            self.assertEqual(result['engine_source_sha256'],MARKET.source_sha256)
            payload=fixture();payload['scenarios']=[];inp.write_text(json.dumps(payload))
            run=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(run.returncode,2,run.stderr)


def main():
    global ENGINE, MARKET, ENGINE_DIR
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine-cache',required=True,type=Path)
    parser.add_argument('--result',type=Path)
    args=parser.parse_args(); ENGINE_DIR=args.engine_cache
    ENGINE=load_full_engine(ENGINE_DIR)
    MARKET=load_market_engine(ENGINE_DIR/'kaggriculture.py')
    started=time.perf_counter()
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(QueueTests))
    summary=dict(tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),
        official_complete_market_calls=FULL_MARKET_CALLS,complete_comparison_cases=CASE_COUNT,
        game_panels=0,game_seeds=0,elapsed_seconds=time.perf_counter()-started,
        engine_sha256=MARKET.source_sha256,
        source_sha256=hashlib.sha256(Path(__file__).with_name('queue_delta.py').read_bytes()).hexdigest(),
        test_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    if args.result: args.result.write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary))
    return 0 if result.wasSuccessful() else 1

if __name__=='__main__': raise SystemExit(main())
