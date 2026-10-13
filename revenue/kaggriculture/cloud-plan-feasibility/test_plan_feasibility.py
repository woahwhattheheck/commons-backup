# SPDX-License-Identifier: Apache-2.0
"""New fixed-slot integration cases; no games, panels or policy tuning."""
from __future__ import annotations
import argparse
import ast
from copy import deepcopy
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

from plan_feasibility import PlanFeasibility, PlanConflict, fixed_market

HERE = Path(__file__).resolve().parent
PARSER = argparse.ArgumentParser()
PARSER.add_argument('--lab', type=Path, default=HERE.parent / 'cloud-execution-lab')
PARSER.add_argument('--selector-dir', type=Path, default=HERE.parent / 'cloud-market-game-theory')
PARSER.add_argument('--continuation-dir', type=Path, default=HERE.parent / 'cloud-plan-continuation')
PARSER.add_argument('--engine-cache', type=Path, required=True)
PARSER.add_argument('--report', type=Path)
ARGS, REMAINING = PARSER.parse_known_args()
for directory in (ARGS.lab, ARGS.selector_dir, ARGS.continuation_dir):
    sys.path.insert(0, str(directory.resolve()))
from selected_action_sell import ProjectionLedger
from selector import WholePlanSelector
from continuation import ContinuationPlanSelector


def source(path):
    data = path.read_bytes()
    return {'sha256': hashlib.sha256(data).hexdigest(),
            'git_blob': hashlib.sha1(f'blob {len(data)}\0'.encode() + data).hexdigest(),
            'bytes': len(data)}


def load_engine():
    """Load unchanged engine and actual upstream seed helper, entirely offline."""
    utils_path = ARGS.engine_cache / 'utils.py'
    helper = next(n for n in ast.parse(utils_path.read_text()).body
                  if isinstance(n, ast.FunctionDef) and n.name == 'resolve_episode_seed')
    namespace = {'Any': Any, 'Callable': Callable, 'random': random}
    exec(compile(ast.Module(body=[helper], type_ignores=[]), str(utils_path), 'exec'), namespace)
    package = types.ModuleType('kaggle_environments')
    utils = types.ModuleType('kaggle_environments.utils')
    utils.resolve_episode_seed = namespace['resolve_episode_seed']
    sys.modules['kaggle_environments'] = package
    sys.modules['kaggle_environments.utils'] = utils
    spec = importlib.util.spec_from_file_location('plan_official_engine', ARGS.engine_cache / 'kaggriculture.py')
    engine = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(engine)
    return engine


ENGINE = load_engine()
ENGINE_CASES = []
PARITY_CASES = 0
WITNESS = []


class Struct(dict):
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__


def fixture(now=10, cash=1000, shed=None, seat=0):
    cfg = {'episodeSteps': 720, 'turnsPerDay': 24, 'shedCapacity': 100,
           'maxMarketOrdersPerTurn': 10, 'farmHandCostMult': 1, 'boardSize': 10}
    farms = [dict(money=cash, hires_today=0, farmer=[4, 4], hands=[],
                  unlocked_quadrants=['NW'], tiles=[[None]*10 for _ in range(10)]) for _ in range(2)]
    stock = {'CARROT': 2} if shed is None else shed
    private = dict(shed=deepcopy(stock), seeds={}, inventories=[{}])
    obs = {'step': now, 'day': now//24, 'hour': now % 24, 'player': seat,
           'farms': farms, 'private': private,
           'market': {'inventory': {p: 10000 for p in ENGINE.PRODUCTS},
                      'prices': {}, 'params': None},
           'town': {'unlocked_shops': []}}
    action = {'farmer': ['PASS'], 'hands': [], 'market': [['SELL', 'CARROT', 2]]}
    return obs, cfg, action, deepcopy(stock)


