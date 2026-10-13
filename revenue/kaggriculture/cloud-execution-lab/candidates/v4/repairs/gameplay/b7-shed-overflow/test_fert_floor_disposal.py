#!/usr/bin/env python3
from __future__ import annotations
import copy, unittest
from fert_floor_disposal import analyze_floor_disposal


def observation(step=23, price=1, public=10493):
    return {"step":step,"player":0,"farms":[{"farmer":[4,4],"hands":[]}],
            "private":{"shed":{"FERTILIZER":20,"CARROT":70},"inventories":[{"WHEAT":20}]},
            "market":{"prices":{"FERTILIZER":price},"inventory":{"FERTILIZER":public}}}

def action(market=None): return {"farmer":["PASS"],"hands":[],"market":copy.deepcopy(market or [])}

def post(obs, act, cfg): return obs['farms'][0], copy.deepcopy(obs['private'])
def price(item, inv, params=None):
    # Exact current FERT linear curve around the floor boundary.
    return max(1, int(round(100 - 0.2 * (inv - 10000)))) if inv >= 10000 else 100

class Tests(unittest.TestCase):
    def runit(self, obs=None, act=None, cfg=None):
        return analyze_floor_disposal(obs or observation(), act or action(), cfg or {},
                                      post_units_fn=post, market_price_fn=price)
    def test_capacity_candidate_minimum_quantity(self):
        r=self.runit(); self.assertTrue(r['eligible']); self.assertEqual(r['proposal'],['SELL','FERTILIZER',10])
        self.assertFalse(r['warehouse']); self.assertFalse(r['economic_authorization']); self.assertGreater(r['immediate_round_trip_gap'],0)
    def test_no_overflow(self):
        o=observation();o['private']['shed']={'FERTILIZER':20,'CARROT':50};o['private']['inventories']=[{'WHEAT':20}]
        self.assertEqual(self.runit(o)['reason'],'no_certified_eod_overflow')
    def test_insufficient_fert(self):
        o=observation();o['private']['shed']={'FERTILIZER':5,'CARROT':85};o['private']['inventories']=[{'WHEAT':20}]
        self.assertEqual(self.runit(o)['reason'],'fertilizer_insufficient_for_full_carry')
    def test_non_eod(self): self.assertEqual(self.runit(observation(step=22))['reason'],'not_eod')
    def test_nonfloor(self): self.assertEqual(self.runit(observation(price=2))['reason'],'not_floor')
    def test_existing_fert_touch(self):
        for row in ([['SELL','FERTILIZER',1]],[['BUY_PRODUCT','FERTILIZER',1]]):
            self.assertEqual(self.runit(act=action(row))['reason'],'existing_fertilizer_market_touch')
    def test_market_full(self):
        self.assertEqual(self.runit(act=action([['SELL','WHEAT',1]]*10))['reason'],'no_market_slot')
    def test_current_buys_are_conservative_capacity(self):
        o=observation();o['private']['shed']={'FERTILIZER':30,'CARROT':40};o['private']['inventories']=[{'WHEAT':10}]
        r=self.runit(o,action([['BUY_PRODUCT','WHEAT',25]]));self.assertEqual(r['proposal'],['SELL','FERTILIZER',5])
    def test_post_units_not_raw_state(self):
        o=observation();o['private']['shed']={'FERTILIZER':20,'CARROT':10};o['private']['inventories']=[{}]
        def projected(obs,act,cfg): return obs['farms'][0], {'shed':{'FERTILIZER':20,'CARROT':70},'inventories':[{'MILK':20}]}
        r=analyze_floor_disposal(o,action(),{},post_units_fn=projected,market_price_fn=price)
        self.assertEqual(r['proposal'],['SELL','FERTILIZER',10])
    def test_bool_numeric_rejected(self):
        o=observation();o['market']['inventory']['FERTILIZER']=True
        self.assertEqual(self.runit(o)['reason'],'malformed_market_state')
    def test_missing_abi_rejected(self):
        self.assertEqual(analyze_floor_disposal(observation(),action())['reason'],'missing_current_abi')
    def test_malformed_market_row_rejected(self):
        self.assertEqual(self.runit(act=action(["bad"]))['reason'],'malformed_market')

if __name__=='__main__': unittest.main()
