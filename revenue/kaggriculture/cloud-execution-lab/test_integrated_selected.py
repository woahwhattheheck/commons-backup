# SPDX-License-Identifier: Apache-2.0
"""New integration boundaries only; no accepted suite or game is repeated."""
import copy
import json
from pathlib import Path
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import integrated_selected as I
from test_ordered_selected_sell import OrderedSelectedSellTests, action, sold

RECEIPTS=[]

class IntegratedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        OrderedSelectedSellTests.setUpClass()
        cls.helper=OrderedSelectedSellTests()

    def setup_case(self, step, selected, future=None, shed=None, carried=None):
        obs,cfg,state,env=self.helper.fixture(step, shed, carried)
        obj=I.make_agent()
        route=[action() for _ in range(720)]
        route[step]=copy.deepcopy(selected)
        for t,a in (future or {}).items(): route[t]=copy.deepcopy(a)
        obj.controller.R={'case':route};obj.controller.cur='case'
        obj.budget=I.budget_module.SeedBudget(obj.controller.R)
        return obj,obs,cfg,state,env

    def test_seed_after_selected_plant_and_before_future_plant(self):
        selected=action(['PLANT','WHEAT'], market=[['BUY_SEED','WHEAT',17],['SELL','CARROT',1]])
        future={101:action(['PLANT','WHEAT'])}
        obj,obs,cfg,state,env=self.setup_case(100,selected,future,{'CARROT':1})
        obs['private']['seeds']['WHEAT']=1
        x,y=obs['farms'][0]['farmer'];obs['farms'][0]['tiles'][y][x]=None
        out=obj.transform(obs,cfg,selected)
        self.assertEqual(obj.last_packet['post_unit_observation']['private']['seeds']['WHEAT'],0)
        self.assertEqual(out['market'][0],['BUY_SEED','WHEAT',1])
        self.assertEqual(out['farmer'],selected['farmer'])
        self.helper.advance(state,env,out,100)
        self.assertEqual(state[0].observation['private']['seeds']['WHEAT'],1)
        RECEIPTS.append({'case':'seed_after_current_plant','requested':17,'retained':1})

    def test_seed_does_not_activate_later_hire(self):
        selected=action(market=[['BUY_SEED','WHEAT',17],['HIRE']])
        obj,obs,cfg,state,env=self.setup_case(100,selected)
        obs['farms'][0]['money']=170
        out=obj.transform(obs,cfg,selected)
        self.assertEqual(out,selected)
        self.assertEqual(obj.diagnostics['seed_reason'],'later_economic_order')
        self.helper.advance(state,env,out,100)
        self.assertEqual(state[0].observation['farms'][0]['money'],0)
        RECEIPTS.append({'case':'seed_hire_dependency','preserved':True})

    def test_committed_future_harvest_is_capacity_only(self):
        selected=action()
        obj,obs,cfg,_,_=self.setup_case(21,selected,{22:action(),23:action()},
                                      {'CARROT':94},[{'EGG':2},{}])
        farm=obs['farms'][0]; x,y=farm['farmer']
        farm['tiles'][y][x]=I.m._new_animal('GOOSE',0)
        farm['tiles'][y][x]['yield_units']=4
        target={'at':[x,y],'product':'EGG','op':['HARVEST'],'units':4,'value_now':200}
        plan={'target':target,'phase':'go','steps':1,'home':(x,y),'started':20,
              'unit':0,'window':4,'errand_id':'cap-20-w0'}
        obj.production.plans={0:copy.deepcopy(plan)}
        obj.production._commit(plan,target,obs,0,20,0)
        out=obj.transform(obs,cfg,selected)
        packet=obj.last_packet
        self.assertEqual(sum(e['pending_capacity_units'] for e in packet['arrival_contract']['capacity_events']),4)
        self.assertEqual(sum(e['quantity_delta'] for e in packet['projection']['stock_events'] if e['product']=='EGG'),2)
        self.assertEqual(sold(out,'EGG'),0)
        self.assertEqual(obj.production.plans[0],plan)
        RECEIPTS.append({'case':'pending4_plus_carried2','pending':4,'projected_deposit':2})

    def test_actual_parent_called_once_both_seats_missing_step(self):
        elapsed=[]
        for seat in (0,1):
            obs,cfg,state,env=self.helper.fixture(0)
            if seat: obs=copy.deepcopy(state[1].observation)
            obs.pop('step',None)
            start=time.perf_counter();obj=I.make_agent()
            original=obj.controller.act
            with patch.object(obj.controller,'act',wraps=original) as called:
                out=obj.act(obs,cfg)
                self.assertEqual(called.call_count,1)
            elapsed.append(time.perf_counter()-start)
            self.assertEqual(obj.diagnostics['selected_unit_stages'],1)
            self.assertEqual(out['farmer'],obj.last_selected['farmer'])
            self.assertEqual(out['hands'],obj.last_selected['hands'])
        RECEIPTS.append({'case':'one_parent_cold_both_seats','max_constructor_plus_call_s':max(elapsed)})

    def test_retained_midgame_selected_stage_matches_committed_fixture(self):
        frame=json.loads((I.HERE/'reference/selected-action/claude/cap-midgame-errand.json').read_text())['frames'][0]
        obj=I.make_agent();obs=copy.deepcopy(frame['observation']);selected=frame['selected_action']
        # This fixture supplies an already-selected producer snapshot. No future
        # replay actions or outcomes enter the runtime continuation.
        obj.production.producer_snapshot=lambda post, action:copy.deepcopy(frame['producer_snapshot_post_unit'])
        out=obj.transform(obs,{},selected)
        self.assertEqual(obj.last_packet['post_unit_observation']['private'],frame['post_unit_observation']['private'])
        self.assertEqual(obj.last_packet['arrival_contract'],frame['arrival_contract'])
        self.assertEqual(out['farmer'],selected['farmer'])
        self.assertEqual(out['hands'],selected['hands'])
        RECEIPTS.append({'case':'retained667_post_units_contract','pending_units':4})

    def test_parent_control_reuses_same_selected_production_and_seed_stage(self):
        selected=action(market=[['BUY_SEED','WHEAT',17],['SELL','CARROT',1]])
        obj,obs,cfg,_,_=self.setup_case(100,selected,shed={'CARROT':1})
        obj.sell=False
        with patch.object(obj.execution.seller,'transform',side_effect=AssertionError('seller in parent control')):
            out=obj.transform(obs,cfg,selected)
        self.assertEqual(out['market'],[[],['SELL','CARROT',1]])
        self.assertEqual(obj.diagnostics['status'],'parent_control')
        RECEIPTS.append({'case':'same_producer_seed_parent_control','seller_calls':0})

    def test_current_queue_binding_fallback_and_route_switch_boundary(self):
        selected=action(['PLACE','WHEAT',1],market=[['BUY_PRODUCT','WHEAT',1]])
        obj,obs,cfg,_,_=self.setup_case(225,selected,carried=[{'WHEAT':1},{}])
        fallback=action(['PLACE','WHEAT',1])
        out=obj.transform(obs,cfg,selected,fallback_action=fallback)
        self.assertEqual(out,fallback)
        self.assertEqual(obj.last_packet['projection']['end_step'],225)
        self.assertIn('cash bound',obj.diagnostics['reason'])
        RECEIPTS.append({'case':'purchase_bound_and_switch','fallback':True,'end':225})

if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(IntegratedTests)
    start=time.perf_counter();result=unittest.TextTestRunner(verbosity=2).run(suite)
    data={'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
          'wall_s':time.perf_counter()-start,'cases':RECEIPTS,'full_games':0}
    (I.HERE/'runtime/integrated-selected/TEST-RESULTS.json').write_text(json.dumps(data,indent=2)+'\n')
    raise SystemExit(not result.wasSuccessful())