def make(obs=None, cfg=None, action=None, shed=None, *, end=12, events=None,
         future=None, reservations=None, contract=None):
    if obs is None:
        obs, cfg, action, shed = fixture()
    now = obs.get('step', obs['day']*cfg['turnsPerDay']+obs['hour'])
    projection = {'observed_step': now, 'end_step': end, 'stock_events': events or [],
                  'future_market': ({t: [] for t in range(now+1, end+1)}
                                    if future is None else future)}
    return PlanFeasibility(ProjectionLedger, obs, cfg, action, post_unit_shed=shed,
                           projection=projection, arrival_contract=contract,
                           reservations=reservations)


def plan(*rows):
    return {'id': 'test', 'sales': [list(row) for row in rows]}


def context(checker, *, end=12, quantity=2):
    return dict(now=checker._now(), item='CARROT', slot=0, end=end,
                remaining_quantity=quantity, observation=deepcopy(checker._obs),
                configuration=deepcopy(checker._cfg), post_unit_shed=deepcopy(checker._shed),
                reservations=checker.selector_reservations())


def engine_market(obs, cfg, queue, *, rival=None):
    state = []
    shared = deepcopy(obs)
    for seat in range(2):
        private = deepcopy(obs['private']) if seat == obs['player'] else dict(shed={'CARROT': 20}, seeds={}, inventories=[{}])
        observation = Struct(shared, private=private, player=seat)
        state.append(Struct(observation=observation,
                            action={'market': deepcopy(queue if seat == obs['player'] else rival or [])}))
    # The engine's two observations share public objects, just as in interpreter state.
    for s in state:
        s.observation.farms = shared['farms']
        s.observation.market = shared['market']
    before = deepcopy(state[obs['player']].observation.private['shed'])
    cash_before = [farm['money'] for farm in shared['farms']]
    hires_before = shared['farms'][obs['player']]['hires_today']
    ENGINE._process_market(state, Struct(configuration=cfg))
    own = state[obs['player']]
    record = {'seat': obs['player'], 'queue': queue, 'rival_queue': rival or [],
              'before_shed': before, 'after_shed': deepcopy(own.observation.private['shed']),
              'own_cash': own.observation.farms[obs['player']]['money'],
              'rival_cash': own.observation.farms[1-obs['player']]['money'],
              'own_cash_before': cash_before[obs['player']],
              'rival_cash_before': cash_before[1-obs['player']],
              'hires_before': hires_before,
              'hires_after': own.observation.farms[obs['player']]['hires_today']}
    ENGINE_CASES.append(record)
    return record


