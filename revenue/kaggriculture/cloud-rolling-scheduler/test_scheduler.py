"""Job/executor contracts and discriminating official-engine integration cases."""
from __future__ import annotations
import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from scheduler import Operation as O, Visit as V, JointPlan, decode_day, remaining, neighbors, search, capital_signature, deadline_feasible
from policy import Continuation, RollingAgent, fork_parent, market_with_workers

ROOT=Path(__file__).resolve().parent.parent
CACHE=Path(os.environ.get('T03_ENGINE_DIR',str(ROOT/'cloud-eval/.engine-cache')))


def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module);return module


def visit(name,target,action,step=0,deadline=23,worker=0):
    return V(name,target,(O(tuple(action),step,step,deadline),),worker)


class EngineCases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (CACHE/'kaggriculture.py').exists():
            raise unittest.SkipTest('Set T03_ENGINE_DIR to the pre-staged pinned engine; no test downloader is used')
        cls.ev=load(ROOT/'cloud-eval/evaluate.py','t03_test_evaluator')
        cls.engine,_=cls.ev.get_engine(CACHE)
        cls.oracle=load(ROOT/'cloud-service-value/oracle.py','t03_test_oracle')
        cls.arlene=load(ROOT/'cloud-frontier-policy/next-panel/vendor/arlene.py','t03_test_arlene')

    def observation(self,step=0,positions=((4,4),)):
        e=self.engine;farm=e._new_farm(10,1000);farm['farmer']=list(positions[0]);farm['hands']=[list(p) for p in positions[1:]]
        private=e._new_private();private['inventories']=[{} for _ in positions]
        return {'step':step,'day':step//24,'hour':step%24,'player':0,'farms':[farm],
                'private':private,'market':e._new_market(),'town':{'unlocked_shops':[]}}

    def test_waypoint_birth_phase_matches_all_four_routes(self):
        e=self.engine
        for key,route in self.arlene.routes().items():
            for day in range(19,30):
                obs=self.observation(day*24)
                plan=JointPlan(decode_day(route,day))
                reference=e._new_farm(10,1000);private=e._new_private()
                for step in (day*24,day*24+1):
                    obs.update(step=step,hour=step%24)
                    units=plan.actions(obs)
                    original=[route[step].get('farmer',['PASS']),*route[step].get('hands',[])]
                    for i,action in enumerate(units):
                        e._apply_unit_action(obs['farms'][0],obs['private'],i,action,10,day,24)
                    for i,action in enumerate(original):
                        e._apply_unit_action(reference,private,i,action,10,day,24)
                    for order in route[step].get('market',[]):
                        if order and order[0]=='HIRE':
                            obs['farms'][0]['hands'].append(e._spawn_hand(obs['farms'][0],10));obs['private']['inventories'].append({})
                            reference['hands'].append(e._spawn_hand(reference,10));private['inventories'].append({})
                    self.assertEqual(obs['farms'][0]['farmer'],reference['farmer'],(key,step))
                    self.assertEqual(obs['farms'][0]['hands'],reference['hands'],(key,step))

    def test_actual_position_not_old_movement_offset(self):
        obs=self.observation(10,((1,1),))
        plan=JointPlan({0:(visit('v',(2,1),['CARE'],10),)})
        self.assertEqual(plan.actions(obs),[['EAST']])
        obs['step']=11;obs['farms'][0]['farmer']=[2,0] # an externally changed observed position
        self.assertEqual(plan.actions(obs),[['SOUTH']])
        obs['step']=12;obs['farms'][0]['farmer']=[2,1]
        self.assertEqual(plan.actions(obs),[['CARE']])

    def test_fork_does_not_consume_live_jobs(self):
        obs=self.observation();q={0:(visit('v',(4,4),['CARE']),)};p=JointPlan(q);f=p.fork()
        f.actions(obs);self.assertEqual(len(p.pending()[0]),1);self.assertEqual(f.pending()[0],())

    def test_same_step_idempotent_and_rewind_rejected(self):
        obs=self.observation(2);p=JointPlan({0:(visit('a',(4,4),['CARE'],2),visit('b',(4,4),['HARVEST'],3))})
        self.assertEqual(p.actions(obs),p.actions(obs));self.assertEqual(p.cursor[0],[1,0])
        obs['step']=1
        with self.assertRaises(ValueError):p.actions(obs)

    def test_expired_job_is_not_silently_credited(self):
        obs=self.observation(5);p=JointPlan({0:(visit('late',(4,4),['PLANT','WHEAT'],0,4),)})
        self.assertEqual(p.actions(obs),[['PASS']]);self.assertEqual(p.missed,['late/0']);self.assertEqual(p.completed,[])

    def test_new_weed_is_dependency_and_plant_waits_for_real_state(self):
        obs=self.observation();obs['farms'][0]['tiles'][4][4]={'kind':'WEED'}
        p=JointPlan({0:(visit('plant',(4,4),['PLANT','WHEAT']),)})
        self.assertEqual(p.actions(obs),[['DIG']]);self.assertEqual(p.completed,[])
        obs['step']=1;obs['farms'][0]['tiles'][4][4]=None
        self.assertEqual(p.actions(obs),[['PLANT','WHEAT']]);self.assertEqual(p.completed,['plant/0'])

    def test_nonexistent_hands_never_act(self):
        obs=self.observation();p=JointPlan({0:(),7:(visit('future',(4,4),['CARE'],worker=7),)})
        self.assertEqual(p.actions(obs),[['PASS']]);self.assertEqual(len(p.pending()[7]),1)

    def test_release_prevents_early_input_pickup(self):
        obs=self.observation(1);p=JointPlan({0:(visit('input',(4,4),['PICKUP','WHEAT',2],3),)})
        self.assertEqual(p.actions(obs),[['PASS']]);obs['step']=3;self.assertEqual(p.actions(obs),[['PICKUP','WHEAT',2]])

    def test_decoder_preserves_every_nonmove_nonpass_operation(self):
        for key,route in self.arlene.routes().items():
            for day in (19,20,27,28,29):
                decoded=decode_day(route,day)
                got=sorted((op.original_step,worker,op.action) for worker,rows in decoded.items() for v in rows for op in v.operations if op.action[0] not in ('ARRIVE','PASS'))
                expected=[]
                for step in range(day*24,min(day*24+24,719)):
                    for worker,a in enumerate([route[step].get('farmer',['PASS']),*route[step].get('hands',[])]):
                        if a and a[0] not in ('NORTH','SOUTH','EAST','WEST','PASS'):expected.append((step,worker,tuple(a)))
                self.assertEqual(got,sorted(expected),key)

    def test_neighbor_preserves_job_multiset_and_capital_owner(self):
        obs=self.observation(10,((4,4),(0,0)))
        q={0:(visit('crop',(4,4),['PLANT','WHEAT'],10),visit('milk',(0,0),['HARVEST'],11)),1:(visit('care',(0,0),['CARE'],10,worker=1),)}
        out=neighbors(q,obs)
        self.assertTrue(out)
        for _,rows in out:
            self.assertEqual(sorted(v.id for r in rows.values() for v in r),['care','crop','milk'])
            self.assertIn('crop',[v.id for v in rows[0]])

    def test_parent_market_recomputes_same_turn_drop(self):
        obs=self.observation(718);obs['private']['inventories'][0]={'MILK':5}
        p=fork_parent(self.arlene.Agent());original=copy.deepcopy(p.R[p.cur][718])
        a=market_with_workers(p,obs,[['DROP']])
        self.assertIn(['SELL','MILK',5],a['market']);self.assertEqual(p.R[p.cur][718],original)
        self.assertEqual(obs['private']['inventories'][0],{'MILK':5})

    def test_exact_engine_resource_order(self):
        obs=self.observation(706,((4,4),(4,4)));obs['private']['inventories'][0]={'MILK':5}
        p=JointPlan({0:(visit('drop',(4,4),['DROP'],706,718),),1:(visit('pickup',(4,4),['PICKUP','MILK',5],706,718,1),)})
        def plan(o):
            a=p.actions(o);return {'farmer':a[0],'hands':a[1:],'market':[]}
        r=self.oracle.simulate_bundle(self.engine,obs,{},plan,end_step=706)
        self.assertEqual(r['private']['inventories'],[{}, {'MILK':5}]);self.assertEqual(r['private']['shed']['MILK'],0)

    def test_reassignment_can_create_real_terminal_cash(self):
        obs=self.observation(706,((4,4),(0,0)));obs['farms'][0]['tiles'][0][0]=self.engine._new_animal('COW',0);obs['farms'][0]['tiles'][0][0]['yield_units']=6
        q={0:(visit('harvest',(0,0),['HARVEST'],706,718),visit('drop0',(4,4),['DROP'],706,718)),
           1:(visit('care',(0,0),['CARE'],706,718,1),visit('drop1',(4,4),['DROP'],706,718,1))}
        def evaluate(queues):
            plan=JointPlan(queues)
            def action(o):
                a=plan.actions(o);return {'farmer':a[0],'hands':a[1:],'market':[['SELL','MILK',100]]}
            r=self.oracle.simulate_bundle(self.engine,obs,{},action,end_step=718)
            r['missed_jobs']=plan.missed+[v.id for row in plan.pending().values() for v in row]
            return r
        original=copy.deepcopy(obs)
        base=evaluate(q);found=search(q,obs,evaluate,max_candidates=8,budget_seconds=2)
        self.assertGreater(found.value,base['cash_gain']);self.assertNotEqual(found.label,'incumbent')
        self.assertEqual(capital_signature(found.receipt['farm'],found.receipt['private']),capital_signature(base['farm'],base['private']))
        self.assertEqual(obs,original)

    def test_missed_capital_proposal_cannot_buy_score(self):
        obs=self.observation(706,((4,4),(0,0)))
        q={0:(visit('h',(0,0),['HARVEST'],706,718),),1:()}
        base=self.oracle.simulate_bundle(self.engine,obs,{}, {},end_step=706)
        calls=[]
        def evaluate(queues):
            result=copy.deepcopy(base);result['cash_gain']=1000 if calls else 0
            if calls:result['farm']['tiles'][0][0]=self.engine._new_plant('WHEAT',29,24)
            calls.append(1);return result
        result=search(q,obs,evaluate,max_candidates=2,budget_seconds=2)
        self.assertEqual(result.label,'incumbent');self.assertEqual(result.value,0)

    def test_late_result_cannot_replace_incumbent(self):
        obs=self.observation(706,((4,4),(0,0)))
        q={0:(visit('h',(0,0),['HARVEST'],706,718),),1:()}
        base=self.oracle.simulate_bundle(self.engine,obs,{}, {},end_step=706)
        calls=[]
        def evaluate(queues):
            result=copy.deepcopy(base);result['cash_gain']=1000 if calls else 0;calls.append(1);return result
        with patch('scheduler.time.perf_counter',side_effect=[0,.1,.8,.9]):
            result=search(q,obs,evaluate,max_candidates=2,budget_seconds=.7)
        self.assertEqual(result.label,'incumbent');self.assertTrue(result.exhausted)

    def test_zero_candidates_retains_complete_reference(self):
        obs=self.observation();base=self.oracle.simulate_bundle(self.engine,obs,{}, {},end_step=0)
        calls=[]
        def evaluate(q):calls.append(q);return base
        result=search({0:()},obs,evaluate,max_candidates=0)
        self.assertEqual(len(calls),1);self.assertEqual(result.label,'incumbent')

    def test_parent_prefix_unchanged(self):
        obs=self.observation();raw=self.arlene.Agent();candidate=RollingAgent(self.arlene,self.engine,self.oracle)
        self.assertEqual(candidate.act(obs,{}),raw.act(obs));self.assertEqual(candidate.events,[])

    def test_travel_deadline_bound_rejects_impossible_insert(self):
        obs=self.observation(710,((4,4),))
        self.assertFalse(deadline_feasible({0:(visit('far',(0,0),['HARVEST'],710,718),visit('return',(4,4),['DROP'],710,718))},obs))
        self.assertTrue(deadline_feasible({0:(visit('near',(4,3),['HARVEST'],710,718),)},obs))

    def test_waypoint_uses_movement_decision_not_extra_pass(self):
        obs=self.observation(710,((4,4),))
        q={0:(visit('waypoint',(4,3),['ARRIVE'],710,710),)}
        self.assertTrue(deadline_feasible(q,obs))
        p=JointPlan(q);self.assertEqual(p.actions(obs),[['NORTH']]);self.assertEqual(p.pending()[0],())

    def test_invalid_budget_rejected(self):
        with self.assertRaises(ValueError):search({}, {}, lambda q: {},budget_seconds=0)
        with self.assertRaises(ValueError):search({}, {}, lambda q: {},max_candidates=-1)


if __name__=='__main__':unittest.main()
