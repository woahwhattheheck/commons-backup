# SPDX-License-Identifier: Apache-2.0
"""Native-source regressions against the pinned full official interpreter.

Usage: python test_represented_market.py --package CHECKED_NATIVE --receipt out.json
No network, runner dispatch, legacy materializer or replacement engine.
"""
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
import unittest

from compose import compose_source, git_blob

RESULTS = {'interpreter_calls': 0, 'witnesses': {}, 'release_authorized': False}
PASS = {'farmer': ['PASS'], 'hands': [], 'market': []}


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class MarketAdmission(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = ARGS.package.resolve()
        sys.path.insert(0, str(root))
        cls.source = (root/'frozen_selected.py').read_text()
        cls.candidate = compose_source(cls.source)
        cls.old = types.ModuleType('represented_market_baseline')
        cls.new = types.ModuleType('represented_market_candidate')
        exec(compile(cls.source, str(root/'frozen_selected.py'), 'exec'), cls.old.__dict__)
        exec(compile(cls.candidate, str(root/'frozen_selected.py'), 'exec'), cls.new.__dict__)
        cls.ev = load(root/'checks/reference/evaluator/evaluate.py', 'represented_evaluator')
        cls.engine, hashes = cls.ev.get_engine(root/'checks/reference/engine',
                                             root/'checks/reference/evaluator/loader.py')
        RESULTS['engine_sha256'] = hashes
        RESULTS['native_frozen_blob'] = git_blob(cls.source.encode())
        RESULTS['candidate_frozen_blob'] = git_blob(cls.candidate.encode())

    def fixture(self, seat=0, cash=1000, stock=None, step=1, config=None, shops=()):
        e, S = self.engine, self.ev.Struct
        cfg = S({k: v.get('default') if isinstance(v, dict) else v
                 for k, v in e.specification['configuration'].items()})
        cfg.update(weedSpawnChance=0)
        cfg.update(config or {})
        farms = [e._new_farm(10, cash), e._new_farm(10, cash)]
        market = e._new_market()
        state = []
        for idx in range(2):
            private = e._new_private()
            if idx == seat:
                private['shed'].update(stock or {})
            state.append(S(observation=S(player=idx, step=step, day=step//24,
                                          hour=step%24, farms=farms, private=private,
                                          market=market, town={'unlocked_shops': list(shops)}),
                           action=copy.deepcopy(PASS), status='ACTIVE', reward=0))
        return state, S(configuration=cfg, done=False, info={'seed': 9600803})

    def tick(self, state, env, seat, action, step):
        for s in state:
            s.observation.step = step
            s.action = copy.deepcopy(PASS)
        state[seat].action = copy.deepcopy(action)
        self.engine.interpreter(state, env)
        RESULTS['interpreter_calls'] += 1

    def compare_market(self, orders, *, seat=0, cash=1000, stock=None, step=1,
                       config=None, shops=(), inventory=None, hires=0, params=None):
        state, env = self.fixture(seat,cash,stock,step,config,shops)
        obs = state[seat].observation
        obs.farms[seat]['hires_today'] = hires
        if inventory:
            obs.market['inventory'].update(inventory)
        if params:
            obs.market['params'] = self.engine._resolve_market_params(params)
        f,p,market = copy.deepcopy((obs.farms[seat],obs.private,obs.market))
        original = copy.deepcopy(orders)
        self.new.apply_represented_market(f,p,orders,10,market,env.configuration)
        self.new.advance_represented_market(market,step,shops,env.configuration)
        action = copy.deepcopy(PASS); action['market'] = orders
        self.tick(state,env,seat,action,step)
        self.assertEqual(f,obs.farms[seat])
        self.assertEqual(p,obs.private)
        self.assertEqual(market['inventory'],obs.market['inventory'])
        self.assertEqual(orders,original)
        return f,p,market

    def test_01_unaffordable_requests_do_not_create_goods_or_hands(self):
        for seat in range(2):
            f,p,_ = self.compare_market([['BUY_PRODUCT','WHEAT',2],
                       ['BUY_ANIMAL','GOOSE',1],['HIRE']], seat=seat,cash=0)
            self.assertEqual((p['shed']['WHEAT'],p['shed']['GOOSE'],len(f['hands'])),(0,0,0))

    def test_02_paid_product_animal_seed_hire_and_land_activate(self):
        for seat in range(2):
            f,p,_ = self.compare_market([['BUY_PRODUCT','WHEAT',2],
                        ['BUY_ANIMAL','GOOSE',1],['BUY_SEED','CARROT',2],
                        ['HIRE'],['BUY_LAND']],seat=seat,cash=2000)
            self.assertEqual((p['shed']['WHEAT'],p['shed']['GOOSE'],p['seeds']['CARROT']), (2,1,2))
            self.assertEqual(len(f['hands']),1)
            self.assertIn('NE',f['unlocked_quadrants'])

    def test_03_partial_fills_and_shared_shed_capacity(self):
        for seat in range(2):
            for cash in (25,26,51,52,300,301,500):
                self.compare_market([['BUY_PRODUCT','WHEAT',5],['BUY_ANIMAL','GOOSE',3]],
                                    seat=seat,cash=cash,config={'shedCapacity':3})
            self.compare_market([['BUY_ANIMAL','GOOSE',1],['HIRE']],seat=seat,
                                cash=300,stock={'MILK':100})

    def test_04_ordered_cash_and_fixed_spend(self):
        for seat in range(2):
            for orders in ([['SELL','MILK',1],['HIRE']],
                           [['HIRE'],['SELL','MILK',1]],
                           [['BUY_SEED','CARROT',1],['HIRE']],
                           [['BUY_LAND'],['BUY_PRODUCT','WHEAT',1],['HIRE']],
                           [['BUY_ANIMAL','GOOSE',1],['HIRE']]):
                self.compare_market(orders,seat=seat,cash=20,stock={'MILK':1})

    def test_05_fibonacci_hire_schedule_and_multiplier(self):
        for seat in range(2):
            for hires in (0,2,5,10):
                self.compare_market([['HIRE']]*10,seat=seat,cash=100,hires=hires,
                                    config={'farmHandCostMult':3})

    def test_06_raw_prefix_empty_slots_and_clamped_zero_limit(self):
        for seat in range(2):
            for limit in (0,1,2,10,12):
                f,p,_ = self.compare_market([[],['BUY_ANIMAL','GOOSE',1]] + [['HIRE']]*10,
                           seat=seat,cash=1000,config={'maxMarketOrdersPerTurn':limit})
                self.assertEqual(p['shed']['GOOSE'],int(limit>=2))

    def test_07_malformed_and_unsupported_operations(self):
        orders = [None, 'HIRE', ('HIRE',), ['BUY_PRODUCT','MILK',1],
                  ['BUY_ANIMAL','WHEAT',1], ['SELL','GOOSE',1], ['DISPOSE','GOOSE',1],
                  ['BUY_SEED','CARROT','bad'],['BUY_PRODUCT','WHEAT',-1],['HIRE']]
        for seat in range(2):
            self.compare_market(orders,seat=seat,cash=1000,stock={'GOOSE':1})
            self.compare_market(('HIRE',),seat=seat)

    def test_08_post_buy_quotes_and_floor_admission(self):
        for seat in range(2):
            self.compare_market([['BUY_PRODUCT','WHEAT',6],['SELL','WHEAT',6]],seat=seat,cash=1000)
            self.compare_market([['SELL','MILK',4],['BUY_PRODUCT','FERTILIZER',1],['HIRE']],
                                seat=seat,cash=0,stock={'MILK':4},inventory={'MILK':10075})

    def test_09_known_town_ticks_and_sparse_price_overrides(self):
        for seat in range(2):
            for step in (0,4,8):
                self.compare_market([['BUY_PRODUCT','WHEAT',2]],seat=seat,step=step,
                                    shops=['BAKERY','BAKERY'],params={'WHEAT':{'base':31}})
            self.compare_market([],seat=seat,step=1,config={'townShopSellInterval':0,
                                   'townCenterSellInterval':0},shops=['BAKERY'])

    def event_fixture(self, seat, cash, orders, item='WHEAT', stock=None, hand=False):
        state,env = self.fixture(seat,cash,stock)
        obs = state[seat].observation
        route = [copy.deepcopy(PASS) for _ in range(6)]
        route[1]['market'] = copy.deepcopy(orders)
        if hand:
            route[2]['hands'] = [['PICKUP',item,2]]
            route[4]['hands'] = [['DROP']]
        else:
            route[2]['farmer'] = ['PICKUP',item,2]
            route[4]['farmer'] = ['DROP']
        before = copy.deepcopy((obs,route))
        old = self.old.represented_shed_event(1,2,5,route,obs.farms[seat],obs.private,
                                            env.configuration,orders)
        new = self.new.represented_shed_event(1,2,5,route,obs.farms[seat],obs.private,
                                            env.configuration,orders,obs.market,())
        self.assertEqual((obs,route),before)
        actual = None
        for step in range(1,6):
            start = sum(obs.private['shed'].values())
            self.tick(state,env,seat,route[step],step)
            if step>2 and sum(obs.private['shed'].values())>start and actual is None:
                actual = step
        self.assertEqual(new,actual)
        return old,new,actual

    def test_10_end_to_end_phantom_purchase_horizon_removed(self):
        for seat in range(2):
            for item,op,cash in [('WHEAT','BUY_PRODUCT',0),('GOOSE','BUY_ANIMAL',0),
                                 ('MILK','BUY_PRODUCT',1000)]:
                witness = self.event_fixture(seat,cash,[[op,item,2]],item)
                self.assertEqual(witness,(4,None,None))
                RESULTS['witnesses'][f'phantom_{item}_seat{seat}'] = witness

    def test_11_end_to_end_paid_purchase_horizon_preserved(self):
        for seat in range(2):
            for item,op in [('WHEAT','BUY_PRODUCT'),('GOOSE','BUY_ANIMAL')]:
                witness = self.event_fixture(seat,1000,[[op,item,2]],item)
                self.assertEqual(witness,(4,4,4))
                RESULTS['witnesses'][f'paid_{item}_seat{seat}'] = witness

    def test_12_hire_cannot_create_ghost_worker_but_paid_hire_works(self):
        for seat in range(2):
            for cash in (0,1):
                witness = self.event_fixture(seat,cash,[['HIRE']],stock={'WHEAT':2},hand=True)
                self.assertEqual(witness,(4,4 if cash else None,4 if cash else None))
                RESULTS['witnesses'][f'hire_cash{cash}_seat{seat}'] = witness

    def test_13_unpriced_context_is_conservative(self):
        state,env = self.fixture(cash=26)
        f,p = copy.deepcopy((state[0].observation.farms[0],state[0].observation.private))
        self.new.apply_represented_market(f,p,[['BUY_PRODUCT','WHEAT',1],['HIRE']],10)
        self.assertEqual(p['shed']['WHEAT'],0)
        self.assertEqual(len(f['hands']),0)

    def test_14_randomized_order_tapes_both_seats(self):
        rng = random.Random(20260911)
        menu = [['HIRE'],['BUY_LAND'],[],['BUY_SEED','CARROT',2],['BUY_PRODUCT','WHEAT',4],
                ['BUY_PRODUCT','FERTILIZER',2],['BUY_ANIMAL','GOOSE',2],['SELL','MILK',3],
                ['SELL','WHEAT',2],['BUY_PRODUCT','MILK',2]]
        for seat in range(2):
            for _ in range(100):
                self.compare_market([copy.deepcopy(rng.choice(menu)) for _ in range(rng.randrange(1,14))],
                    seat=seat,cash=rng.choice([0,1,25,51,101,300,500,1000,5000]),
                    stock={'WHEAT':rng.randrange(5),'MILK':rng.randrange(5)},
                    config={'shedCapacity':rng.choice([2,5,100]),
                            'maxMarketOrdersPerTurn':rng.choice([0,1,5,10,12])})

    def test_15_composer_fails_closed_and_preserves_unrelated_source(self):
        with self.assertRaises(ValueError):
            compose_source(self.candidate)
        with self.assertRaises(ValueError):
            compose_source(self.source.replace("private['shed'][order[1]]=private['shed'].get(order[1],0)+max(0,int(order[2]))", 'pass'))
        def method(source,name):
            tree = ast.parse(source); lines=source.splitlines(True)
            node = next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
            return ''.join(lines[node.lineno-1:node.end_lineno])
        for name in ('_funding_trace','funded_minimum_now','seller_choice_rank'):
            self.assertEqual(method(self.source,name),method(self.candidate,name))
        # LIVEPATH's independent copy-only seam and UNITFLOW's unit loop remain present.
        self.assertIn('    f,p=copy.deepcopy(farm),copy.deepcopy(private)\n',self.candidate)
        self.assertIn("        acts=[action.get('farmer',['PASS']),*action.get('hands',[])]",self.candidate)

    def test_16_horizon_ignores_nonexecutable_suffix_sell(self):
        saved = self.new.parent.DECISIONS
        self.new.parent.DECISIONS=[]
        try:
            route=[copy.deepcopy(PASS) for _ in range(24)]
            for action in route:
                action['market']=[['HIRE']]*10+[['SELL','MILK',1]]
            old_end,old = self.old.event_aware_horizon(1,22,route,{'MILK'},['SMOOTHIE_SHOP'],{})
            new_end,new = self.new.event_aware_horizon(1,22,route,{'MILK'},['SMOOTHIE_SHOP'],{})
            self.assertGreater(old_end,old['baseline_end'])
            self.assertEqual(new_end,new['baseline_end'])
            RESULTS['witnesses']['raw_suffix_horizon']={'old':old_end,'new':new_end}
        finally:
            self.new.parent.DECISIONS=saved


    def test_17_future_market_receipts_fund_only_executable_orders(self):
        for seat in range(2):
            state,env=self.fixture(seat=seat,cash=0,stock={'MILK':1})
            obs=state[seat].observation
            route=[copy.deepcopy(PASS) for _ in range(7)]
            route[2]['market']=[['SELL','MILK',1],['BUY_PRODUCT','WHEAT',2]]
            route[3]['farmer']=['PICKUP','WHEAT',2]
            route[5]['farmer']=['DROP']
            predicted=self.new.represented_shed_event(1,3,6,route,obs.farms[seat],
                obs.private,env.configuration,[],obs.market,())
            self.assertEqual(predicted,5)
            for step in range(1,6):
                self.tick(state,env,seat,route[step],step)
            self.assertEqual(obs.private['shed']['WHEAT'],2)

    def test_18_decay_precedes_next_units(self):
        for seat in range(2):
            state,env=self.fixture(seat=seat,cash=0)
            obs=state[seat].observation
            farm=obs.farms[seat];x,y=farm['farmer']
            plant=self.engine._new_plant('CARROT',-4,24)
            plant.update(yield_units=1,max_lifespan_step=1)
            farm['tiles'][y][x]=plant
            route=[copy.deepcopy(PASS) for _ in range(6)]
            route[2]['farmer']=['HARVEST']
            route[4]['farmer']=['DROP']
            old=self.old.represented_shed_event(1,2,5,route,farm,obs.private,env.configuration,[])
            new=self.new.represented_shed_event(1,2,5,route,farm,obs.private,env.configuration,[],obs.market,())
            self.assertEqual((old,new),(4,None))
            for step in range(1,6):
                self.tick(state,env,seat,route[step],step)
            self.assertEqual(obs.private['shed']['CARROT'],0)
            RESULTS['witnesses'][f'decay_seat{seat}']={'old':old,'new':new,'actual':None}

    def test_19_full_shed_and_truncated_purchase_do_not_extend(self):
        for seat in range(2):
            self.assertEqual(self.event_fixture(seat,1000,[[],['BUY_PRODUCT','WHEAT',2]],
                                               stock={'MILK':100}),(4,None,None))
            state,env=self.fixture(seat=seat,cash=1000,config={'maxMarketOrdersPerTurn':1})
            obs=state[seat].observation
            route=[copy.deepcopy(PASS) for _ in range(6)]
            route[2]['farmer']=['PICKUP','WHEAT',2]
            route[4]['farmer']=['DROP']
            new=self.new.represented_shed_event(1,2,5,route,obs.farms[seat],obs.private,
                env.configuration,[[],['BUY_PRODUCT','WHEAT',2]],obs.market,())
            self.assertIsNone(new)

    def test_20_unmodeled_day_boundary_declines_extension(self):
        state,env=self.fixture(cash=1000,step=22)
        obs=state[0].observation
        obs.private['inventories'][0]['WHEAT']=2
        route=[copy.deepcopy(PASS) for _ in range(27)]
        route[25]['farmer']=['DROP']
        new=self.new.represented_shed_event(22,23,26,route,obs.farms[0],obs.private,
                                           env.configuration,[],obs.market,())
        self.assertIsNone(new)


def main():
    global ARGS
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package',type=Path,required=True)
    parser.add_argument('--receipt',type=Path,required=True)
    ARGS=parser.parse_args()
    started=time.perf_counter()
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(MarketAdmission))
    RESULTS.update(tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),
                   optimized=not __debug__,elapsed_seconds=time.perf_counter()-started)
    ARGS.receipt.write_text(json.dumps(RESULTS,indent=2,sort_keys=True)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__=='__main__':
    main()
