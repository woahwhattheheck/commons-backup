# SPDX-License-Identifier: Apache-2.0
"""E05 pure joint market composition contracts; no engine or game execution."""
import unittest
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch
from selected_sell_core import joint_plan_metrics, shared_slot_ledger
from frozen_selected import (FrozenSelected, joint_resource_bound, joint_queue_ledger,
                             materialize_sales, sale_quantities)
from scheduler import m, post_units, _order_spend


def fixture(now=100, shed=None):
    farm={'tiles':[[None]*10 for _ in range(10)],'farmer':[4,4],'hands':[],
          'money':100000,'hires_today':0,'unlocked_quadrants':['NW']}
    private={'shed':dict(shed or {'MILK':3,'WOOL':4}), 'seeds':{},'inventories':[{}]}
    obs={'step':now,'player':0,'farms':[farm,deepcopy(farm)],'private':private,
         'market':{'inventory':{p:10000 for p in m.PRODUCTS},
                   'prices':{p:m.market_price(p,10000) for p in m.PRODUCTS}},
         'town':{'unlocked_shops':[]}}
    route=[{'farmer':['PASS'],'hands':[],'market':[]} for _ in range(720)]
    return obs,route,deepcopy(route[now])


def consumer(route,planned=None):
    bot=FrozenSelected.__new__(FrozenSelected)
    bot.controller=SimpleNamespace(R={'test':route},cur='test')
    bot.mode='candidate';bot.planned=deepcopy(planned or {});bot.pending={}
    bot.previous=None;bot.observed_harvests={};bot.diagnostics={}
    return bot


def profitable_lot(**kw):
    item=kw['item'];q=kw['quantity'];now=kw['now']
    gain={'MILK':3,'WOOL':2}.get(item,0)
    plan=((now,q),) if gain else tuple(kw['reference'])
    report={'item':item,'quantity':q,'plan':list(plan), 'reference':list(kw['reference']),
            'worst_relative_gain':gain,'feasible':True,'forced_feasibility':False,
            'scenarios':{'no_rival':{'reference_relative_value':0,'relative_value':gain},
                         'observed_paired':{'reference_relative_value':0,'relative_value':gain+1}}}
    return plan,report


def info(a,b):
    return {'scenarios':{'no_rival':{'reference_relative_value':0,'relative_value':a},
                         'observed_paired':{'reference_relative_value':0,'relative_value':b}}}

class JointMarketCompositionTests(unittest.TestCase):
    def test_two_products_share_scenario_value(self):
        out=joint_plan_metrics([info(3,2),info(5,1)])
        self.assertEqual(out['scenario_deltas'],{'no_rival':8.0,'observed_paired':3.0})
        self.assertEqual(out['worst_relative_gain'],3.0)

    def test_mismatched_scenarios_decline(self):
        self.assertIsNone(joint_plan_metrics([info(1,1),{'scenarios':{'x':{}}}]))

    def test_two_extras_fit_last_two_slots(self):
        inherited=[['HIRE'] for _ in range(8)]
        plans={'MILK':((4,2),),'EGG':((4,3),)}
        ledger=shared_slot_ledger(plans,lambda _t:inherited,10)
        self.assertEqual(ledger[4]['extra_items'],['EGG','MILK'])
        self.assertEqual(ledger[4]['total_slots'],10)

    def test_pair_rejected_when_only_one_slot_remains(self):
        inherited=[['HIRE'] for _ in range(9)]
        plans={'MILK':((4,2),),'EGG':((4,3),)}
        self.assertIsNone(shared_slot_ledger(plans,lambda _t:inherited,10))

    def test_existing_sell_capacity_needs_no_extra_slot(self):
        inherited=[['SELL','MILK',2]]+[['HIRE'] for _ in range(8)]
        plans={'MILK':((4,2),),'EGG':((4,3),)}
        ledger=shared_slot_ledger(plans,lambda _t:inherited,10)
        self.assertEqual(ledger[4]['extra_items'],['EGG'])

    def test_different_future_dates_allocate_independently(self):
        plans={'MILK':((5,2),),'EGG':((6,3),)}
        ledger=shared_slot_ledger(plans,lambda _t:[['HIRE'] for _ in range(9)],10)
        self.assertEqual(ledger[5]['total_slots'],10)
        self.assertEqual(ledger[6]['total_slots'],10)

