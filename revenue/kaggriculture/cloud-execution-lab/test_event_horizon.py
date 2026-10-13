"""E08 event-aware SELL horizon contracts.

These are source-level boundary tests. Playing-strength claims require separate
official-engine complete games and are intentionally not inferred here.
"""
from __future__ import annotations

import unittest
from unittest import mock

import frozen_selected as fs


def route():
    return [{'farmer':['PASS'],'hands':[],'market':[]} for _ in range(720)]


def farm_at(pos=(4,4), money=100):
    tiles=[[None for _ in range(10)] for _ in range(10)]
    return {
        'money':money,
        'unlocked_quadrants':['NW'],
        'hires_today':0,
        'farmer':list(pos),
        'hands':[],
        'tiles':tiles,
    }


def private_state(*, shed=None, inventory=None):
    return {
        'shed':dict(shed or {}),
        'inventories':[dict(inventory or {})],
        'seeds':{},
    }


class EventAwareHorizonTests(unittest.TestCase):
    def test_product_absorption_just_outside_old_window_extends_to_real_slot(self):
        tape=route()
        with mock.patch.object(fs.parent,'DECISIONS',()), \
             mock.patch.dict(fs.m.SHOPS,{'MILK_ONLY':['MILK']},clear=False):
            end,info=fs.event_aware_horizon(
                10,718,tape,{'MILK':4},['MILK_ONLY'],
                {'townShopSellInterval':4,'townCenterSellInterval':24,
                 'maxMarketOrdersPerTurn':10})
        self.assertEqual(info['baseline_end'],18)
        self.assertEqual(info['hard_end'],23)
        self.assertEqual(info['service_dates'],{'MILK':21})
        self.assertIsNone(info['unit_event'])
        self.assertEqual(end,21)
        self.assertTrue(info['extended'])

    def test_full_market_without_same_product_slot_does_not_extend(self):
        tape=route()
        tape[21]['market']=[['BUY_SEED','CARROT',1] for _ in range(10)]
        with mock.patch.object(fs.parent,'DECISIONS',()), \
             mock.patch.dict(fs.m.SHOPS,{'MILK_ONLY':['MILK']},clear=False):
            end,info=fs.event_aware_horizon(
                10,718,tape,{'MILK':4},['MILK_ONLY'],
                {'townShopSellInterval':4,'townCenterSellInterval':24,
                 'maxMarketOrdersPerTurn':10})
        self.assertEqual(end,18)
        self.assertEqual(info['service_dates'],{})
        self.assertFalse(info['extended'])

    def test_existing_same_product_sell_slot_is_executable_at_full_market(self):
        tape=route()
        tape[21]['market']=[['BUY_SEED','CARROT',1] for _ in range(9)]
        tape[21]['market'].append(['SELL','MILK',1])
        with mock.patch.object(fs.parent,'DECISIONS',()), \
             mock.patch.dict(fs.m.SHOPS,{'MILK_ONLY':['MILK']},clear=False):
            end,info=fs.event_aware_horizon(
                10,718,tape,{'MILK':4},['MILK_ONLY'],
                {'townShopSellInterval':4,'townCenterSellInterval':24,
                 'maxMarketOrdersPerTurn':10})
        self.assertEqual(info['service_dates'],{'MILK':21})
        self.assertEqual(end,21)

    def test_no_relevant_refill_retains_inherited_horizon(self):
        tape=route()
        with mock.patch.object(fs.parent,'DECISIONS',()), \
             mock.patch.dict(fs.m.SHOPS,{'CARROT_ONLY':['CARROT']},clear=False):
            end,info=fs.event_aware_horizon(
                10,718,tape,{'MILK':4},['CARROT_ONLY'],
                {'townShopSellInterval':4,'townCenterSellInterval':24})
        self.assertEqual(end,18)
        self.assertEqual(info['service_dates'],{})
        self.assertFalse(info['extended'])

    def test_bare_harvest_is_not_a_shed_event(self):
        tape=route()
        tape[20]['farmer']=['HARVEST']
        farm=farm_at((0,0))
        farm['tiles'][0][0]={'kind':'PLANT','crop':'CARROT','planted_day':-3,
                             'yield_units':2,'watered_today':False,
                             'consecutive_unwatered':0,'max_lifespan_step':999,
                             'fertilized_until_day':-1}
        private=private_state(shed={'MILK':4})
        event=fs.represented_shed_event(
            10,18,23,tape,farm,private,
            {'turnsPerDay':24,'shedCapacity':100})
        self.assertIsNone(event)

    def test_harvest_then_represented_drop_extends_to_actual_deposit(self):
        tape=route()
        # Farmer begins one step from a shed-access tile. Harvest -> move -> DROP.
        tape[19]['farmer']=['HARVEST']
        tape[20]['farmer']=['EAST']
        tape[21]['farmer']=['DROP']
        farm=farm_at((3,4))
        farm['tiles'][4][3]={'kind':'PLANT','crop':'CARROT','planted_day':-3,
                             'yield_units':2,'watered_today':False,
                             'consecutive_unwatered':0,'max_lifespan_step':999,
                             'fertilized_until_day':-1}
        private=private_state(shed={'MILK':4})
        event=fs.represented_shed_event(
            10,18,23,tape,farm,private,
            {'turnsPerDay':24,'shedCapacity':100})
        self.assertEqual(event,21)

    def test_invalid_drop_does_not_extend(self):
        tape=route();tape[20]['farmer']=['DROP']
        event=fs.represented_shed_event(
            10,18,23,tape,farm_at((0,0)),
            private_state(shed={'MILK':4},inventory={'CARROT':2}),
            {'turnsPerDay':24,'shedCapacity':100})
        self.assertIsNone(event)

    def test_animal_place_is_not_mistaken_for_shed_deposit(self):
        tape=route();tape[20]['farmer']=['PLACE','COW']
        farm=farm_at((0,0))
        farm['tiles'][0][0]={'kind':'PASTURE'}
        event=fs.represented_shed_event(
            10,18,23,tape,farm,
            private_state(shed={'MILK':4},inventory={'COW':1}),
            {'turnsPerDay':24,'shedCapacity':100})
        self.assertIsNone(event)

    def test_checkpoint_before_event_prevents_extension(self):
        tape=route()
        with mock.patch.object(fs.parent,'DECISIONS',((20,'fixture',0,'tail'),)), \
             mock.patch.dict(fs.m.SHOPS,{'MILK_ONLY':['MILK']},clear=False):
            end,info=fs.event_aware_horizon(
                10,718,tape,{'MILK':4},['MILK_ONLY'],
                {'townShopSellInterval':4,'townCenterSellInterval':24})
        self.assertEqual(info['hard_end'],19)
        self.assertEqual(info['baseline_end'],18)
        self.assertEqual(end,18)
        self.assertFalse(info['extended'])

    def test_unrepresented_tape_before_event_prevents_extension(self):
        tape=route()[:20]
        with mock.patch.object(fs.parent,'DECISIONS',()), \
             mock.patch.dict(fs.m.SHOPS,{'MILK_ONLY':['MILK']},clear=False):
            end,info=fs.event_aware_horizon(
                10,718,tape,{'MILK':4},['MILK_ONLY'],
                {'townShopSellInterval':4,'townCenterSellInterval':24})
        self.assertEqual(info['hard_end'],19)
        self.assertEqual(end,18)
        self.assertFalse(info['extended'])

    def test_terminal_cutoff_is_hard(self):
        tape=route()
        with mock.patch.object(fs.parent,'DECISIONS',()), \
             mock.patch.dict(fs.m.SHOPS,{'MILK_ONLY':['MILK']},clear=False):
            end,info=fs.event_aware_horizon(
                713,718,tape,{'MILK':4},['MILK_ONLY'],
                {'townShopSellInterval':4,'townCenterSellInterval':24})
        self.assertEqual(info['hard_end'],718)
        self.assertEqual(info['baseline_end'],718)
        self.assertEqual(end,718)
        self.assertFalse(info['extended'])

    def test_product_event_dates_never_borrow_another_products_absorption(self):
        with mock.patch.dict(fs.m.SHOPS,{'MILK_ONLY':['MILK']},clear=False):
            milk=fs.product_event_dates(
                'MILK',10,21,['MILK_ONLY'],
                {'townShopSellInterval':4,'townCenterSellInterval':24})
            carrot=fs.product_event_dates(
                'CARROT',10,18,['MILK_ONLY'],
                {'townShopSellInterval':4,'townCenterSellInterval':24})
        self.assertEqual(milk,[10,13,21])
        self.assertEqual(carrot,[10,18])

    def _minimal_agent(self, tape):
        agent=object.__new__(fs.FrozenSelected)
        agent.pending={};agent.planned={};agent.mode='candidate'
        agent.controller=type('Controller',(),{'cur':'fixture','R':{'fixture':tape}})()
        agent.observe=mock.Mock()
        agent.rival_supply=mock.Mock(return_value=0)
        agent.receipt_profile=mock.Mock(return_value=lambda _plan: True)
        return agent

    def _minimal_obs(self, money=10, shops=None):
        own={'money':money,'unlocked_quadrants':['NW'],'hires_today':0}
        return {'step':10,'player':0,'farms':[own,{}],
                'market':{'inventory':{'MILK':10000},'params':None,'prices':{'MILK':160}},
                'town':{'unlocked_shops':list(shops or ['MILK_ONLY'])}}

    def test_extended_service_window_prices_known_future_funding(self):
        tape=route();tape[20]['market']=[['BUY_SEED','CARROT',1]]
        agent=self._minimal_agent(tape)
        obs=self._minimal_obs(money=10)
        base={'farmer':['PASS'],'hands':[],'market':[['SELL','MILK',1]]}
        farm=farm_at((4,4),money=10)
        private=private_state(shed={'MILK':4})
        seen={}
        def optimizer(**kwargs):
            seen.update(kwargs)
            return kwargs['reference'],{'worst_relative_gain':0,'forced_feasibility':False,
                                        'plan':list(kwargs['reference']),'scenarios':{}}
        with mock.patch.object(fs.parent,'DECISIONS',()), \
             mock.patch.dict(fs.m.SHOPS,{'MILK_ONLY':['MILK']},clear=False), \
             mock.patch.object(fs,'post_units',return_value=(farm,private)), \
             mock.patch.object(fs,'seller_public_observation',return_value={}), \
             mock.patch.object(fs,'optimize_lot',side_effect=optimizer):
            out=agent.transform(
                obs,{'townShopSellInterval':4,'townCenterSellInterval':24},base)
        self.assertEqual(seen['dates'][-1],21)
        self.assertEqual(
            seen['minimum_now'],1,
            'The turn-20 seed purchase must be prepaid inside the extended window')
        self.assertEqual(agent.diagnostics['horizon']['service_dates'],{'MILK':21})
        self.assertEqual(out['market'],base['market'])

    def test_actual_future_drop_extends_receipt_capacity_check(self):
        tape=route();tape[20]['farmer']=['DROP']
        agent=self._minimal_agent(tape)
        obs=self._minimal_obs(money=100,shops=['CARROT_ONLY'])
        base={'farmer':['PASS'],'hands':[],'market':[]}
        farm=farm_at((4,4),money=100)
        private=private_state(shed={'MILK':4},inventory={'CARROT':2})
        seen={}
        def optimizer(**kwargs):
            seen.update(kwargs)
            return kwargs['reference'],{'worst_relative_gain':0,'forced_feasibility':False,
                                        'plan':list(kwargs['reference']),'scenarios':{}}
        with mock.patch.object(fs.parent,'DECISIONS',()), \
             mock.patch.dict(fs.m.SHOPS,{'CARROT_ONLY':['CARROT']},clear=False), \
             mock.patch.object(fs,'post_units',return_value=(farm,private)), \
             mock.patch.object(fs,'seller_public_observation',return_value={}), \
             mock.patch.object(fs,'optimize_lot',side_effect=optimizer):
            agent.receipt_profile=mock.Mock(return_value=lambda _plan: True)
            agent.transform(
                obs,{'townShopSellInterval':4,'townCenterSellInterval':24},base)
        self.assertEqual(agent.diagnostics['horizon']['unit_event'],20)
        self.assertEqual(seen['dates'][-1],20)
        self.assertEqual(agent.receipt_profile.call_args.args[4],20)


    def test_current_hire_without_later_deposit_does_not_extend(self):
        tape=route()
        farm=farm_at((0,0))
        event=fs.represented_shed_event(
            10,18,23,tape,farm,private_state(shed={'MILK':4}),
            {'turnsPerDay':24,'shedCapacity':100},
            [['HIRE']])
        self.assertIsNone(event)

    def test_current_hire_then_future_hand_drop_extends(self):
        tape=route()
        # Spawn occupies (4,4). West onto a mature plant, harvest, return, DROP.
        tape[11]['hands']=[['WEST']]
        tape[12]['hands']=[['HARVEST']]
        tape[13]['hands']=[['EAST']]
        tape[21]['hands']=[['DROP']]
        farm=farm_at((0,0))
        farm['tiles'][4][3]={'kind':'PLANT','crop':'CARROT','planted_day':-3,
                             'yield_units':2,'watered_today':False,
                             'consecutive_unwatered':0,'max_lifespan_step':999,
                             'fertilized_until_day':-1}
        private=private_state(shed={'MILK':4})
        cfg={'turnsPerDay':24,'shedCapacity':100}
        self.assertIsNone(fs.represented_shed_event(
            10,18,23,tape,farm,private,cfg,[]),
            'Without the current HIRE the hand tape is a no-op')
        self.assertEqual(fs.represented_shed_event(
            10,18,23,tape,farm,private,cfg,[['HIRE']]),21)

    def test_current_buy_then_pickup_drop_extends(self):
        tape=route()
        tape[20]['farmer']=['PICKUP','CARROT',2]
        tape[21]['farmer']=['DROP']
        farm=farm_at((4,4))
        private=private_state(shed={'MILK':4})
        cfg={'turnsPerDay':24,'shedCapacity':100}
        self.assertIsNone(fs.represented_shed_event(
            10,18,23,tape,farm,private,cfg,[]),
            'PICKUP of absent CARROT cannot seed a later DROP')
        self.assertEqual(fs.represented_shed_event(
            10,18,23,tape,farm,private,cfg,[['BUY_PRODUCT','CARROT',2]]),21)

    def test_current_sell_then_represented_drop_still_extends(self):
        tape=route()
        tape[19]['farmer']=['HARVEST']
        tape[20]['farmer']=['EAST']
        tape[21]['farmer']=['DROP']
        farm=farm_at((3,4))
        farm['tiles'][4][3]={'kind':'PLANT','crop':'CARROT','planted_day':-3,
                             'yield_units':2,'watered_today':False,
                             'consecutive_unwatered':0,'max_lifespan_step':999,
                             'fertilized_until_day':-1}
        private=private_state(shed={'MILK':4})
        event=fs.represented_shed_event(
            10,18,23,tape,farm,private,
            {'turnsPerDay':24,'shedCapacity':100},
            [['SELL','MILK',2]])
        self.assertEqual(event,21)

    def test_transform_binds_current_hire_before_future_hand_drop(self):
        tape=route()
        tape[11]['hands']=[['WEST']]
        tape[12]['hands']=[['HARVEST']]
        tape[13]['hands']=[['EAST']]
        tape[21]['hands']=[['DROP']]
        agent=self._minimal_agent(tape)
        obs=self._minimal_obs(money=100,shops=['CARROT_ONLY'])
        base={'farmer':['PASS'],'hands':[],'market':[['HIRE']]}
        farm=farm_at((0,0),money=100)
        farm['tiles'][4][3]={'kind':'PLANT','crop':'CARROT','planted_day':-3,
                             'yield_units':2,'watered_today':False,
                             'consecutive_unwatered':0,'max_lifespan_step':999,
                             'fertilized_until_day':-1}
        private=private_state(shed={'MILK':4})
        seen={}
        def optimizer(**kwargs):
            seen.update(kwargs)
            return kwargs['reference'],{'worst_relative_gain':0,'forced_feasibility':False,
                                        'plan':list(kwargs['reference']),'scenarios':{}}
        with mock.patch.object(fs.parent,'DECISIONS',()), \
             mock.patch.dict(fs.m.SHOPS,{'CARROT_ONLY':['CARROT']},clear=False), \
             mock.patch.object(fs,'post_units',return_value=(farm,private)), \
             mock.patch.object(fs,'seller_public_observation',return_value={}), \
             mock.patch.object(fs,'optimize_lot',side_effect=optimizer):
            agent.receipt_profile=mock.Mock(return_value=lambda _plan: True)
            agent.transform(
                obs,{'townShopSellInterval':4,'townCenterSellInterval':24},base)
        self.assertEqual(agent.diagnostics['horizon']['unit_event'],21)
        self.assertEqual(seen['dates'][-1],21)
        self.assertEqual(agent.receipt_profile.call_args.args[4],21)


if __name__=='__main__':
    unittest.main(verbosity=2)
