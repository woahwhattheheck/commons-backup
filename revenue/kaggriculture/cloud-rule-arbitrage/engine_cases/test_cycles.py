# SPDX-License-Identifier: Apache-2.0
import copy
import os
from pathlib import Path
import unittest

from liquidity_cycle import LiquidityCycle
from market_math import MARKET_PARAMS, market_price
from official_cases import load_engine, paired, run_market


class Cycles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ev, cls.engine, _ = load_engine(Path(os.environ['T11_ENGINE_DIR']))

    def pair(self, **kw):
        return paired(self.ev, self.engine, **kw)

    def test_default_positive_and_opposite_direction(self):
        for seat in (0, 1):
            for op, expected in (("SELL", 1), ("BUY_PRODUCT", -1)):
                r = self.pair(seat=seat, own_shed={"WHEAT": 1}, rival_shed={"WHEAT": 1},
                              own_orders=[["SELL", "WHEAT", 1], ["BUY_PRODUCT", "WHEAT", 1]],
                              rival_orders=[[op, "WHEAT", 1]])
                self.assertEqual(r['cash_delta'], [expected, 0])
                self.assertEqual(r['actual']['shed'][0], {'WHEAT': 1})
                self.assertEqual(r['actual']['market'], r['control']['market'])

    def test_zero_cash_repurchase_can_fail(self):
        r = self.pair(own_cash=0, own_shed={"WHEAT": 1},
                      own_orders=[["SELL", "WHEAT", 1], ["BUY_PRODUCT", "WHEAT", 1]],
                      rival_orders=[["BUY_PRODUCT", "WHEAT", 1]])
        self.assertEqual(r['actual']['shed'][0], {'WHEAT': 0})
        self.assertEqual(r['cash_delta'][0], 25)  # Sale, not a restored cycle.

    def test_same_state_solo_quantity_has_zero_cash_profit(self):
        for item in ('WHEAT', 'FERTILIZER'):
            for inventory in (9800, 10000, 10100, 11000):
                for q in (1, 7, 100):
                    r = self.pair(item=item, inventory=inventory, own_cash=100000,
                                  own_orders=[["BUY_PRODUCT", item, q], ["SELL", item, q]])
                    self.assertEqual(r['cash_delta'], [0, 0])
                    self.assertEqual(r['actual']['shed'][0].get(item, 0), 0)

    def test_floor_limit_and_capacity(self):
        self.assertEqual(market_price('FERTILIZER', 10492), 2)
        self.assertEqual(market_price('FERTILIZER', 10493), 1)
        for inventory in (10492, 10493, 10494, 10500, 11000):
            for q in (1, 3, 100, 700):
                r = self.pair(item='FERTILIZER', inventory=inventory, capacity=800,
                              own_cash=100000, own_orders=[['BUY_PRODUCT','FERTILIZER',q],['SELL','FERTILIZER',q]])
                self.assertEqual(r['cash_delta'], [0, 0])
                self.assertEqual(r['actual']['market']['FERTILIZER'], inventory-min(q,max(0,inventory-10493)))
        for cash, fullness, removed in ((0,0,0),(3,0,3),(100,99,1),(100,100,0)):
            r = self.pair(item='FERTILIZER', inventory=11000, own_cash=cash,
                          own_shed={'MILK':fullness}, own_orders=[['BUY_PRODUCT','FERTILIZER',100],['SELL','FERTILIZER',100]])
            self.assertEqual(r['cash_delta'], [0, 0])
            self.assertEqual(r['actual']['market']['FERTILIZER'], 11000-removed)

    def test_other_product_funding_is_not_our_margin_profit(self):
        r = self.pair(own_shed={'WHEAT':1}, rival_shed={'MILK':1}, rival_cash=0,
                      own_orders=[['SELL','WHEAT',1],['BUY_PRODUCT','WHEAT',1]],
                      rival_orders=[['SELL','MILK',1],['BUY_PRODUCT','WHEAT',1]])
        self.assertEqual(r['cash_delta'], [0, 1])
        self.assertEqual(r['margin_delta'], -1)

    def test_transform_reservations_and_input_purity(self):
        fixture = run_market(self.ev,self.engine, inventory=10002,own_shed={'WHEAT':2},rival_cash=0)
        obs,cfg=fixture['before'],fixture['configuration']
        base={'farmer':['WATER'],'hands':[['CARE']], 'market':[]}
        before=copy.deepcopy((obs,cfg,base))
        policy=LiquidityCycle()
        out=policy.transform(obs,cfg,base)
        self.assertEqual(out['market'],[['SELL','WHEAT',1],['BUY_PRODUCT','WHEAT',1]])
        self.assertEqual((obs,cfg,base),before)
        self.assertEqual(out['farmer'],base['farmer'])
        for reserved in ({'market_slots':[1]},{'stock':{'WHEAT':2}}):
            self.assertEqual(policy.transform(obs,cfg,base,reservations=reserved),base)
        pickup={'farmer':['PICKUP','WHEAT',2],'market':[]}
        self.assertEqual(policy.transform(obs,cfg,pickup),pickup)
        occupied=dict(base,market=[['HIRE']])
        self.assertEqual(policy.transform(obs,cfg,occupied),occupied)
        self.assertEqual(policy.transform(obs,dict(cfg,maxMarketOrdersPerTurn=1),base),base)

    def test_default_price_discontinuity_and_floor_decline(self):
        for inventory,item in ((10000,'WHEAT'),(11000,'FERTILIZER')):
            f=run_market(self.ev,self.engine,inventory=inventory,item=item,own_shed={item:1},rival_cash=0)
            self.assertEqual(LiquidityCycle().transform(f['before'],f['configuration'],{'market':[]}),{'market':[]})

    def test_condition_restores_own_inventory_across_rival_flows(self):
        # This matrix checks immediate own receipt/restoration, not future WTL.
        # Independent same-state rival queues include self-funding and both slots.
        base={'farmer':['PASS'],'market':[]}
        positive=0
        for item,inventory in (('WHEAT',10002),('WHEAT',99980),('FERTILIZER',10010)):
            # WHEAT's far glut may be excluded by the floor condition.
            for seat in (0,1):
                for cash in (0,1):
                    fixture=run_market(self.ev,self.engine,item=item,inventory=inventory,
                                       own_shed={item:1},rival_cash=cash,seat=seat)
                    action=LiquidityCycle().transform(fixture['before'],fixture['configuration'],base)
                    if not action.get('market'):
                        continue
                    options=[[],['BUY_PRODUCT',item,100],['SELL',item,1],['SELL',item,50],['SELL','MILK',1]]
                    for first in options:
                        for second in options:
                            r=self.pair(item=item,inventory=inventory,seat=seat,own_cash=0,
                                        own_shed={item:1},rival_shed={item:99,'MILK':1},rival_cash=cash,
                                        own_orders=action['market'],rival_orders=[first,second])
                            self.assertGreaterEqual(r['cash_delta'][0],0)
                            self.assertEqual(r['actual']['shed'][0],{item:1})
                            positive+=r['cash_delta'][0]>0
        self.assertGreater(positive,0)

    def test_process_pool_record_has_no_dynamic_struct_class(self):
        import pickle
        from panel import plain_record
        record={'events':[self.ev.Struct(nested=self.ev.Struct(cash=17))]}
        output=plain_record(record)
        self.assertIs(type(output['events'][0]),dict)
        self.assertNotIn(b't11_official_evaluator',pickle.dumps(output))

    def test_closed_form_matches_official_quantity_and_rounding(self):
        from cycle_quotes import sell_rebuy_quote
        for inventory in (9970,10000,10100):
            for q in (1,3,10,100):
                for r in (0,1,5,100):
                    for direction in ('SELL','BUY_PRODUCT'):
                        quote=sell_rebuy_quote('WHEAT',inventory,q,r,rival_direction=direction)
                        actual=self.pair(inventory=inventory,own_cash=100000,rival_cash=100000,
                             own_shed={'WHEAT':q},rival_shed={'WHEAT':r} if direction=='SELL' else {},
                             own_orders=[['SELL','WHEAT',q],['BUY_PRODUCT','WHEAT',q]],
                             rival_orders=[[direction,'WHEAT',r]])
                        self.assertEqual(actual['cash_delta'],[quote['own_cash_delta'],quote['rival_cash_delta']])
                        self.assertEqual(actual['actual']['market']['WHEAT'],quote['final_inventory'])
                        self.assertIsNone(quote['probability'])

    def test_temporal_consumption_is_conditional_and_fert_has_none(self):
        for rival_quantity,expected in ((0,1),(5,-1)):
            r=self.pair(own_orders=[['BUY_PRODUCT','WHEAT',1]],
                 rival_orders=[['SELL','WHEAT',rival_quantity]],rival_shed={'WHEAT':rival_quantity},
                 consumption_step=12,shops=['BAKERY']*4,after_consumption_orders=[['SELL','WHEAT',1]])
            self.assertEqual(r['cash_delta'][0],expected)
        r=self.pair(item='FERTILIZER',inventory=10000,
                    own_orders=[['BUY_PRODUCT','FERTILIZER',1]],consumption_step=24,
                    shops=['BAKERY']*4,after_consumption_orders=[['SELL','FERTILIZER',1]])
        self.assertEqual(r['cash_delta'][0],0)
        self.assertEqual(r['actual']['market']['FERTILIZER'],10000)


if __name__=='__main__':
    unittest.main()