class JointResourceContracts(unittest.TestCase):
    def bound(self,obs,route,base,end=108):
        farm,private=post_units(obs,base,{})
        return joint_resource_bound(obs,{},base,farm,private,route,end)

    def test_carried_harvest_is_not_a_shed_arrival_without_a_delivery(self):
        obs,route,base=fixture(shed={'MILK':3,'WOOL':4,'WHEAT':42})
        obs['private']['inventories'][0]={'STRAWBERRY':80}
        route[104]['farmer']=['PLACE','WOOL',6]
        route[105]['farmer']=['HARVEST']
        bound=self.bound(obs,route,base)
        self.assertEqual(bound['stock_total_upper'],55)
        self.assertEqual(bound['stock_upper']['WOOL'],10)

    def test_shared_placements_cannot_each_reuse_the_same_room(self):
        obs,route,base=fixture(shed={'MILK':45,'WOOL':45})
        route[102]['farmer']=['PLACE','MILK',6]
        route[103]['farmer']=['PLACE','WOOL',6]
        self.assertIsNone(self.bound(obs,route,base))

    def test_ordered_purchase_cannot_rely_on_an_earlier_or_later_sale(self):
        obs,route,base=fixture(shed={'MILK':45,'WOOL':45})
        base['market']=[['SELL','MILK',10],['BUY_ANIMAL','COW',15],['SELL','WOOL',10]]
        self.assertIsNone(self.bound(obs,route,base))

    def test_drop_and_day_close_require_a_different_capacity_proof(self):
        obs,route,base=fixture()
        route[108]['hands']=[['DROP']]
        self.assertIsNone(self.bound(obs,route,base))
        route[108]['hands']=[]
        self.assertIsNone(self.bound(obs,route,base,end=119))

    def test_variable_buy_declines_the_concrete_107_to_108_funding_case(self):
        obs,route,base=fixture()
        buy=['BUY_PRODUCT','FERTILIZER',1]
        reserve,_=_order_spend(buy,obs['farms'][0],obs['market']['inventory'],None,0,{})
        self.assertEqual(reserve,107)
        self.assertEqual(m.market_price('FERTILIZER',10000-40-1),108)
        obs['farms'][0]['money']=reserve;route[102]['market']=[buy]
        self.assertIsNone(self.bound(obs,route,base))

    def test_boundary_hire_is_funded_before_both_sales_can_be_withheld(self):
        obs,route,base=fixture()
        obs['farms'][0].update(money=54,hires_today=9)
        route[109]['market']=[['HIRE']]
        self.assertIsNone(self.bound(obs,route,base))
        obs['farms'][0]['money']=55
        bound=self.bound(obs,route,base)
        self.assertEqual((bound['fixed_cost'],bound['capital_end']),(55,109))

    def test_boundary_deposit_cannot_be_rescued_by_replanning_after_units(self):
        obs,route,base=fixture(shed={'MILK':1,'WOOL':1,'WHEAT':96})
        base['market']=[['SELL','MILK',1],['SELL','WOOL',1]]
        route[109]['farmer']=['DROP']
        self.assertIsNone(self.bound(obs,route,base))
        route[109]['farmer']=['PLACE','STRAWBERRY',3]
        self.assertIsNone(self.bound(obs,route,base))
        route[109]['farmer']=['PASS']
        self.assertIsNone(self.bound(obs,route,base,end=118))

    def test_seed_and_animal_costs_are_fixed_and_actual_cash_is_preserved(self):
        obs,route,base=fixture()
        base['market']=[['BUY_SEED','CARROT',2]]
        route[103]['market']=[['BUY_ANIMAL','COW',1],['HIRE'],['HIRE']]
        obs['farms'][0]['money']=442
        before=deepcopy(obs)
        bound=self.bound(obs,route,base)
        self.assertEqual(bound['fixed_cost'],442)
        self.assertEqual(bound['stock_upper']['COW'],1)
        self.assertEqual(obs,before)

    def test_branch_and_terminal_boundaries_decline(self):
        obs,route,base=fixture(now=428)
        self.assertIsNone(self.bound(obs,route,base,end=432))
        obs,route,base=fixture(now=710)
        self.assertIsNone(self.bound(obs,route,base,end=718))


class JointEmitterContracts(unittest.TestCase):
    def ledger(self, plans, current, planned, shed, orders, now=100,end=102):
        return joint_queue_ledger(plans,current,planned,shed,{'stock_upper':shed},
                                  lambda t:orders.get(t,[]),now,end,10)

    def test_duplicate_sells_spend_only_one_physical_stock(self):
        orders=[['SELL','MILK',3],['BUY_SEED','CARROT',1],['SELL','MILK',3],[]]
        market=materialize_sales(orders,{'MILK':4},{'MILK':4},{'MILK'},10)
        self.assertEqual(market,[['SELL','MILK',3],['BUY_SEED','CARROT',1],['SELL','MILK',1],[]])

    def test_unchanged_due_product_consumes_the_third_extra_slot(self):
        shed={'CARROT':1,'MILK':3,'WOOL':4}
        plans={'MILK':((100,3),),'WOOL':((100,4),)}
        result=self.ledger(plans,{'CARROT':1,'MILK':0,'WOOL':0},
                           {'CARROT':[(100,1)]},shed,{100:[[]]*8})
        self.assertIsNone(result)

    def test_retained_future_product_reserves_its_slot_too(self):
        shed={'CARROT':1,'MILK':3,'WOOL':4}
        plans={'MILK':((101,3),),'WOOL':((101,4),)}
        self.assertIsNone(self.ledger(plans,{}, {'CARROT':[(101,1)]},shed,{101:[[]]*8}))

    def test_future_plan_and_inherited_sell_are_added_by_the_real_emitter(self):
        shed={'MILK':5,'WOOL':4}
        plans={'MILK':((101,2),),'WOOL':((101,2),)}
        orders={101:[['SELL','MILK',2]]+[[]]*7}
        result=self.ledger(plans,{}, {},shed,orders)
        self.assertEqual(result[101]['extra_items'],['MILK','WOOL'])
        self.assertEqual(result[101]['total_slots'],10)

    def test_unconfirmed_prior_due_sale_does_not_release_a_future_slot(self):
        shed={'MILK':3,'WOOL':4}
        plans={'MILK':((101,3),),'WOOL':((101,4),)}
        self.assertIsNone(self.ledger(plans,{}, {},shed,{102:[[]]*10}))


