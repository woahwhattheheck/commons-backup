# SPDX-License-Identifier: Apache-2.0
"""Execute with --native pointing to the authenticated complete native fixture."""
from __future__ import annotations
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import sys
import tempfile
import types
import unittest

AP=argparse.ArgumentParser(); AP.add_argument('--native',type=Path,required=True)
ARGS, REST=AP.parse_known_args(); NATIVE=ARGS.native.resolve()
sys.path.insert(0,str(NATIVE))
import f1_spill as lane
import compose_native as composer

PINS={'kaggriculture.py':'3c202c7ee921da239356789e266b694635103fc4',
      'kaggriculture.json':'b354d06b742fe48402513792253f1a5c29366b20',
      'utils.py':'91c8822ee6201ba4a5a8416c7dbe34f95dd61c87'}
for name,expected in PINS.items():
    if composer.blob((NATIVE/'checks/reference/engine'/name).read_bytes())!=expected:
        raise ValueError('official source authentication failed: '+name)
loader_path=NATIVE/'checks/reference/evaluator/loader.py'
if composer.blob(loader_path.read_bytes())!='23948e10cfc3d32f46c9abb1321b0d8fc8db21d5':
    raise ValueError('loader authentication failed')
spec=importlib.util.spec_from_file_location('f1_engine_loader',loader_path)
loader=importlib.util.module_from_spec(spec);spec.loader.exec_module(loader)
ENGINE,HASHES=loader.get_engine(NATIVE/'checks/reference/engine')
TRANSITIONS=0

def execute(state,env):
    global TRANSITIONS
    TRANSITIONS+=1
    ENGINE.interpreter(state,env)


def fixture(seat=0,step=71,shed=100,held=1,actor=0):
    cfg=loader.Struct({k:v.get('default') if isinstance(v,dict) else v
                       for k,v in ENGINE.specification['configuration'].items()})
    cfg.seed=17; cfg.weedSpawnChance=0
    env=loader.Struct(configuration=cfg,done=False,info={})
    state=[loader.Struct(observation=loader.Struct(),action={},status='ACTIVE',reward=0)
           for _ in (0,1)]
    execute(state,env)
    for s in state:s.observation.step=step
    obs=state[seat].observation;farm=obs.farms[seat]
    farm['farmer']=[1,1]
    if actor:
        farm['hands']=[[1,1]]; farm['hires_today']=1
    obs.private['inventories']=[{} for _ in range(actor+1)]
    obs.private['inventories'][actor]={'FERTILIZER':held}
    obs.private['shed']={'CARROT':shed}
    tile=ENGINE._new_plant('WHEAT',0,24)
    tile.update(watered_today=True,yield_units=2,consecutive_unwatered=0)
    farm['tiles'][1][1]=tile
    action={'farmer':['PASS'],'hands':[['PASS']]*actor,'market':[]}
    return state,env,action


def paired(seat=0,orders=None,actor=0):
    state,env,action=fixture(seat=seat,actor=actor)
    if orders is not None:action['market']=orders
    obs=copy.deepcopy(state[seat].observation)
    original=copy.deepcopy((obs,action));report=[]
    arm=lane.apply_spill(obs,action,env.configuration,enabled=True,report=report)
    if (obs,action)!=original:raise AssertionError('input mutation')
    outputs=[]
    for selected in (action,arm):
        ss,ee=copy.deepcopy((state,env))
        for i,s in enumerate(ss):s.action=selected if i==seat else {'farmer':['PASS'],'hands':[],'market':[]}
        execute(ss,ee);outputs.append((ss,ee))
    return action,arm,outputs,report


