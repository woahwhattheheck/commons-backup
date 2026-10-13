# SPDX-License-Identifier: Apache-2.0
"""Exact native optimizer differential, tie, callback and official market tests.

TITAN_SIEVE_RUNTIME must point to the unchanged extracted b567 current archive.
No Kaggle install, network, production mutation, or optimized-away assertions.
"""
from __future__ import annotations
import ast
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import random
import sys
import types
import unittest
from unittest.mock import patch

from patch_selected_incumbent import SOURCE_BLOB, git_blob, transform

ROOT = Path(os.environ.get('TITAN_SIEVE_RUNTIME', '.')).resolve()
PINS = {
    'checks/test_engine_semantics.py': '5fc139742d1fb8cc757e9bf58c033794b7f8ec5f',
    'checks/reference/engine/utils.py': '91c8822ee6201ba4a5a8416c7dbe34f95dd61c87',
    'selected_sell_core.py': SOURCE_BLOB,
    'frozen_selected.py': 'fc7baf5c179818a55037f6a61d92984d81d1a21c',
    'mechanics.py': '044a4f9c0a4a44dde10ada57563238bcaf82075d',
    'reference/decision/decision.py': '2931aa55831204fbb473ab85a6f5b81ec947fcf7',
    'checks/reference/engine/kaggriculture.py': '3c202c7ee921da239356789e266b694635103fc4',
    'checks/reference/engine/kaggriculture.json': 'b354d06b742fe48402513792253f1a5c29366b20',
    'checks/reference/evaluator/evaluate.py': '1fb6b655bb4ca1e1684be165a8ef513e2e6c2325',
    'checks/reference/evaluator/loader.py': '23948e10cfc3d32f46c9abb1321b0d8fc8db21d5',
}
METRICS = {'differential_pairs': 0, 'baseline_score_calls': 0,
           'candidate_score_calls': 0, 'market_pairs': 0,
           'official_market_calls': 0, 'synthetic_tie_cases': 0}


def authenticate():
    for name, digest in PINS.items():
        data = (ROOT / name).read_bytes()
        if digest is not None and git_blob(data) != digest:
            raise ValueError('runtime input mismatch: ' + name)
    sys.path.insert(0, str(ROOT))


def load_source(source, name):
    module = types.ModuleType(name)
    module.__file__ = str(ROOT / 'selected_sell_core.py')
    exec(compile(source, module.__file__, 'exec'), module.__dict__)
    return module


def example(**updates):
    result = dict(item='MILK', quantity=12, inventory=10030, params=None,
                  shops=['SMOOTHIE_SHOP'] * 4, config={}, now=4,
                  dates=[4,5,8], reference=((4,6),(8,6)),
                  rival_quantity=2, minimum_now=0, last=718)
    result.update(updates)
    return result


def cases(count=800):
    rng = random.Random(20260911)
    products = ['WHEAT','CARROT','TOMATO','STRAWBERRY','MELON','EGG','MILK','WOOL','FERTILIZER']
    shops = [[], ['SMOOTHIE_SHOP'], ['SMOOTHIE_SHOP']*4,
             ['BAKERY','PIZZA_SHOP','BRUNCH_SPOT','YARN_STORE','ICE_CREAM_SHOP',
              'PET_CAFE','SMOOTHIE_SHOP','FARMERS_MARKET']]
    for i in range(count):
        q = rng.choice([0,1,2,6,12,24,48,100])
        now = rng.choice([0,1,4,20,23,710,715,718])
        horizon = rng.choice([0,1,2,3,5,8])
        end = now+horizon
        dates = sorted(set([now,now+min(1,horizon),now+min(3,horizon),end]))
        first = rng.randrange(q+1)
        reference = ((now,q),) if end==now else ((now,first),(end,q-first))
        yield example(item=rng.choice(products),quantity=q,
                      inventory=rng.choice([9900,9990,10000,10020,10050,10075,10076,10077,10100]),
                      shops=rng.choice(shops),now=now,dates=dates,reference=reference,
                      rival_quantity=rng.choice([0,1,2,6,24,100]),
                      minimum_now=rng.choice([0,first]),
                      last=end if i%3==0 else end+20,
                      config={'townShopSellInterval':rng.choice([1,4,7]),
                              'townCenterSellInterval':rng.choice([1,12,24])})


class IncumbentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        authenticate()
        cls.source = (ROOT / 'selected_sell_core.py').read_bytes()
        cls.candidate_source = transform(cls.source)
        cls.base = load_source(cls.source, 'sieve_base')
        cls.candidate = load_source(cls.candidate_source, 'sieve_candidate')

    def compare(self, kwargs, callback=None):
        outputs=[];traces=[];counts=[]
        for module in (self.base,self.candidate):
            trace=[];calls=[0]
            original=module.MarketPath.score
            def score(instance,*args,**kw):
                calls[0]+=1
                return original(instance,*args,**kw)
            def capacity(plan):
                trace.append(tuple(plan))
                return callback(tuple(plan),len(trace))
            kw=copy.deepcopy(kwargs)
            if callback is not None:kw['capacity_ok']=capacity
            with patch.object(module.MarketPath,'score',score):
                outputs.append(module.optimize_lot(**kw))
            traces.append(trace);counts.append(calls[0])
        self.assertEqual(outputs[0],outputs[1],kwargs)
        self.assertEqual(traces[0],traces[1],kwargs)
        self.assertLessEqual(counts[1],counts[0],kwargs)
        METRICS['differential_pairs']+=1
        METRICS['baseline_score_calls']+=counts[0]
        METRICS['candidate_score_calls']+=counts[1]
        return outputs[0],counts

    def test_01_exact_source_contract(self):
        self.assertEqual(git_blob(self.source),SOURCE_BLOB)
        self.assertEqual(git_blob(self.candidate_source),'5e6be72cda2e71a1aff6c68b13a0a934b2964a36')
        with self.assertRaises(ValueError):transform(self.source+b'\n')
        with self.assertRaises(ValueError):transform(self.candidate_source)

    def test_02_only_strict_optimizer_changes(self):
        a=ast.parse(self.source);b=ast.parse(self.candidate_source)
        self.assertEqual(len(a.body),len(b.body))
        for left,right in zip(a.body,b.body):
            if getattr(left,'name',None)!='optimize_lot':
                self.assertEqual(ast.dump(left),ast.dump(right))
        old=next(n for n in a.body if getattr(n,'name',None)=='optimize_lot')
        new=next(n for n in b.body if getattr(n,'name',None)=='optimize_lot')
        old_branch=next(n for n in old.body if isinstance(n,ast.If) and isinstance(n.test,ast.BoolOp))
        new_branch=next(n for n in new.body if isinstance(n,ast.If) and isinstance(n.test,ast.BoolOp))
        self.assertEqual(ast.dump(ast.Module(body=old_branch.orelse,type_ignores=[])),
                         ast.dump(ast.Module(body=new_branch.orelse,type_ignores=[])))

    def test_03_active_frozen_binding(self):
        # Authenticate the actual consumer seam, not standalone scheduler.py.
        import frozen_selected
        import selected_sell_core
        self.assertIs(frozen_selected.optimize_lot,selected_sell_core.optimize_lot)
        self.assertEqual(git_blob(Path(selected_sell_core.__file__).read_bytes()),SOURCE_BLOB)

    def test_04_physical_price_differential(self):
        for kw in cases():self.compare(kw)

    def test_05_capacity_callback_order_and_state(self):
        for kw in list(cases(80)):
            self.compare(kw,lambda plan,index:index==1 or index%4!=0)

    def test_06_forced_feasibility_untouched(self):
        for kw in list(cases(60)):
            self.compare(kw,lambda plan,index:index!=1 and index%3!=0)

    def test_07_alternative_acceptance_untouched(self):
        for kw in list(cases(40)):
            for rule in ('expected_downside','minimax_regret'):
                kw['config'].update(sellAcceptanceRule=rule,sellDownsideBound=100,
                    sellScenarioWeights={'no_rival':2,'observed_paired':3})
                _,counts=self.compare(kw)
                self.assertEqual(counts[0],counts[1])

    def test_08_unknown_rule_uses_strict(self):
        kw=example();kw['config']['sellAcceptanceRule']='not-a-rule'
        self.compare(kw)

    def fake_compare(self, first, second, *, second_plan=None, mutant=None):
        reference=((4,2),)
        p1=((4,0),);p2=second_plan or ((4,0),(5,0),(7,2))
        table={p1:first,p2:second}
        class FakePath:
            def __init__(self,*args):pass
            def score(self,plan,quantity,rival,alignment,terminal=False):
                if rival==0:index=0
                elif isinstance(rival,tuple):index=3 if rival[0][0]==5 else 4
                else:index=1 if alignment=='paired' else 2
                value=0 if tuple(plan)==reference else table.get(tuple(plan),[-1]*5)[index]
                return value,value,0,0
        kwargs=example(quantity=2,now=4,dates=[4,5,7],reference=reference,rival_quantity=1)
        outputs=[]
        modules=(self.base,self.candidate) if mutant is None else (self.base,load_source(mutant,'sieve_mutant'))
        for module in modules:
            with patch.object(module,'MarketPath',FakePath):outputs.append(module.optimize_lot(**kwargs))
        self.assertEqual(outputs[0][0],p2)
        if mutant is None:self.assertEqual(outputs[0],outputs[1])
        else:self.assertNotEqual(outputs[0],outputs[1])
        METRICS['synthetic_tie_cases']+=1

    def test_09_equal_primary_better_sum(self):
        self.fake_compare([1]*5,[1,2,2,2,2])

    def test_10_later_scenario_equal_primary(self):
        self.fake_compare([1]*5,[3,1,2,2,2])

    def test_11_equal_sum_better_now_quantity(self):
        self.fake_compare([1]*5,[1]*5,second_plan=((4,1),))

    def test_12_rounding_boundary_survives(self):
        self.fake_compare([1.000000004]*5,[0.999999996,2,2,2,2])
        self.fake_compare([1.000000004]*5,[3,0.999999996,2,2,2])

    def test_13_first_bound_inclusive_mutant_killed(self):
        mutant=self.candidate_source.replace(b'round(first_score[0]-baseline[0][0],8) < best_key[0]',
                                              b'round(first_score[0]-baseline[0][0],8) <= best_key[0]')
        self.fake_compare([1]*5,[1,2,2,2,2],mutant=mutant)

    def test_14_later_bound_inclusive_mutant_killed(self):
        mutant=self.candidate_source.replace(b'round(delta,8) < best_key[0]',b'round(delta,8) <= best_key[0]')
        self.fake_compare([1]*5,[3,1,2,2,2],mutant=mutant)

    def test_15_unrounded_first_bound_mutant_killed(self):
        mutant=self.candidate_source.replace(b'round(first_score[0]-baseline[0][0],8) < best_key[0]',
                                              b'first_score[0]-baseline[0][0] < best_key[0]')
        self.fake_compare([1.000000004]*5,[0.999999996,2,2,2,2],mutant=mutant)

    def test_16_unrounded_later_bound_mutant_killed(self):
        mutant=self.candidate_source.replace(b'round(delta,8) < best_key[0]',b'delta < best_key[0]')
        self.fake_compare([1.000000004]*5,[3,0.999999996,2,2,2],mutant=mutant)

    def test_17_discriminating_reduction(self):
        kw=example(item='CARROT',quantity=24,inventory=10000,
            shops=list(self.base.m.SHOPS),now=710,dates=[710,711,713,715],
            reference=((710,19),(715,5)),rival_quantity=0)
        result,counts=self.compare(kw)
        self.assertEqual(counts,[547,199])
        self.assertEqual(result[1]['worst_relative_gain'],15)

    def test_18_official_market_state_both_seats(self):
        sys.path.insert(0,str(ROOT/'checks'))
        from test_engine_semantics import EngineSemantics
        EngineSemantics.setUpClass();fixture=EngineSemantics();e=fixture.engine
        vectors=[]
        for item in ('MILK','CARROT','FERTILIZER'):
            for inventory in (10000,10075,10100):
                vectors.append(example(item=item,quantity=12,inventory=inventory,
                    now=4,dates=[4,5,7],reference=((4,6),(7,6)),last=7))
        for kw in vectors:
            (plan,_),_=self.compare(kw)
            model=self.base.MarketPath(kw['item'],kw['inventory'],None,kw['shops'],kw['config'],4,7)
            for seat in (0,1):
                for rival,alignment in [(0,'paired'),(2,'paired'),(2,'after'),(((5,2),),'paired'),(((6,2),),'paired')]:
                    expected=model.score(plan,12,rival,alignment,True)
                    snapshots=[]
                    for module in (self.base,self.candidate):
                        selected=module.optimize_lot(**kw)[0]
                        stock=[2,2];stock[seat]=12
                        state,env=fixture.fixture(item=kw['item'],stock=tuple(stock),
                            inventory=kw['inventory'],shops=kw['shops'],step=4)
                        for step in range(4,8):
                            own=dict(selected).get(step,0)
                            other=(dict(rival).get(step,0) if isinstance(rival,tuple)
                                   else rival if step==4 else 0)
                            for s in state:s.action={'farmer':['PASS'],'hands':[],'market':[]}
                            state[seat].action['market']=[['SELL',kw['item'],own]]
                            state[1-seat].action['market']=([[]] if alignment=='after' else [])+[['SELL',kw['item'],other]]
                            e._process_market(state,env);e._town_consume(env,state,step)
                            METRICS['official_market_calls']+=1
                        own_cash=fixture.cash(state)[seat];other_cash=fixture.cash(state)[1-seat]
                        remaining=state[seat].observation.private['shed'][kw['item']]
                        self.assertEqual((own_cash-other_cash,own_cash,other_cash,remaining),expected)
                        snapshots.append(copy.deepcopy([dict(s.observation) for s in state]))
                    self.assertEqual(snapshots[0],snapshots[1])
                    METRICS['market_pairs']+=1


if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(IncumbentTests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    receipt={'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
             'optimized':not __debug__,'metrics':METRICS,'pins':PINS,
             'source_blob':SOURCE_BLOB,'candidate_blob':git_blob(transform((ROOT/'selected_sell_core.py').read_bytes()))}
    print(json.dumps(receipt,sort_keys=True))
    sys.exit(0 if result.wasSuccessful() else 1)
