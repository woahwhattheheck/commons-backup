# SPDX-License-Identifier: Apache-2.0
"""Independent expected-outcome assertions against complete official callbacks."""
import copy
import os
import random
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import realized_market_ledger as M

REFERENCE = Path(os.environ.get('TITAN_REFERENCE') or (Path(__file__).parent/'../../../../reference'))


class LedgerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.e, cls.loader = M.load_engine(REFERENCE/'engine', REFERENCE/'evaluator/loader.py')

    def world(self, seat=0, *, step=0, cash=3000, **cfg):
        s, env = M.new_game(self.e, self.loader, 1901, **cfg)
        for i in range(2):
            s[i].observation.step = step
            s[i].action = {'farmer': ['PASS'], 'market': []}
        s[0].observation.farms[seat]['money'] = cash
        return s, env

    def audit(self, state, env):
        pristine = copy.deepcopy((state, env))
        original = {n: getattr(self.e, n) for n in M.HOOKS}
        result = M.audit_transition(self.e, state, env)
        self.assertEqual((state, env), pristine, 'input mutation')
        for name in M.HOOKS:
            self.assertIs(getattr(self.e, name), original[name])
        self.assertTrue(result[2]['parity'])
        return result

    def test_unfunded_hire_is_not_hire(self):
        for seat in range(2):
            s, e = self.world(seat, cash=0)
            s[seat].action['market'] = [['HIRE']] * 7
            _, _, r = self.audit(s, e)
            self.assertEqual([x['filled'] for x in r['rows']], [0] * 7)
            self.assertEqual(r['totals'][seat]['hands'], 0)

    def test_hire_fibonacci_and_eod_not_net_hand_inference(self):
        for seat in range(2):
            s, e = self.world(seat, step=23, cash=5)
            s[seat].action['market'] = [['HIRE']] * 7
            out, _, r = self.audit(s, e)
            self.assertEqual([x['filled'] for x in r['rows']], [1, 1, 1, 0, 0, 0, 0])
            self.assertEqual(r['totals'][seat]['cash'], -4)
            self.assertEqual(r['totals'][seat]['hands'], 3)
            self.assertEqual(out[0].observation.farms[seat]['hands'], [])

    def test_zero_price_hire_counts_success(self):
        for seat in range(2):
            s, e = self.world(seat, cash=0, farmHandCostMult=0)
            s[seat].action['market'] = [['HIRE'], ['HIRE']]
            _, _, r = self.audit(s, e)
            self.assertEqual([x['filled'] for x in r['rows']], [1, 1])
            self.assertEqual(r['totals'][seat]['cash'], 0)
            self.assertEqual(r['totals'][seat]['hands'], 2)

    def test_cap_preserves_invalid_raw_slots_and_dead_infinity(self):
        for seat in range(2):
            s, e = self.world(seat, maxMarketOrdersPerTurn=2)
            s[seat].action['market'] = [None, ['HIRE'], ['BUY_PRODUCT', 'WHEAT', float('inf')]]
            # Direct interpreter accepts the unreachable inf without converting it;
            # strict JSON replay transport deliberately does not accept nonfinite rows.
            with M.MarketLedger(self.e) as ledger:
                self.e.interpreter(s, e)
            r = ledger.report()
            self.assertEqual([x['status'] for x in r['rows']], ['invalid', 'filled', 'clipped'])
            self.assertIsNone(r['rows'][2]['requested'])
            self.assertEqual(r['rows'][1]['slot'], 1)

    def test_cap_floor_is_one(self):
        s, e = self.world(maxMarketOrdersPerTurn=0)
        s[0].action['market'] = [['HIRE'], ['HIRE']]
        _, _, r = self.audit(s, e)
        self.assertEqual(r['cap'], 1)
        self.assertEqual([x['filled'] for x in r['rows']], [1, 0])

    def test_partial_sell_counts_inventory_not_request(self):
        for seat in range(2):
            s, e = self.world(seat)
            s[seat].observation.private['shed'] = {'WHEAT': 2}
            s[seat].action['market'] = [['SELL', 'WHEAT', 300]]
            _, _, r = self.audit(s, e)
            row = r['rows'][0]
            self.assertEqual((row['requested'], row['filled'], row['attempts']), (300, 2, 3))
            self.assertEqual(row['status'], 'partial')
            self.assertEqual(row['delta']['shed'], {'WHEAT': -2})

    def test_partial_buy_cash(self):
        for seat in range(2):
            s, e = self.world(seat, cash=51)
            s[seat].action['market'] = [['BUY_SEED', 'CARROT', 100]]
            cost = self.e.CROPS['CARROT']['seed']
            _, _, r = self.audit(s, e)
            row = r['rows'][0]
            self.assertEqual(row['filled'], 51 // cost)
            self.assertEqual(row['delta']['cash'], -cost * (51 // cost))
            self.assertEqual(row['delta']['seeds'], {'CARROT': 51 // cost})

    def test_product_capacity_and_later_hire(self):
        for seat in range(2):
            s, e = self.world(seat, shedCapacity=2)
            s[seat].observation.private['shed'] = {'CARROT': 1}
            s[seat].action['market'] = [['BUY_PRODUCT', 'WHEAT', 10], ['HIRE']]
            _, _, r = self.audit(s, e)
            self.assertEqual([x['filled'] for x in r['rows']], [1, 1])
            self.assertEqual(r['rows'][0]['attempts'], 2)
            self.assertEqual(r['rows'][0]['delta']['market'], {'WHEAT': -1})

    def test_floor_sell_no_market_supply(self):
        for seat in range(2):
            s, e = self.world(seat)
            s[0].observation.market['inventory']['WHEAT'] = 10**15
            s[seat].observation.private['shed'] = {'WHEAT': 3}
            s[seat].action['market'] = [['SELL', 'WHEAT', 3]]
            _, _, r = self.audit(s, e)
            self.assertEqual(r['totals'][seat]['cash'], 3)
            self.assertEqual(r['totals'][seat]['shed'], {'WHEAT': -3})
            self.assertEqual(r['totals'][seat]['market'], {})

    def test_lockstep_prices_same_quote_before_commit(self):
        s, e = self.world()
        for seat in range(2):
            s[seat].observation.private['shed'] = {'WHEAT': 2}
            s[seat].action['market'] = [['SELL', 'WHEAT', 2]]
        inv = s[0].observation.market['inventory']['WHEAT']
        params = s[0].observation.market.get('params')
        p0 = self.e.market_price('WHEAT', inv, params)
        p1 = self.e.market_price('WHEAT', inv+2, params)
        _, _, r = self.audit(s, e)
        self.assertEqual([x['seat'] for x in r['events']], [0, 1, 0, 1])
        self.assertEqual([x['price'] for x in r['events']], [p0, p0, p1, p1])
        self.assertEqual(r['totals'][0]['cash'], p0+p1)
        self.assertEqual(r['totals'][1]['cash'], p0+p1)

    def test_repeated_same_object_slots_and_asymmetric_queues(self):
        s, e = self.world()
        order = ['HIRE']
        s[0].action['market'] = [order, None, order]
        s[1].action['market'] = [['HIRE']]
        _, _, r = self.audit(s, e)
        self.assertEqual([(x['seat'],x['slot']) for x in r['events']], [(0,0),(1,0),(0,2)])
        self.assertEqual([x['slot'] for x in r['rows'] if x['seat']==0], [0,1,2])

    def test_land_atomic_fills_and_saturation(self):
        for seat in range(2):
            s, e = self.world(seat, cash=10000)
            s[seat].action['market'] = [['BUY_LAND']]*5
            _, _, r = self.audit(s, e)
            self.assertEqual([x['filled'] for x in r['rows']], [1,1,1,0,0])
            self.assertEqual(r['totals'][seat]['land'], 3)
            self.assertEqual(r['totals'][seat]['cash'], -7000)

    def test_unsupported_and_malformed_are_not_transactions(self):
        s, e = self.world()
        s[0].action['market'] = [[], ['BUY_PRODUCT','MILK',10], ['SELL','WHEAT',-2],
                                  ['BUY_ANIMAL','GOOSE',0], ['SELL','WHEAT','no']]
        _, _, r = self.audit(s, e)
        self.assertEqual([x['status'] for x in r['rows']], ['invalid','no_attempt','invalid','invalid','invalid'])
        self.assertEqual(r['events'], [])

    def test_farmer_drop_before_sale(self):
        for seat in range(2):
            s, e = self.world(seat)
            s[seat].observation.private['inventories'][0] = {'WHEAT': 2}
            s[seat].observation.private['shed'] = {}
            s[seat].action = {'farmer':['DROP'], 'market':[['SELL','WHEAT',2]]}
            _, _, r = self.audit(s, e)
            self.assertEqual(r['rows'][0]['filled'], 2)
            self.assertEqual(r['market_before'][seat]['shed'], {'WHEAT':2})

    def test_randomized_both_seat_full_interpreter_parity(self):
        rng = random.Random(719281)
        for case in range(240):
            s, e = self.world(step=rng.randrange(718), shedCapacity=rng.randrange(1,101),
                              maxMarketOrdersPerTurn=rng.randrange(0,11))
            for seat in range(2):
                s[0].observation.farms[seat]['money'] = rng.randrange(0,7001)
                s[seat].observation.private['shed'] = {'WHEAT':rng.randrange(15), 'FERTILIZER':rng.randrange(15)}
                pool = [None, ['HIRE'], ['BUY_LAND'], ['BUY_PRODUCT','WHEAT',rng.randrange(1,40)],
                        ['SELL','WHEAT',rng.randrange(1,40)], ['SELL','FERTILIZER',10],
                        ['BUY_ANIMAL','COW',3], ['BUY_SEED','WHEAT',6], ['BUY_PRODUCT','MILK',2]]
                s[seat].action['market'] = [copy.deepcopy(rng.choice(pool)) for _ in range(rng.randrange(14))]
            self.audit(s, e)

    def test_exception_restores_hooks_and_cannot_report_success(self):
        s, e = self.world()
        s[0].action['market'] = [['HIRE'], ['SELL','WHEAT',float('inf')]]
        original = {n:getattr(self.e,n) for n in M.HOOKS}
        ledger = M.MarketLedger(self.e)
        with self.assertRaises(OverflowError):
            with ledger:
                self.e.interpreter(s,e)
        for n in M.HOOKS:
            self.assertIs(getattr(self.e,n), original[n])
        with self.assertRaises(RuntimeError): ledger.report()

    def test_nested_and_reused_observers_rejected(self):
        ledger = M.MarketLedger(self.e)
        with ledger:
            with self.assertRaises(RuntimeError):
                with M.MarketLedger(self.e): pass
        with self.assertRaises(RuntimeError):
            with ledger: pass

    def test_full_state_parity_is_not_only_market_delta(self):
        s, e = self.world()
        original = self.e.interpreter
        def faulty(state, env):
            result = original(state, env)
            if getattr(self.e, '_realized_observer', None):
                state[0].observation.private['inventories'][0]['EGG'] = 77
            return result
        with patch.object(self.e, 'interpreter', faulty):
            with self.assertRaisesRegex(AssertionError, 'full interpreter parity'):
                M.audit_transition(self.e, s, e)

    def test_helper_default_and_inactive_forwarding(self):
        s, e = self.world()
        farm = s[0].observation.farms[0]
        with M.MarketLedger(self.e):
            self.e._do_hire(farm, s[0].observation.private, 10)
        self.assertEqual(farm['money'], 2999)
        self.assertEqual(len(farm['hands']), 1)

    def test_report_is_detached(self):
        s, e = self.world()
        s[0].action['market'] = [['HIRE']]
        with M.MarketLedger(self.e) as ledger: self.e.interpreter(s,e)
        r = ledger.report()
        r['rows'][0]['raw'][0] = 'BAD'
        r['totals'][0]['cash'] = 999
        self.assertEqual(ledger.report()['rows'][0]['raw'], ['HIRE'])
        self.assertEqual(ledger.report()['totals'][0]['cash'], -1)

    def test_reference_missing_or_modified_fails_before_import(self):
        files = ['engine/kaggriculture.py','engine/kaggriculture.json','engine/utils.py','evaluator/loader.py']
        for rel in files:
            for mode in ('missing','modified'):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    for name in files:
                        path = root/name; path.parent.mkdir(parents=True,exist_ok=True)
                        shutil.copyfile(REFERENCE/name,path)
                    if mode=='missing': (root/rel).unlink()
                    else: (root/rel).write_bytes((root/rel).read_bytes()+b'\n# altered\n')
                    with patch.object(M.importlib.util,'spec_from_file_location',side_effect=AssertionError('import occurred')):
                        with self.assertRaises((FileNotFoundError,ValueError)):
                            M.load_engine(root/'engine',root/'evaluator/loader.py')


if __name__ == '__main__':
    unittest.main(verbosity=2)