class Certificate(unittest.TestCase):
    def test_tail_boundary_and_prefix(self):
        p={'shed':{'WHEAT':99},'inventories':[{'FERTILIZER':1}]}
        self.assertIsNone(lane.discarded_tail(p,[],0))
        p['inventories'][0]['FERTILIZER']=2
        self.assertIsNotNone(lane.discarded_tail(p,[],0))
        self.assertIsNone(lane.discarded_tail(p,[['SELL','WHEAT',1]],0))
    def test_raw_slots_not_compacted(self):
        p={'shed':{'CARROT':100},'inventories':[{'FERTILIZER':1}]}
        q=[[]]*10+[['SELL','CARROT',100]]
        self.assertIsNotNone(lane.discarded_tail(p,q,0))
        self.assertIsNone(lane.discarded_tail(p,q,0,max_orders=11))
    def test_inventory_order(self):
        p={'shed':{'CARROT':98},'inventories':[{'WHEAT':2,'FERTILIZER':1}]}
        self.assertIsNotNone(lane.discarded_tail(p,[],0))
        p['inventories']=[{'FERTILIZER':1,'WHEAT':2}]
        self.assertIsNone(lane.discarded_tail(p,[],0))
    def test_worker_order(self):
        p={'shed':{},'inventories':[{'WHEAT':100},{'FERTILIZER':1}]}
        self.assertIsNotNone(lane.discarded_tail(p,[],1))
        p['inventories'].reverse()
        self.assertIsNone(lane.discarded_tail(p,[],0))
    def test_invalid_fail_closed(self):
        good={'shed':{'CARROT':100},'inventories':[{'FERTILIZER':1}]}
        for value in (True,-1,1.5,'1',None):
            p=copy.deepcopy(good);p['inventories'][0]['FERTILIZER']=value
            self.assertIsNone(lane.discarded_tail(p,[],0))
        for q in ([['SELL','CARROT','3']],[['SELL','CARROT',True]],{},[['UNKNOWN']]):
            self.assertIsNone(lane.discarded_tail(good,q,0))
        p=copy.deepcopy(good);p['inventories']=[p['shed']]
        self.assertIsNone(lane.discarded_tail(p,[],0))
    def test_exhaustive_transfer_conservation(self):
        checked=0
        for shed in (0,50,97,98,99,100,105):
          for prior in (0,1,5,50,100):
           for before in (0,1,5):
            for held in (1,2,4):
             for sold in (0,1,3,100):
              p={'shed':{'CARROT':shed},'inventories':[{'WHEAT':prior},{'EGG':before,'FERTILIZER':held,'MILK':7}]}
              cert=lane.discarded_tail(p,[['SELL','CARROT',sold]],1)
              if cert is None:continue
              for actual in {0,min(sold,shed)}:
               b=copy.deepcopy(p);a=copy.deepcopy(p)
               for priv in (b,a):priv['shed']['CARROT']-=actual
               a['inventories'][1]['FERTILIZER']-=1
               if not a['inventories'][1]['FERTILIZER']:del a['inventories'][1]['FERTILIZER']
               ENGINE._drop_inventories_to_shed(b,100);ENGINE._drop_inventories_to_shed(a,100)
               self.assertEqual(b,a);checked+=1
        self.assertGreater(checked,1000)
        print('ordered-transfer comparisons',checked)