class BridgeTests(unittest.TestCase):
    def test_fixed_queue_preserves_positions_and_inputs(self):
        queue = [['SELL','CARROT',1], ['BUY_SEED','WHEAT',1], ['SELL','CARROT',1], ['SELL','MILK',3]]
        saved = deepcopy(queue)
        self.assertEqual(fixed_market(queue, 'CARROT', 2, 2), [[], queue[1], ['SELL','CARROT',2], queue[3]])
        self.assertEqual(queue, saved)

    def test_occupied_fixed_slot_and_reserved_clear(self):
        with self.assertRaises(PlanConflict):
            fixed_market([['HIRE']], 'CARROT', 1, 0)
        with self.assertRaises(PlanConflict):
            fixed_market([['SELL','CARROT',2]], 'CARROT', 0, 0, reserved_slots=(0,))
        self.assertEqual(fixed_market([['HIRE']], 'CARROT', 0, 0), [['HIRE']])

    def test_legal_complete_plan(self):
        p = make()
        self.assertIs(p.admit(plan((10,0),(12,2)), item='CARROT', slot=0, end=12, quantity=2), True)
        self.assertEqual(p.last_markets[10], [[]])
        self.assertEqual(p.last_markets[12], [['SELL','CARROT',2]])

    def test_full_quantity_not_engine_clamped(self):
        p = make()
        self.assertIs(p.admit(plan((12,3)), item='CARROT', slot=0, end=12, quantity=3), False)
        self.assertEqual(p.last_check['reason'], 'planned_sale_exceeds_unreserved_stock')

    def test_quantity_and_date_validation(self):
        for bad in [plan((12,1)), plan((12,1),(12,1)), plan((13,2)), plan((12,-2)), plan((True,2))]:
            with self.subTest(bad=bad):
                self.assertIs(make().admit(bad,item='CARROT',slot=0,end=12,quantity=2), False)

    def test_missing_future_date_is_unknown(self):
        p = make(future={12: []})
        self.assertIsNone(p.admit(plan((12,2)), item='CARROT',slot=0,end=12,quantity=2))
        self.assertEqual(p.last_check['reason'], 'missing_future_market_date')

    def test_projection_does_not_cover_plan(self):
        p = make(end=11)
        self.assertIsNone(p.admit(plan((12,2)),item='CARROT',slot=0,end=12,quantity=2))

    def test_current_projection_disagreement(self):
        p = make(future={10: [], 11: [], 12: []})
        self.assertIsNone(p.admit(plan((12,2)),item='CARROT',slot=0,end=12,quantity=2))

    def test_stock_reservation_retained_at_terminal(self):
        obs,cfg,a,s = fixture(now=718,shed={'CARROT':3})
        p = make(obs,cfg,a,s,end=718,reservations={'stock':{'CARROT':2}})
        self.assertIs(p.admit(plan((718,2)),item='CARROT',slot=0,end=718,quantity=2), False)
        self.assertIs(p.admit(plan((718,1)),item='CARROT',slot=0,end=718,quantity=1), True)

    def test_after_market_deposit_not_early_sale_stock(self):
        obs,cfg,a,s = fixture(now=716,shed={}); a['market']=[]
        ev=[{'step':717,'phase':'after_market','product':'CARROT','quantity_delta':2}]
        p=make(obs,cfg,a,s,end=718,events=ev)
        self.assertIs(p.admit(plan((717,2)),item='CARROT',slot=0,end=718,quantity=2), False)
        self.assertIs(p.admit(plan((718,2)),item='CARROT',slot=0,end=718,quantity=2), True)

    def test_ordered_deposit_and_withdrawal(self):
        obs,cfg,a,s=fixture(now=716,shed={'WHEAT':90,'CARROT':10});a['market']=[['SELL','CARROT',10]]
        ev=[{'step':717,'phase':'before_market','product':'MILK','quantity_delta':10},
            {'step':717,'phase':'before_market','product':'WHEAT','quantity_delta':-10}]
        p=make(obs,cfg,a,s,end=717,events=ev)
        self.assertIsNone(p.admit(plan((717,10)),item='CARROT',slot=0,end=717,quantity=10))
        self.assertIs(p.admit(plan((716,10)),item='CARROT',slot=0,end=717,quantity=10), True)
        p=make(obs,cfg,a,s,end=717,events=ev[::-1])
        self.assertIs(p.admit(plan((717,10)),item='CARROT',slot=0,end=717,quantity=10), True)

    def test_pending_capacity_does_not_create_sale_stock(self):
        obs,cfg,a,s=fixture(shed={});a['market']=[]
        contract={'observed_step':10,'capacity_events':[dict(owner='producer',errand_id='lot',step=12,
          phase='before_market',pending_capacity_units=2,units_total=2,guaranteed_stock_units=0,contingent=True)]}
        p=make(obs,cfg,a,s,contract=contract)
        self.assertIs(p.admit(plan((12,2)),item='CARROT',slot=0,end=12,quantity=2), False)

    def test_cash_lower_bound_failure_is_unknown_not_impossible(self):
        obs,cfg,a,s=fixture(cash=0,shed={'CARROT':1});cfg['farmHandCostMult']=10
        a['market']=[['SELL','CARROT',1],['HIRE']]
        p=make(obs,cfg,a,s,end=10)
        self.assertIsNone(p.admit(plan((10,1)),item='CARROT',slot=0,end=10,quantity=1))
        actual=engine_market(obs,cfg,a['market'])
        self.assertGreater(actual['own_cash'],0)
        self.assertEqual(actual['hires_after'], actual['hires_before'] + 1)
        WITNESS.append({'case':'conservative_cash_not_impossibility','verdict':p.last_check,'actual_market':actual})

    def test_cash_funded_prefix_and_unfunded_reordering(self):
        obs,cfg,a,s=fixture(cash=0,shed={'CARROT':1});a['market']=[['SELL','CARROT',1],['HIRE']]
        p=make(obs,cfg,a,s,end=10)
        self.assertIs(p.admit(plan((10,1)),item='CARROT',slot=0,end=10,quantity=1), True)
        self.assertIsNone(p.admit(plan((10,1)),item='CARROT',slot=2,end=10,quantity=1))

    def test_cash_schema_conversion(self):
        res={'cash':[{'step':10,'phase':'before_market','minimum':4},
                     {'step':12,'phase':'after_market','minimum':30}], 'stock':{'MILK':1}}
        p=make(reservations=res)
        self.assertEqual(p.selector_reservations(), {'cash':4,'stock':{'MILK':1}})
        self.assertEqual(res['cash'][1]['minimum'],30)

    def test_stale_context_is_unknown(self):
        p=make();ctx=context(p);ctx['observation']['farms'][0]['money']+=1
        self.assertIsNone(p.continuation(plan((12,2)),ctx))
        ctx=context(p);ctx['reservations']['cash']=1
        self.assertIsNone(p.continuation(plan((12,2)),ctx))

    def test_snapshot_and_callback_inputs_do_not_mutate(self):
        obs,cfg,a,s=fixture();p=make(obs,cfg,a,s)
        before=deepcopy((obs,cfg,a,s));ctx=context(p);saved=deepcopy(ctx)
        self.assertIs(p.continuation(plan((12,2)),ctx), True)
        self.assertEqual(ctx,saved);self.assertEqual((obs,cfg,a,s),before)
        a['market'].clear();self.assertEqual(p._action['market'],[['SELL','CARROT',2]])

    def test_completed_plan_restores_later_inherited_sales(self):
        obs,cfg,a,s=fixture(shed={'CARROT':3})
        p=make(obs,cfg,a,s,future={11:[],12:[['SELL','CARROT',1]]})
        self.assertIs(p.admit(plan((10,2)),item='CARROT',slot=0,end=12,quantity=2), True)
        self.assertNotIn(12,p.last_markets)

    def test_actual_wrapper_retires_changed_continuation(self):
        obs,cfg,a,s=fixture();p=make(obs,cfg,a,s)
        plans=[plan((10,2)),plan((12,2))]
        window=dict(key='retained',item='CARROT',quantity=2,now=10,end=12,slot=0,plans=plans,deltas=[[0],[1]])
        actor=ContinuationPlanSelector(WholePlanSelector(random.Random(1)))
        first=actor.transform(obs,cfg,a,window=window,post_unit_shed=s,
             reservations=p.selector_reservations(),continuation_feasible=p.continuation,
             feasible=lambda q:p.admit(q,item='CARROT',slot=0,end=12,quantity=2))
        self.assertEqual(first['market'],[[]]);self.assertEqual(actor.draws,1)
        obs2=deepcopy(obs);obs2.update(step=11,hour=11)
        event=[{'step':12,'phase':'before_market','product':'CARROT','quantity_delta':-2}]
        q=make(obs2,cfg,a,s,events=event)
        result=actor.transform(obs2,cfg,a,post_unit_shed=s,reservations=q.selector_reservations(),
                               continuation_feasible=q.continuation)
        self.assertEqual(result,a);self.assertIsNone(actor.active);self.assertEqual(actor.draws,1)
        self.assertEqual(actor.last_decision['reason'],'continuation_infeasible')
        WITNESS.append({'case':'changed_actual_remaining_stock','first_market':first['market'],
                        'fallback_market':result['market'],'draws':actor.draws,'decision':actor.last_decision})

    def test_official_market_complete_fills_both_seats(self):
        for seat in (0,1):
            for item in ('CARROT','MILK'):
                for quantity in (1,2,5):
                    for rival in ([],[['SELL','CARROT',2]]):
                        with self.subTest(seat=seat,item=item,quantity=quantity,rival=rival):
                            obs,cfg,a,s=fixture(shed={item:quantity+1},seat=seat)
                            a['market']=[[],['BUY_SEED','WHEAT',1],["SELL",item,quantity]]
                            p=make(obs,cfg,a,s,end=10,reservations={'stock':{item:1}})
                            self.assertIs(p.admit(plan((10,quantity)),item=item,slot=2,end=10,quantity=quantity),True)
                            actual=engine_market(obs,cfg,p.last_markets[10],rival=rival)
                            self.assertEqual(actual['after_shed'][item],1)

    def test_actual_selector_fixed_queue_correspondence(self):
        global PARITY_CASES
        queues=[[],[['SELL','CARROT',1]], [[],['SELL','CARROT',2]],
                [['SELL','CARROT',1],['HIRE'],['SELL','CARROT',1]],
                [['SELL','MILK',2],[],['SELL','CARROT',2]]]
        for queue in queues:
            for slot in range(4):
                for due in (0,1,2):
                    obs,cfg,a,s=fixture(shed={'CARROT':2});a['market']=deepcopy(queue)
                    active_plan=plan((10,due),(12,2-due))
                    if due==2:active_plan=plan((10,2))
                    window=dict(key='parity',item='CARROT',quantity=2,now=10,end=12,slot=slot,
                                plans=[plan((10,2)),active_plan],deltas=[[0],[1]])
                    actor=WholePlanSelector(random.Random(1))
                    actual=actor.transform(obs,cfg,a,window=window,post_unit_shed=s,feasible=lambda _:True)
                    try:expected=fixed_market(queue,'CARROT',due,slot)
                    except PlanConflict:self.assertEqual(actual,a)
                    else:self.assertEqual(actual['market'],expected)
                    PARITY_CASES+=1

    def test_missing_buy_cost_bound_remains_unknown(self):
        obs,cfg,a,s=fixture();a['market']=[['BUY_PRODUCT','WHEAT',1],['SELL','CARROT',2]]
        p=make(obs,cfg,a,s,end=10)
        self.assertIsNone(p.admit(plan((10,2)),item='CARROT',slot=1,end=10,quantity=2))
        p=make(obs,cfg,a,s,end=10,reservations={'order_cost_bounds':[{'step':10,'slot':0,'max_cash_cost':100}]})
        self.assertIs(p.admit(plan((10,2)),item='CARROT',slot=1,end=10,quantity=2),True)

    def test_terminal_and_horizon_bounds(self):
        self.assertIsNone(make(end=20).admit(plan((20,2)),item='CARROT',slot=0,end=20,quantity=2))
        self.assertIs(make().admit(plan((719,2)),item='CARROT',slot=0,end=719,quantity=2),False)


