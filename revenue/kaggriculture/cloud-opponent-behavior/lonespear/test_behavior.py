"""Source-bound public predictor and official-engine market regressions."""
from __future__ import annotations
import copy
import itertools
import json
import os
from pathlib import Path
import unittest

import behavior
import engine_cases

HERE = Path(__file__).resolve().parent
KAG = HERE.parents[1]
SOURCE = Path(os.environ.get('TITAN_LONESPEAR_SOURCE', KAG/'cloud-policy-portfolio/revision2/vendor/opponents/sources/lonespear-v18/main_v18.py'))
EVALUATOR = Path(os.environ.get('TITAN_EVALUATOR', KAG/'cloud-eval/evaluate.py'))
ENGINE = Path(os.environ.get('TITAN_ENGINE', KAG/'cloud-policy-portfolio/vendor/engine'))



class SourceAndEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = engine_cases.source(SOURCE)
        cls.evaluator = engine_cases.load(EVALUATOR, 'iris_eval')
        cls.engine, cls.engine_hashes = cls.evaluator.get_engine(ENGINE)
        cls.frame = json.loads((HERE/'base-frame.json').read_text())

    def fixture(self, animals=8, plants=20, empty=20, money=1000, hands=0, hires=0, hour=0, actor=1):
        obs = copy.deepcopy(self.frame['observation'])
        obs.update(player=1-actor, day=12, hour=hour, step=288+hour)
        tiles = [dict(kind='PASTURE', animal='COW') for _ in range(animals)]
        tiles += [dict(kind='PLANT', crop='WHEAT') for _ in range(plants)]
        tiles += [None]*empty + ['LOCKED']*(100-len(tiles)-empty)
        obs['farms'][actor].update(money=money, hands=[[4,4] for _ in range(hands)],
                                   hires_today=hires, tiles=[tiles[i:i+10] for i in range(0,100,10)])
        return obs

    def test_exact_requests_against_original_source_grid(self):
        count=0
        for hour, cash, staff, actor in itertools.product((0,1,2,3,23), (0,40,41,60,61,1000), (0,6,10,11), (0,1)):
            obs=self.fixture(hour=hour,money=cash,hands=staff,hires=staff,actor=actor)
            pred=behavior.predict(obs, actor=actor)
            orders=engine_cases.source_orders(self.source,obs,actor,self.engine._new_private())
            n=sum(o==['HIRE'] for o in orders)
            self.assertEqual(pred['status'],'known')
            self.assertEqual(pred['hire_requests'],n)
            self.assertTrue(all(o==['HIRE'] for o in orders[:n]))
            count+=1
        self.assertEqual(count,240)

    def test_exact_prefix_fills_against_official_engine(self):
        for cash, staff, mult, limit, actor in itertools.product((41,61,100,1000),(0,6,9),(1,3),(1,10),(0,1)):
            obs=self.fixture(money=cash,hands=staff,hires=staff,actor=actor)
            cfg={'farmHandCostMult':mult,'maxMarketOrdersPerTurn':limit}
            pred=behavior.predict(obs,cfg,actor=actor)
            private=[self.engine._new_private(),self.engine._new_private()]
            private[actor]['inventories']=[{} for _ in range(staff+1)]
            actions=[{'market':[]},{'market':[]}]
            actions[actor]['market']=[['HIRE'] for _ in range(pred['hire_requests'])]
            got=engine_cases.run_market(self.engine,obs,private,actions,cfg)
            self.assertEqual(got['farms'][actor]['hires_today']-staff,pred['hire_prefix_fills'])
            self.assertEqual(got['after_cash'][actor],pred['cash_after_hire_prefix'])

    def test_private_feed_is_an_interval(self):
        for cash, stock in itertools.product((40,60,61,1000),(0,1,5,16,17,100)):
            obs=self.fixture(money=cash)
            pred=behavior.predict(obs)
            private=self.engine._new_private(); private['shed']['WHEAT']=stock
            orders=engine_cases.source_orders(self.source,obs,1,private)
            values=[o[2] for o in orders if len(o)==3 and o[:2]==['BUY_PRODUCT','WHEAT']]
            self.assertLessEqual(sum(values),pred['feed_request_units']['upper'])
            self.assertGreaterEqual(sum(values),pred['feed_request_units']['lower'])
            self.assertFalse(pred['feed_quantity_known'])

    def test_private_and_labels_do_not_enter_prediction(self):
        obs=self.fixture(); a=behavior.predict(obs)
        obs['private']={'shed':{'WHEAT':99999},'seeds':{'WHEAT':8888}}
        obs['action']={'market':[['HIRE']]}; obs['seed']=1234; obs['outcome']='WIN'
        obs['farms'][1]['private']={'shed':{'WHEAT':1}}
        self.assertEqual(a,behavior.predict(obs))

    def test_public_negative_controls(self):
        for kwargs, reason in (({'hour':3},'late_hour'),({'money':40},'cash_threshold'),
                               ({'hires':11,'hands':11},'daily_hire_target'),({'hands':11},'already_staffed')):
            pred=behavior.predict(self.fixture(**kwargs))
            self.assertEqual(pred['hire_requests'],0)
            self.assertEqual(pred['reason'],reason)

    def test_unknowns_are_not_zero_predictions(self):
        for key in ('money','hires_today','hands','tiles'):
            obs=self.fixture(); del obs['farms'][1][key]
            self.assertEqual(behavior.predict(obs)['status'],'unknown')
        for value in (True,-1,float('nan'),float('inf'),'100'):
            obs=self.fixture(money=value)
            self.assertEqual(behavior.predict(obs)['status'],'unknown')

    def test_source_counts_of_empty_and_unoccupied_assets(self):
        obs=self.fixture(animals=2,plants=5,empty=10)
        obs['farms'][1]['tiles'][9][8]={'kind':'PASTURE'}
        obs['farms'][1]['tiles'][9][9]={'kind':'COOP','animal':'GOOSE'}
        pred=behavior.predict(obs)
        survey=self.source._survey(obs['farms'][1]['tiles'],12)
        self.assertEqual(pred['public']['animals'],survey['n_animals'])
        self.assertEqual(pred['workload'],survey['n_animals']*3+survey['plants']+len(survey['empty'])//3)

    def test_history_distinguishes_resets_and_inconsistent_counts(self):
        old=self.fixture(hands=6,hires=6); new=copy.deepcopy(old)
        new['step']+=1; new['hour']+=1; new['farms'][1]['hires_today']=8
        new['farms'][1]['hands'] += [[4,4],[4,4]]
        self.assertEqual(behavior.observed_fill(old,new,actor=1)['fills'],2)
        new['day']+=1
        self.assertEqual(behavior.observed_fill(old,new,actor=1)['status'],'unknown')
        new['day']-=1; new['farms'][1]['hands'].pop()
        self.assertEqual(behavior.observed_fill(old,new,actor=1)['status'],'unknown')

    def test_response_preserves_workers_and_reserved_stock(self):
        action={'farmer':['MOVE','NORTH'],'hands':[['PASS']], 'market':[['SELL','WHEAT',5]]}
        pred=behavior.predict(self.fixture())
        before=copy.deepcopy(action)
        out=behavior.propose_delayed_wheat_sale(action,pred,shed_wheat=10,retained_wheat=5)
        self.assertTrue(out['changed']); self.assertEqual(out['sale_slot'],7)
        self.assertEqual(out['action']['farmer'],action['farmer'])
        self.assertEqual(out['action']['hands'],action['hands'])
        self.assertEqual(action,before)
        self.assertFalse(behavior.propose_delayed_wheat_sale(action,pred,shed_wheat=9,retained_wheat=5)['changed'])

    def test_response_keeps_other_sale_indices(self):
        pred=behavior.predict(self.fixture(hands=6,hires=6))
        action={'farmer':['PASS'],'hands':[], 'market':[['SELL','WHEAT',50],['SELL','FERTILIZER',23]]}
        out=behavior.propose_delayed_wheat_sale(action,pred,shed_wheat=50,retained_wheat=0)
        self.assertTrue(out['changed']); self.assertEqual(out['sale_slot'],6)
        self.assertEqual(out['action']['market'][1],action['market'][1])
        self.assertEqual(out['action']['market'][6],action['market'][0])
        self.assertEqual(out['action']['market'][0],['PASS'])

    def test_response_unknown_and_slot_limit_fallback(self):
        action={'market':[['SELL','WHEAT',5]]}
        pred=behavior.predict(self.fixture())
        for slots in (0,1,7,'10',None,True):
            out=behavior.propose_delayed_wheat_sale(action,pred,shed_wheat=5,retained_wheat=0,max_orders=slots)
            self.assertFalse(out['changed'])
        pred['hire_requests']=None
        self.assertFalse(behavior.propose_delayed_wheat_sale(action,pred,shed_wheat=5,retained_wheat=0)['changed'])

    def test_response_returns_full_fallback_for_unmodeled_queues(self):
        pred=behavior.predict(self.fixture())
        for market in ([],[['HIRE']], [['SELL','WHEAT',5],['HIRE']], [['SELL','MILK',5]]):
            action={'farmer':['PASS'],'market':market}
            out=behavior.propose_delayed_wheat_sale(action,pred,shed_wheat=10,retained_wheat=0)
            self.assertFalse(out['changed']); self.assertEqual(out['action'],action)


if __name__=='__main__':
    unittest.main(verbosity=2)