class Gameplay(unittest.TestCase):
    def test_off_identity(self):
        self.assertIs(lane.apply_spill(None,None,None),None)
    def test_actual_engine_eod_inventory_exact_both_seats_workers(self):
        for seat in (0,1):
         for actor in (0,1):
          parent,arm,outs,report=paired(seat,actor=actor)
          self.assertIsNot(parent,arm);self.assertEqual(report[-1]['reason'],'proposed')
          b,a=(out[0][seat].observation for out in outs)
          self.assertEqual(b.private,a.private)
          self.assertEqual(b.farms[seat]['money'],a.farms[seat]['money'])
          bf,af=copy.deepcopy(b.farms[seat]),copy.deepcopy(a.farms[seat])
          self.assertEqual(af['tiles'][1][1]['fertilized_until_day'],4)
          af['tiles'][1][1]['fertilized_until_day']=-1
          self.assertEqual(bf,af)
    def test_harvested_bonus_and_filled_sale(self):
        for seat in (0,1):
         parent,arm,outs,report=paired(seat)
         cash=[];wheat=[]
         for ss,ee in outs:
          # Both arms follow identical future work and sell every harvested unit.
          for step,cmd in ((72,['WEST']),(73,['WEST']),(74,['WEST']),(75,['NORTH']),
                           (76,['NORTH']),(77,['NORTH']),(78,['WATER']),(79,['HARVEST']),
                           (80,['SOUTH']),(81,['SOUTH']),(82,['SOUTH']),
                           (83,['EAST']),(84,['EAST']),(85,['EAST']),(86,['DROP'])):
           for i,s in enumerate(ss):
            s.observation.step=step
            s.action={'farmer':cmd if i==seat else ['PASS'],'hands':[],
                      'market':([['SELL','WHEAT',100]] if step==86 else [['SELL','CARROT',100]] if step==80 else []) if i==seat else []}
           execute(ss,ee)
           if step==79:wheat.append(ss[seat].observation.private['inventories'][0].get('WHEAT',0))
          cash.append(ss[seat].observation.farms[seat]['money'])
         self.assertEqual(wheat,[3,4]);self.assertGreater(cash[1],cash[0])
    def test_sell_space_and_tail_slots(self):
        for seat in (0,1):
         p,a,_,_=paired(seat,[['SELL','CARROT',1]])
         self.assertIs(p,a)
         p,a,outs,_=paired(seat,[[]]*10+[['SELL','CARROT',100]])
         self.assertIsNot(p,a)
         self.assertEqual(outs[0][0][seat].observation.private,outs[1][0][seat].observation.private)
    def test_no_future_water_window_no_spend(self):
        state,env,action=fixture();o=state[0].observation
        for updates in ({'fertilized_until_day':4},{'yield_units':6},
                        {'planted_day':0,'max_lifespan_step':72},{'crop':'CARROT'}):
         obs=copy.deepcopy(o);obs.farms[0]['tiles'][1][1].update(updates)
         self.assertIs(lane.apply_spill(obs,action,env.configuration,enabled=True),action)
    def test_no_real_pass_or_carried_fert(self):
        state,env,action=fixture();o=state[0].observation
        for cmd in (['WATER'],['WEST'],['HARVEST'],[],['PASS','extra']):
         a=dict(action,farmer=cmd);self.assertIs(lane.apply_spill(o,a,env.configuration,enabled=True),a)
        o.private['inventories'][0]={}
        self.assertIs(lane.apply_spill(o,action,env.configuration,enabled=True),action)
    def test_future_day_final_and_config_guards(self):
        state,env,action=fixture();o=state[0].observation
        for step in (70,696,718,719,True,-1):
         obs=copy.deepcopy(o);obs.step=step
         self.assertIs(lane.apply_spill(obs,action,env.configuration,enabled=True),action)
        for cfg in ({'turnsPerDay':12},{'boardSize':8},{'episodeSteps':721}):
         self.assertIs(lane.apply_spill(o,action,cfg,enabled=True),action)
    def test_later_harvest_prevents_fertilize(self):
        state,env,action=fixture(actor=1);o=state[0].observation
        o.private['inventories']=[{'FERTILIZER':1},{}];action['hands']=[['HARVEST']]
        self.assertIs(lane.apply_spill(o,action,env.configuration,enabled=True),action)
    def test_later_water_collateral_rejected(self):
        state,env,action=fixture(actor=1);o=state[0].observation
        o.private['inventories']=[{'FERTILIZER':1},{}];action['hands']=[['WATER']]
        o.farms[0]['tiles'][1][1]['watered_today']=False
        self.assertIs(lane.apply_spill(o,action,env.configuration,enabled=True),action)
    def test_multiworker_at_most_one_change_and_no_input_mutation(self):
        state,env,action=fixture(actor=1);o=state[0].observation
        o.private['inventories']=[{'FERTILIZER':1},{'FERTILIZER':1}]
        orig=copy.deepcopy((o,action));a=lane.apply_spill(o,action,env.configuration,enabled=True)
        self.assertEqual(sum(cmd==['FERTILIZE'] for cmd in [a['farmer'],*a['hands']]),1)
        self.assertEqual((o,action),orig)


    def test_ignored_nonexistent_actor_rows_preserved(self):
        state,env,action=fixture();o=state[0].observation
        action['hands']=[['WATER'],['NORTH'],['FERTILIZE']]
        before=copy.deepcopy(action)
        arm=lane.apply_spill(o,action,env.configuration,enabled=True)
        self.assertIsNot(arm,action)
        self.assertEqual(arm['hands'],before['hands'])
        self.assertEqual(action,before)
        self.assertEqual(arm['farmer'],['FERTILIZE'])

    def test_legal_buy_hire_plant_water_harvest_sale_trajectory(self):
        for seat in (0,1):
         for worker in (0,1):
          outcomes=[]
          for enabled in (False,True):
           cfg=loader.Struct({k:v.get('default') if isinstance(v,dict) else v
                for k,v in ENGINE.specification['configuration'].items()})
           cfg.seed=17; cfg.startingMoney=5000  # Legal configured setup, not default bankroll.
           env=loader.Struct(configuration=cfg,done=False,info={})
           state=[loader.Struct(observation=loader.Struct(),action={},status='ACTIVE',reward=0)
                for _ in (0,1)]
           execute(state,env);changes=[];eod=None;harvest=None
           for step in range(53):
            cmd=['PASS'];market=[]
            if step==0:
             market=([['HIRE']] if worker else [])+[['BUY_SEED','WHEAT',1],
                       ['BUY_PRODUCT','FERTILIZER',1],['BUY_PRODUCT','WHEAT',99]]
            if step==1:cmd=['PICKUP','FERTILIZER',1];market=[['BUY_PRODUCT','WHEAT',1]]
            if step==2 or (worker and step==3):cmd=['WEST']
            if step==4:cmd=['PLANT','WHEAT']
            if step==5:cmd=['WATER']
            if step in (24,48):cmd=['WEST']
            if step in (25,49):cmd=['WATER']
            if step==50:cmd=['HARVEST']
            if step==51:cmd=['EAST'];market=[['SELL','WHEAT',100]]
            if step==52:cmd=['DROP'];market=[['SELL','WHEAT',100]]
            for i,st in enumerate(state):
             st.observation.step=step
             is_hand=bool(worker and step<24 and step>0)
             parent={'farmer':cmd if i==seat and not is_hand else ['PASS'],
                     'hands':[cmd] if i==seat and is_hand else [],
                     'market':market if i==seat else []}
             st.action=lane.apply_spill(copy.deepcopy(st.observation),parent,cfg,enabled=enabled and i==seat)
             if st.action!=parent:changes.append(step)
            execute(state,env)
            if step==23:eod=copy.deepcopy(state[seat].observation.private)
            if step==50:harvest=state[seat].observation.private['inventories'][0].get('WHEAT',0)
           outcomes.append({'cash':state[seat].observation.farms[seat]['money'],
                            'eod':eod,'harvest':harvest,'changes':changes})
          b,a=outcomes
          self.assertEqual(b['eod'],a['eod']);self.assertEqual(b['changes'],[])
          self.assertEqual(a['changes'],[23]);self.assertEqual((b['harvest'],a['harvest']),(2,3))
          self.assertGreater(a['cash'],b['cash'])
          print('LEGAL_REACHABLE',seat,worker,'cash',b['cash'],a['cash'],'delta',a['cash']-b['cash'])


