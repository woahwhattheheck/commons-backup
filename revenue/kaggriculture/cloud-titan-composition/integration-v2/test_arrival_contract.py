# SPDX-License-Identifier: MIT
"""Synthetic interface cases. These are not retained cap-plan replay evidence."""
import copy
import unittest
from arrival_contract import build_arrival_contract,pending_capacity,ContractError

def case():
    obs={'step':226,'player':0,'farms':[{'farmer':[0,0],'hands':[[1,0]],
        'tiles':[[{} for _ in range(10)] for _ in range(10)]}],
        'private':{'inventories':[{},{}],'shed':{'WHEAT':6}}}
    action={'farmer':['PASS'],'hands':[['PASS']],'market':[]}
    plan={'errand_id':'crop:2:0:226','worker_index':1,'target':[2,0],
        'product':'CARROT','units_total':4,'units_incremental':1,
        'arrival_step':239,'arrival_kind':'eod_auto','no_forced_sale_date':True,
        'status':'pending','observed_carried_units':0}
    return obs,action,{'owner':'flora','observed_step':226,'plans':[plan]}

class Cases(unittest.TestCase):
    def test_whole_crop_harvest_after_market_not_just_economic_units(self):
        obs,a,s=case();r=build_arrival_contract(obs,{},a,[s])
        self.assertEqual(pending_capacity(r,239,'before_market'),{})
        self.assertEqual(pending_capacity(r,239,'after_market'),{'CARROT':4})
        self.assertEqual(r['capacity_events'][0]['first_possible_sale_step'],240)
        self.assertEqual(r['capacity_events'][0]['units_incremental'],1)
        self.assertEqual(r['sale_lots'],[])
        self.assertEqual(r['guaranteed_future_output_units'],0)

    def test_realization_removes_pending_once_and_keeps_worker_ownership(self):
        obs,a,s=case();obs['private']['inventories'][1]={'CARROT':4}
        s['plans'][0].update(status='carried',observed_carried_units=4)
        r=build_arrival_contract(obs,{},a,[s])
        self.assertEqual(r['capacity_events'],[])
        self.assertEqual(r['realized_carried'][0]['units'],4)
        self.assertEqual(r['worker_reservations'][0]['worker_index'],1)
        other=copy.deepcopy(s);other['owner']='cap'
        with self.assertRaises(ContractError):build_arrival_contract(obs,{},a,[s,other])

    def test_partial_realization_and_abort(self):
        obs,a,s=case();obs['private']['inventories'][1]={'CARROT':2}
        s['plans'][0]['observed_carried_units']=2
        r=build_arrival_contract(obs,{},a,[s])
        self.assertEqual(pending_capacity(r,239,'after_market'),{'CARROT':2})
        s['plans'][0]['status']='aborted'
        r=build_arrival_contract(obs,{},a,[s])
        self.assertEqual(r['capacity_events'],[])
        self.assertEqual(r['worker_reservations'],[])

    def test_stale_unknown_and_unissued_deposit_rejected(self):
        obs,a,s=case();s['observed_step']-=1
        with self.assertRaises(ContractError):build_arrival_contract(obs,{},a,[s])
        s['observed_step']=obs['step'];s['plans'][0].update(arrival_kind='worker_deposit',arrival_step=230)
        with self.assertRaises(ContractError):build_arrival_contract(obs,{},a,[s])
        s['plans'][0]['deposit_action']=['PLACE','CARROT',4]
        self.assertEqual(build_arrival_contract(obs,{},a,[s])['capacity_events'][0]['phase'],'before_market')

    def test_shared_target_and_stock_are_not_double_allocated(self):
        obs,a,s=case();other=copy.deepcopy(s);other['owner']='cap';other['plans'][0]['worker_index']=0
        with self.assertRaises(ContractError):build_arrival_contract(obs,{},a,[s,other])
        s['plans'][0]['observed_carried_units']=1
        with self.assertRaises(ContractError):build_arrival_contract(obs,{},a,[s])

    def test_hire_reference_and_final_sale_window(self):
        obs,a,s=case();s['plans'][0]['worker_index']=2
        with self.assertRaises(ContractError):build_arrival_contract(obs,{},a,[s])
        a['market']=[['HIRE']];s['plans'][0]['hire_order_index']=0
        self.assertEqual(len(build_arrival_contract(obs,{},a,[s])['capacity_events']),1)
        obs['step']=718;s['observed_step']=718;s['plans'][0]['arrival_step']=719
        self.assertFalse(build_arrival_contract(obs,{},a,[s])['capacity_events'][0]['sale_window_available'])

if __name__=='__main__':unittest.main()
