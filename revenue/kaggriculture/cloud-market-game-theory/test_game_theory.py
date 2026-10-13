# SPDX-License-Identifier: Apache-2.0
import copy
from fractions import Fraction
import json
from pathlib import Path
import random
import unittest

from selector import WholePlanSelector
from solver import solve_table


class GameTheoryTests(unittest.TestCase):
    def fixture(self):
        plans=[{'id':'base','sales':[[241,1],[249,1]]},
               {'id':'early','sales':[[241,2]]},{'id':'late','sales':[[249,2]]}]
        obs={'step':241,'player':0,'farms':[{'money':1000},{'money':1000}]}
        action={'farmer':['NORTH'],'hands':[['CARE']], 'market':[['HIRE'],['SELL','STRAWBERRY',1],['BUY_SEED','WHEAT',1]]}
        window={'key':'lot-1','item':'STRAWBERRY','quantity':2,'now':241,'end':249,
                'slot':1,'plans':plans,'deltas':[[0,0],[1,-1],[-1,2]]}
        return obs,action,window

    def test_algebra_only_example(self):
        r=solve_table([[0,0],[4,-1],[-1,4]])
        self.assertEqual(r['weights'],['0','1/2','1/2'])
        self.assertEqual(r['value'],'3/2')

    def test_actual_engine_table_and_negative_column(self):
        r=solve_table([[0,0],[1,-1],[-1,2]])
        self.assertEqual(r['weights'],['0','3/5','2/5'])
        self.assertEqual(r['value'],'1/5')
        self.assertEqual(solve_table([[0,0,0],[1,-1,-1],[-1,2,-2]])['weights'],['1','0','0'])

    def test_pure_and_baseline(self):
        obs,base,w=self.fixture()
        for mode in ('pure','baseline'):
            s=WholePlanSelector(random.Random(1))
            out=s.transform(obs,{},base,window=w,post_unit_shed={'STRAWBERRY':2},feasible=lambda p:True,mode=mode)
            self.assertEqual(out,base);self.assertEqual(s.draws,0)

    def test_whole_plan_persistence_and_detachment(self):
        obs,base,w=self.fixture();original=copy.deepcopy((obs,base,w))
        s=WholePlanSelector(random.Random(1))
        args={'window':w,'post_unit_shed':{'STRAWBERRY':2},'feasible':lambda p:True}
        first=s.transform(obs,{},base,**args)
        for _ in range(10):self.assertEqual(s.transform(obs,{},base,**args),first)
        self.assertEqual(s.draws,1);self.assertEqual((obs,base,w),original)
        self.assertEqual(first['farmer'],base['farmer']);self.assertEqual(first['hands'],base['hands'])
        self.assertEqual(first['market'][0],['HIRE']);self.assertEqual(first['market'][2],['BUY_SEED','WHEAT',1])
        chosen=copy.deepcopy(s.active['plan'])
        completed=max(t for t,q in chosen['sales'] if q)
        for step in range(242,completed+1):
            obs['step']=step
            got=s.transform(obs,{},base,post_unit_shed={'STRAWBERRY':2})
            expected=dict(chosen['sales']).get(step,0)
            self.assertEqual(got['market'][1],['SELL','STRAWBERRY',expected] if expected else [])
        self.assertEqual(s.draws,1)

    def test_all_constituents_feasible(self):
        obs,base,w=self.fixture();s=WholePlanSelector(random.Random(1));seen=[]
        def feasible(p):seen.append(p['id']);return p['id']!='late'
        self.assertEqual(s.transform(obs,{},base,window=w,post_unit_shed={'STRAWBERRY':2},feasible=feasible),base)
        self.assertEqual(seen,['base','early','late']);self.assertEqual(s.draws,0)

    def test_cash_stock_and_terminal_reservations(self):
        obs,base,w=self.fixture()
        for reserve in ({'cash':1001},{'stock':{'STRAWBERRY':1}}):
            s=WholePlanSelector(random.Random(1))
            self.assertEqual(s.transform(obs,{},base,window=w,post_unit_shed={'STRAWBERRY':2},reservations=reserve,feasible=lambda p:True),base)
        w['end']=719
        self.assertEqual(WholePlanSelector().transform(obs,{},base,window=w,post_unit_shed={'STRAWBERRY':2},feasible=lambda p:True),base)

    def test_obstruction_aborts_without_redraw(self):
        obs,base,w=self.fixture();s=WholePlanSelector(random.Random(0))
        s.transform(obs,{},base,window=w,post_unit_shed={'STRAWBERRY':2},feasible=lambda p:True)
        obs['step']=249;base['market'][1]=['BUY_PRODUCT','WHEAT',1]
        self.assertEqual(s.transform(obs,{},base,post_unit_shed={'STRAWBERRY':2}),base)
        self.assertEqual(s.last_decision['reason'],'commitment_aborted');self.assertEqual(s.draws,1)

    def test_private_worlds_same_information_set(self):
        obs,base,w=self.fixture()
        # Evaluator-private worlds differ, while every policy input is identical.
        outputs=[]
        for hidden_shed in ({'STRAWBERRY':0},{'STRAWBERRY':100}):
            simulator={'rival_private':hidden_shed,'public_observation':copy.deepcopy(obs)}
            s=WholePlanSelector(random.Random(9))
            outputs.append((s.transform(simulator['public_observation'],{},base,window=w,
                  post_unit_shed={'STRAWBERRY':2},feasible=lambda p:True),s.active['weights']))
        self.assertEqual(outputs[0],outputs[1])

    def test_exact_oracle_on_small_random_tables(self):
        from scipy.optimize import linprog
        rng=random.Random(7115)
        for _ in range(80):
            rows=[[0]*7]+[[rng.randrange(-20,21) for _ in range(7)] for _ in range(2)]
            answer=solve_table(rows)
            lp=linprog([0,0,0,-1],A_ub=[[-rows[i][j] for i in range(3)]+[1] for j in range(7)],b_ub=[0]*7,
                A_eq=[[1,1,1,0]],b_eq=[1],bounds=[(0,None)]*3+[(None,None)],method='highs')
            self.assertTrue(lp.success);self.assertAlmostEqual(float(Fraction(answer['value'])),-lp.fun)


if __name__=='__main__':unittest.main()
