# SPDX-License-Identifier: MIT
"""Exact FLORA/engine transitions on synthetic midgame states; no full games."""
import copy
import importlib.util
from pathlib import Path
import unittest
from flora_bridge import FloraBridge
from arrival_contract import build_arrival_contract,pending_capacity

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('flora_bridge_engine',HERE.parent/'vendor/claude/engine_pin.py')
K=importlib.util.module_from_spec(spec);spec.loader.exec_module(K)

class Parent:
    def __init__(self):
        self.cur='route';self.R={'route':[{'farmer':['PASS'],'hands':[['PASS']],'market':[]} for _ in range(720)]}
    def act(self,obs):raise AssertionError('A second production pass occurred')

def case():
    farm={'farmer':[0,0],'hands':[[2,0]],'money':1000,'hires_today':0,
          'tiles':[[None for _ in range(10)] for _ in range(10)],'unlocked_quadrants':['NW']}
    farm['tiles'][0][2]={'kind':'PLANT','crop':'CARROT','yield_units':4,'planted_day':6}
    obs={'step':226,'day':9,'hour':10,'player':0,'farms':[farm],
         'private':{'inventories':[{},{}],'shed':{},'seeds':{}},
         'market':{'inventory':{'CARROT':10000},'prices':{'CARROT':35},'params':{}}}
    action={'farmer':['PASS'],'hands':[['PASS']],'market':[]}
    row={'id':'crop:2:0:225','day':9,'hand_index':0,'target':(2,0),
         'product':'CARROT','harvest_units':4,'economic_units':1,'start_step':226}
    bridge=FloraBridge(Parent());bridge.module._EH_RESERVATIONS[0]=[row]
    return bridge,obs,action

class BridgeTests(unittest.TestCase):
    def test_exact_source_harvest_then_carried_pass(self):
        bridge,obs,base=case();original=copy.deepcopy(base)
        chosen=bridge.transform(obs,base)
        self.assertEqual(base,original)
        self.assertEqual(chosen['hands'][0],['HARVEST'])
        self.assertEqual(bridge.owned_workers(obs),{1})
        before=bridge.producer_snapshot(obs,chosen)
        book=build_arrival_contract(obs,{},chosen,[before])
        self.assertEqual(pending_capacity(book,239,'before_market'),{})
        self.assertEqual(pending_capacity(book,239,'after_market'),{'CARROT':4})
        post=copy.deepcopy(obs)
        K._apply_unit_action(post['farms'][0],post['private'],1,chosen['hands'][0],10,9,24,100)
        after=bridge.producer_snapshot(post,chosen)
        book=build_arrival_contract(post,{},chosen,[after])
        self.assertEqual(book['capacity_events'],[])
        self.assertEqual(book['realized_carried'][0]['units'],4)
        post['step']=227;post['hour']=11
        self.assertEqual(bridge.transform(post,base)['hands'][0],['PASS'])

    def test_abort_and_once_only_parent_action(self):
        bridge,obs,base=case();bridge.transform(obs,base)
        bridge.producer_snapshot(obs,base)
        with self.assertRaises(RuntimeError):bridge.transform(obs,base)
        obs['step']=227;obs['hour']=11;obs['farms'][0]['tiles'][0][2]=None
        chosen=bridge.transform(obs,base)
        snapshot=bridge.producer_snapshot(obs,chosen)
        self.assertEqual(snapshot['plans'][0]['status'],'aborted')

    def test_partial_actual_harvest_cancels_unrealized_remainder(self):
        bridge,obs,base=case();obs['farms'][0]['tiles'][0][2]['yield_units']=2
        chosen=bridge.transform(obs,base)
        K._apply_unit_action(obs['farms'][0],obs['private'],1,chosen['hands'][0],10,9,24,100)
        fact=bridge.producer_snapshot(obs,chosen)['plans'][0]
        self.assertEqual(fact['status'],'carried')
        self.assertEqual(fact['units_total'],2)
        self.assertEqual(fact['cancelled_unrealized_units'],2)

if __name__=='__main__':unittest.main()