class JointFrozenIntegration(unittest.TestCase):
    def run_choice(self,obs,route,base,planned=None,busy=False):
        bot=consumer(route,planned);bot.joint_producer_busy=busy
        with patch('frozen_selected.optimize_lot',side_effect=profitable_lot):
            out=bot.transform(obs,{},base)
        return out,bot

    def test_two_funded_improvements_use_the_last_two_slots(self):
        obs,route,base=fixture();base['market']=[['HIRE'] for _ in range(8)]
        original=deepcopy(base)
        out,bot=self.run_choice(obs,route,base)
        self.assertEqual(set(bot.diagnostics['chosen']['items']),{'MILK','WOOL'})
        self.assertEqual(out['market'],base['market']+[['SELL','MILK',3],['SELL','WOOL',4]])
        self.assertEqual(base,original)

    def test_ninth_slot_keeps_the_original_single_product_choice(self):
        obs,route,base=fixture();base['market']=[['HIRE'] for _ in range(9)]
        out,bot=self.run_choice(obs,route,base)
        expected,control=self.run_choice(obs,route,base,busy=True)
        self.assertEqual((out,bot.planned,bot.pending),(expected,control.planned,control.pending))
        self.assertEqual(bot.diagnostics['chosen']['item'],'MILK')

    def test_underfunded_barrier_and_other_producer_leave_the_single_unchanged(self):
        obs,route,base=fixture();base['market']=[['HIRE'] for _ in range(8)]
        obs['farms'][0]['money']=0
        out,bot=self.run_choice(obs,route,base)
        expected,control=self.run_choice(obs,route,base,busy=True)
        self.assertEqual((out,bot.planned),(expected,control.planned))

    def test_future_pickup_commitment_prevents_a_joint_sale(self):
        obs,route,base=fixture();route[102]['farmer']=['PICKUP','WOOL',4]
        out,bot=self.run_choice(obs,route,base)
        self.assertEqual(bot.diagnostics['chosen']['item'],'MILK')

    def test_one_product_keeps_the_same_action_and_plan(self):
        obs,route,base=fixture(shed={'MILK':7})
        out,bot=self.run_choice(obs,route,base)
        expected,control=self.run_choice(obs,route,base,busy=True)
        self.assertEqual((out,bot.planned,bot.pending),(expected,control.planned,control.pending))

    def test_pure_floor_stock_has_no_economic_pair(self):
        obs,route,base=fixture()
        obs['market']['inventory']={p:100000 for p in m.PRODUCTS}
        bot=consumer(route)
        out=bot.transform(obs,{},base)
        self.assertEqual(out,base)
        self.assertNotIn('chosen',bot.diagnostics)

    def test_actual_optimizer_composes_two_demand_supported_lots(self):
        obs,route,base=fixture(now=241,shed={'MILK':8,'WOOL':8})
        obs['town']['unlocked_shops']=['SMOOTHIE_SHOP']*4+['YARN_STORE']*4
        base['market']=[['SELL','MILK',8],['SELL','WOOL',8]]
        bot=consumer(route)
        out=bot.transform(obs,{},base)
        chosen=bot.diagnostics['chosen']
        self.assertEqual(set(chosen['items']),{'MILK','WOOL'})
        self.assertGreater(chosen['worst_relative_gain'],0)
        self.assertEqual(set(bot.planned),{'MILK','WOOL'})
        self.assertEqual(out['farmer'],base['farmer'])
        self.assertEqual(len(out['market']),len(base['market']))

    def test_terminal_settlement_does_not_enter_joint_optimizer(self):
        obs,route,base=fixture(now=718)
        bot=consumer(route)
        with patch('frozen_selected.optimize_lot',side_effect=AssertionError('terminal optimization')):
            out=bot.transform(obs,{},base)
        self.assertEqual(sale_quantities(out['market']),{'MILK':3,'WOOL':4})


if __name__=='__main__':unittest.main()