class NativeComposition(unittest.TestCase):
    def test_source_pin_drift(self):
        src=(NATIVE/'titan_runtime.py').read_bytes()
        self.assertIn(b'finish_spill',composer.transform(src))
        with self.assertRaises(ValueError):composer.transform(src+b'\n')
    def test_existing_output_not_touched(self):
        with tempfile.TemporaryDirectory() as d:
         with self.assertRaises(ValueError):composer.compose(NATIVE,d)
    def test_flags_and_snapshot_binding(self):
        text=composer.transform((NATIVE/'titan_runtime.py').read_bytes()).decode()
        ns={'__file__':str(NATIVE/'titan_runtime.py')};exec(compile(text,'patched','exec'),ns)
        self.assertFalse(ns['Features']().r04_fert_mix)
        with self.assertRaises(ValueError):ns['Features'](r04_fert_mix='yes')
        with self.assertRaises(ValueError):ns['Features'](consumer='ordered',r04_fert_mix=True)
        state,env,action=fixture();o=state[0].observation
        r=types.SimpleNamespace(features=types.SimpleNamespace(r04_fert_mix=True,consumer='frozen'),
             diagnostics={'status':'completed'},spatial=None,quadrant=None,consumer=types.SimpleNamespace(),post=None)
        a,post=lane.finish_spill(r,o,env.configuration,action,None)
        self.assertIsNot(a,action);self.assertIs(post,r.post)
        self.assertEqual(r.consumer.selected_post_units_binding,(71,0,a['farmer'],[]))
        self.assertEqual(post.private['inventories'],[{}])
        self.assertEqual(post.farms[0]['tiles'][1][1]['fertilized_until_day'],4)
    def test_deadline_owned_routes_keep_exact_parent(self):
        state,env,action=fixture();o=state[0].observation
        r=types.SimpleNamespace(features=types.SimpleNamespace(r04_fert_mix=True,consumer='frozen'),
             diagnostics={'status':'deadline_fallback'},spatial=None,quadrant=None,consumer=None)
        marker=object()
        self.assertEqual(lane.finish_spill(r,o,env.configuration,action,marker),(action,marker))
        r.diagnostics['status']='completed'
        for field,value in (('plans',{0:{}}),('_pending',{'plans':{0:{}}}),
                            ('crop_intent',{'status':'owned'}),('sale_obligation',{'worker':0})):
         r.spatial=types.SimpleNamespace(**{field:value})
         out,post=lane.finish_spill(r,o,env.configuration,action,marker)
         self.assertIs(out,action);self.assertIs(post,marker)
        r.spatial=types.SimpleNamespace(_pending={'plans':{}})
        r.consumer=types.SimpleNamespace()
        out,post=lane.finish_spill(r,o,env.configuration,action,marker)
        self.assertIsNot(out,action)


    def test_actual_native_finalizer_after_market_before_history(self):
        text=composer.transform((NATIVE/'titan_runtime.py').read_bytes()).decode()
        ns={'__file__':str(NATIVE/'titan_runtime.py')};exec(compile(text,'patched','exec'),ns)
        Agent,Features=ns['TitanAgent'],ns['Features']
        for sell_frees_space in (False,True):
         state,env,action=fixture();o=state[0].observation
         r=Agent.__new__(Agent);r.features=types.SimpleNamespace(r04_fert_mix=True,terminal_history=True,consumer='frozen')
         r.diagnostics={'status':'completed'};r.spatial=None;r.quadrant=None
         r.consumer=types.SimpleNamespace();seen=[]
         r.history=types.SimpleNamespace(diagnostics={},remember=lambda *args:seen.append(args))
         r._selected_snapshot=lambda *args:copy.deepcopy(o)
         r._feed_stock_selected=lambda obs,cfg,a:a
         r._early_capital_selected=lambda obs,cfg,a:(dict(a,market=[['SELL','CARROT',1]]) if sell_frees_space else a)
         out=r._finish_production(o,action,env.configuration)
         self.assertEqual(out['farmer'],['PASS'] if sell_frees_space else ['FERTILIZE'])
         self.assertEqual(seen[0][2],out)
         if not sell_frees_space:
          self.assertEqual(seen[0][3].farms[0]['tiles'][1][1]['fertilized_until_day'],4)
          self.assertEqual(r.consumer.selected_post_units_binding,(71,0,['FERTILIZE'],[]))


if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    print('full interpreter calls',TRANSITIONS)
    if not result.wasSuccessful():sys.exit(1)