if __name__=='__main__':
    started=time.perf_counter()
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(BridgeTests))
    report={'schema':'plan-feasibility-tests-v1','tests':result.testsRun,'failures':len(result.failures),
      'errors':len(result.errors),'passed':result.wasSuccessful(),'seconds':time.perf_counter()-started,
      'official_market_calls':len(ENGINE_CASES),'selector_queue_comparisons':PARITY_CASES,
      'game_panels':0,'source':{'bridge':source(HERE/'plan_feasibility.py'),
          'test_runner':source(Path(__file__).resolve()),
          'mechanics':source(ARGS.lab/'mechanics.py'),
          'receipts':source(ARGS.lab/'reference/decision/decision.py'),
          'ledger':source(ARGS.lab/'selected_action_sell.py'),'core':source(ARGS.lab/'selected_sell_core.py'),
          'solver':source(ARGS.selector_dir/'solver.py'),'selector':source(ARGS.selector_dir/'selector.py'),
          'continuation':source(ARGS.continuation_dir/'continuation.py')},
      'engine':{n:source(ARGS.engine_cache/n) for n in ('kaggriculture.py','kaggriculture.json','utils.py')},
      'witnesses':WITNESS,'market_cases':ENGINE_CASES}
    if ARGS.report:
        ARGS.report.parent.mkdir(parents=True,exist_ok=True)
        ARGS.report.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
