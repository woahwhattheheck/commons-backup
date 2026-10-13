"""Independent state witnesses for the offline market fill observer."""
from copy import deepcopy
import json
import os
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch
import market_fill_ledger as ledger
from run_market_fill_native import load_engine, world, Struct

class FillTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = load_engine(Path(os.environ['TITAN_NATIVE']))

    def case(self, orders=None, seat=0, **cfg):
        state, env = world(self.engine, **cfg)
        state[seat].action = {'market': orders or []}
        return state, env

    def audit(self, state, env):
        original = deepcopy((state, env))
        nxt, nxtenv, report = ledger.audit_transition(self.engine, state, env)
        self.assertEqual((state, env), original)
        self.assertTrue(report['pristine_state_env_equal'])
        self.assertTrue(report['market_reconciled'])
        self.assertEqual(report['status'], 'complete')
        return nxt, nxtenv, report

    def test_hire_is_actual_addition_and_charge(self):
        for seat in (0,1):
            s,e=self.case([['HIRE']],seat); n,_,r=self.audit(s,e);row=r['rows'][0]
            self.assertEqual(row['seat'],seat)
            self.assertEqual((row['filled_units'],row['delta']['hands'],row['delta']['money']),(1,1,-1))
            self.assertEqual(len(n[seat].observation.farms[seat]['hands']),1)

    def test_failed_hire_retains_requested_denominator(self):
        s,e=self.case([['HIRE']]*4);s[0].observation.farms[0]['money']=2
        _,_,r=self.audit(s,e)
        self.assertEqual([x['filled_units'] for x in r['rows']],[1,1,0,0])
        g=ledger.summarize([r])['groups'][0]
        self.assertEqual((g['submitted_rows'],g['filled_units'],g['requested_units_in_cap'],g['cash_delta']),(4,2,4,-2))

    def test_successful_end_of_day_hire_not_in_final_hands(self):
        for seat in (0,1):
            s,e=self.case([['HIRE']],seat,step=23);n,_,r=self.audit(s,e)
            self.assertEqual(r['rows'][0]['filled_units'],1)
            self.assertEqual(n[seat].observation.farms[seat]['hands'],[])
            self.assertEqual(r['phases'][-1]['delta'][seat]['hands'],-1)

    def test_buy_product_cash_partial(self):
        s,e=self.case([['BUY_PRODUCT','WHEAT',1000]])
        s[0].observation.farms[0]['money']=26
        _,_,r=self.audit(s,e);row=r['rows'][0]
        self.assertEqual((row['requested_units'],row['filled_units'],row['attempts'],row['failed_attempts']),(1000,1,2,1))
        self.assertEqual(row['delta']['shed'],{'WHEAT':1})
        self.assertEqual(row['outcome'],'partial')
        self.assertEqual(row['delta']['money'],-26)

    def test_zero_cash_does_not_invent_purchased_units(self):
        s,e=self.case([['BUY_PRODUCT','WHEAT',1000]],startingMoney=0)
        _,_,r=self.audit(s,e);row=r['rows'][0]
        self.assertEqual(row['filled_units'],0)
        self.assertEqual(row['delta']['market_inventory'],{})
        self.assertEqual(row['outcome'],'unfilled')

    def test_shed_capacity_partial(self):
        s,e=self.case([['BUY_PRODUCT','WHEAT',9]],shedCapacity=3)
        s[0].observation.private['shed']={'MILK':2}
        _,_,r=self.audit(s,e)
        self.assertEqual(r['rows'][0]['filled_units'],1)

    def test_animal_buy_obeys_shed_capacity(self):
        s,e=self.case([['BUY_ANIMAL','COW',5]],shedCapacity=1,startingMoney=100000)
        _,_,r=self.audit(s,e)
        self.assertEqual(r['rows'][0]['filled_units'],1)
        self.assertEqual(r['rows'][0]['delta']['shed'],{'COW':1})

    def test_seeds_are_not_product_storage(self):
        s,e=self.case([['BUY_SEED','WHEAT',3]],shedCapacity=1)
        s[0].observation.private['shed']={'COW':1}
        _,_,r=self.audit(s,e)
        self.assertEqual(r['rows'][0]['filled_units'],3)
        self.assertEqual(r['rows'][0]['delta']['seeds'],{'WHEAT':3})
        self.assertEqual(r['rows'][0]['delta']['shed'],{})

    def test_floor_sale_fills_without_added_supply(self):
        for seat in (0,1):
            s,e=self.case([['SELL','FERTILIZER',9]],seat)
            s[seat].observation.private['shed']={'FERTILIZER':3}
            s[0].observation.market['inventory']['FERTILIZER']=10**9
            _,_,r=self.audit(s,e);row=r['rows'][0]
            self.assertEqual(row['filled_units'],3)
            self.assertEqual(row['delta']['money'],3)
            self.assertEqual(row['delta']['market_inventory'],{})
            self.assertEqual(row['fill_price_counts'],{'1':3})
            self.assertEqual(row['delta']['shed'],{'FERTILIZER':-3})

    def test_raw_slots_not_compacted(self):
        s,e=self.case([None,['HIRE'],['HIRE']],maxMarketOrdersPerTurn=2)
        _,_,r=self.audit(s,e)
        self.assertEqual([x['raw_slot'] for x in r['rows']],[0,1,2])
        self.assertEqual([x['outcome'] for x in r['rows']],['invalid','filled','over_cap'])
        self.assertIsNone(r['rows'][2]['requested_units'])

    def test_effective_cap_is_at_least_one(self):
        s,e=self.case([['HIRE'],['HIRE']],maxMarketOrdersPerTurn=0)
        _,_,r=self.audit(s,e)
        self.assertEqual(r['effective_cap'],1)
        self.assertEqual([x['filled_units'] for x in r['rows']],[1,0])

    def test_simultaneous_sale_quotes_and_seat_identity(self):
        s,e=self.case([['SELL','WHEAT',3]])
        for seat in (0,1):
            s[seat].action={'market':[['SELL','WHEAT',3]]}
            s[seat].observation.private['shed']={'WHEAT':3}
        _,_,r=self.audit(s,e);a,b=r['rows']
        self.assertEqual((a['seat'],b['seat']),(0,1))
        self.assertEqual(a['fill_price_counts'],b['fill_price_counts'])
        self.assertEqual(a['delta']['money'],b['delta']['money'])
        self.assertEqual(a['filled_units'],3)
        self.assertEqual(r['market_delta'][0]['market_inventory'],{'WHEAT':6})

    def test_same_row_alias_still_separate_slots_and_seats(self):
        hire=['HIRE'];s,e=self.case([hire,hire]);s[1].action={'market':[hire]}
        _,_,r=self.audit(s,e)
        self.assertEqual([(x['seat'],x['raw_slot']) for x in r['rows']],[(0,0),(0,1),(1,0)])
        self.assertEqual([x['filled_units'] for x in r['rows']],[1,1,1])

    def test_sale_then_buy_gross_fills_not_net_stock(self):
        s,e=self.case([['SELL','WHEAT',2],['BUY_PRODUCT','WHEAT',2]])
        s[0].observation.private['shed']={'WHEAT':2}
        n,_,r=self.audit(s,e)
        self.assertEqual([x['filled_units'] for x in r['rows']],[2,2])
        self.assertEqual(r['market_delta'][0]['shed'],{})
        self.assertEqual(n[0].observation.private['shed']['WHEAT'],2)

    def test_town_movement_not_charged_to_player(self):
        s,e=self.case([['SELL','WHEAT',2]],step=0)
        s[0].observation.private['shed']={'WHEAT':2}
        _,_,r=self.audit(s,e)
        self.assertEqual(r['rows'][0]['delta']['market_inventory'],{'WHEAT':2})
        self.assertEqual(r['phases'][0]['delta'][0]['market_inventory']['WHEAT'],-1)

    def test_end_of_day_transfer_not_counted_as_market_buy(self):
        s,e=self.case(step=23);s[0].observation.private['inventories']=[{'WHEAT':3}]
        n,_,r=self.audit(s,e)
        self.assertEqual(r['rows'],[])
        self.assertEqual(r['phases'][-1]['delta'][0]['shed'],{'WHEAT':3})
        self.assertEqual(n[0].observation.private['shed']['WHEAT'],3)

    def test_drop_before_market_can_fund_sale(self):
        s,e=self.case([['SELL','WHEAT',3]])
        s[0].observation.private['inventories']=[{'WHEAT':3}]
        s[0].action['farmer']=['DROP','WHEAT',3]
        _,_,r=self.audit(s,e)
        self.assertEqual(r['rows'][0]['filled_units'],3)
        self.assertEqual(r['market_delta'][0]['shed'],{'WHEAT':-3})

    def test_land_unfilled_after_all_quadrants(self):
        s,e=self.case([['BUY_LAND']]*5,startingMoney=100000)
        _,_,r=self.audit(s,e)
        self.assertEqual([x['filled_units'] for x in r['rows']],[1,1,1,0,0])
        self.assertEqual(sum(x['delta']['quadrants'] for x in r['rows']),3)

    def test_invalid_and_unsupported_orders(self):
        s,e=self.case([{},[],['SELL','WHEAT','bad'],['SELL','NO_SUCH',2],['HIRE']])
        _,_,r=self.audit(s,e)
        self.assertEqual([x['outcome'] for x in r['rows']],['invalid','invalid','invalid','unfilled','filled'])
        self.assertEqual(r['rows'][3]['attempts'],0)

    def test_nonlist_market_and_nondict_action(self):
        s,e=self.case();s[0].action={'market':('HIRE',)};s[1].action=['HIRE']
        _,_,r=self.audit(s,e);self.assertEqual(r['rows'],[])

    def test_numeric_conversion_preserves_exception_and_restores(self):
        s,e=self.case([['SELL','WHEAT',float('inf')]])
        a,b=deepcopy((s,e));c,d=deepcopy((s,e))
        observer=ledger.MarketFillLedger(self.engine)
        with self.assertRaises(OverflowError):observer.run(a,b)
        with self.assertRaises(OverflowError):self.engine.interpreter(c,d)
        self.assertEqual((a,b),(c,d))
        self.assertEqual(observer.report['status'],'engine_or_observer_exception')
        for name,fn in observer.original.items():self.assertIs(getattr(self.engine,name),fn)
        self.assertFalse(hasattr(self.engine,'_fill_ledger_active'))

    def test_context_exception_always_restores(self):
        observer=ledger.MarketFillLedger(self.engine)
        with self.assertRaisesRegex(RuntimeError,'injected'):
            with observer.installed():raise RuntimeError('injected')
        for name,fn in observer.original.items():self.assertIs(getattr(self.engine,name),fn)

    def test_nested_observer_rejected(self):
        observer=ledger.MarketFillLedger(self.engine)
        with observer.installed():
            with self.assertRaises(RuntimeError):
                with observer.installed():pass
            with self.assertRaises(ValueError):ledger.MarketFillLedger(self.engine)

    def test_one_shot_and_no_market_are_not_completed_receipts(self):
        s,e=self.case();e.done=True;observer=ledger.MarketFillLedger(self.engine)
        r=observer.run(s,e)
        self.assertEqual(r['status'],'no_market_transition')
        with self.assertRaises(ValueError):ledger.summarize([r])
        with self.assertRaises(RuntimeError):observer.run(s,e)

    def test_engine_source_drift_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'changed.py';p.write_bytes(Path(self.engine.__file__).read_bytes()+b'\n')
            with patch.object(self.engine,'__file__',str(p)):
                with self.assertRaises(ValueError):ledger.MarketFillLedger(self.engine)

    def test_summary_refuses_unreconciled_status(self):
        for status in ('running','not_run','engine_or_observer_exception'):
            with self.assertRaises(ValueError):ledger.summarize([{'status':status}])
        with self.assertRaises(ValueError):ledger.summarize([{'status':'complete','market_reconciled':False}])

    def test_randomized_both_seat_full_engine_matrix(self):
        rng=random.Random(370172)
        for case in range(256):
            s,e=self.case(step=rng.choice([0,1,23,24,47]),shedCapacity=rng.randint(1,9),maxMarketOrdersPerTurn=rng.randint(0,4))
            for seat in (0,1):
                s[seat].observation.farms[seat]['money']=rng.choice([0,1,2,26,55,2000])
                s[seat].observation.private['shed']={x:rng.randint(0,4) for x in ('WHEAT','FERTILIZER','MILK')}
                orders=[['HIRE'],['BUY_PRODUCT','WHEAT',7],['SELL','FERTILIZER',9],['SELL','MILK',3],None,['BUY_LAND']]
                s[seat].action={'market':[deepcopy(rng.choice(orders)) for _ in range(rng.randint(0,6))]}
            n,_,r=self.audit(s,e)
            for row in r['rows']:
                if row['verb'] in ('BUY_PRODUCT','SELL') and row['attempts']:
                    sign=1 if row['verb']=='BUY_PRODUCT' else -1
                    self.assertEqual(row['delta']['shed'].get(row['item'],0),sign*row['filled_units'])
                    actual_cash=sum(float(p)*count for p,count in row['fill_price_counts'].items())
                    self.assertEqual(row['delta']['money'],-sign*actual_cash)
                if not row['in_cap']:self.assertEqual(row['filled_units'],0)
            json.dumps(r,allow_nan=False)

if __name__=='__main__':unittest.main(verbosity=2)
