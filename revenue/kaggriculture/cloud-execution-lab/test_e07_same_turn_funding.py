# SPDX-License-Identifier: Apache-2.0
"""E07 same-turn realized-sale funding contracts; no game execution."""
import hashlib
import json
import unittest
from copy import deepcopy
from pathlib import Path

from frozen_selected import fund_same_turn_acquisition, sale_quantities
from scheduler import MarketPath, m, post_units


ROOT = Path(__file__).resolve().parent


def fixture(shed=None, money=0, now=100):
    farm={'tiles':[[None]*10 for _ in range(10)],'farmer':[4,4],'hands':[],
          'money':money,'hires_today':0,'unlocked_quadrants':['NW']}
    private={'shed':dict(shed or {'MILK':3}), 'seeds':{},'inventories':[{}]}
    obs={'step':now,'player':0,'farms':[farm,deepcopy(farm)],'private':private,
         'market':{'inventory':{p:10000 for p in m.PRODUCTS},
                   'prices':{p:m.market_price(p,10000) for p in m.PRODUCTS}},
         'town':{'unlocked_shops':[]}}
    return obs,{'farmer':['PASS'],'hands':[],'market':[]}


def fund(obs, base, targets, rival=None):
    farm,private=post_units(obs,base,{})
    before=(deepcopy(farm),deepcopy(private))
    out,info=fund_same_turn_acquisition(
        base['market'],farm,private,obs['market'],
        obs['town']['unlocked_shops'],{},obs['step'],targets,rival or {})
    assert (farm,private)==before
    return out,info


class SameTurnFundingContracts(unittest.TestCase):
    def test_exact_one_unit_sale_funds_fixed_seed_without_new_liquidation(self):
        obs,base=fixture(shed={'MILK':3},money=0)
        base['market']=[[],['BUY_SEED','CARROT',1],['SELL','MILK',3]]
        original=deepcopy(base['market'])
        out,info=fund(obs,base,{'MILK'})
        price=m.market_price('MILK',10000)
        self.assertEqual(out,[['SELL','MILK',1],['BUY_SEED','CARROT',1],
                              ['SELL','MILK',2]])
        self.assertEqual(info['moved_quantity'],1)
        self.assertEqual(info['remaining_cash_after_target'],
                         price-m.CROPS['CARROT']['seed'])
        self.assertEqual(sale_quantities(out),sale_quantities(original))
        self.assertEqual(base['market'],original)

    def test_partial_fill_gets_only_the_missing_prefix_receipt(self):
        obs,base=fixture(shed={'EGG':2},money=25)
        base['market']=[[],['BUY_SEED','CARROT',2],['SELL','EGG',2]]
        out,info=fund(obs,base,{'EGG'})
        self.assertEqual(info['baseline_completed'],1)
        self.assertEqual(info['funded_completed'],2)
        self.assertEqual(info['moved_quantity'],1)
        self.assertEqual(out[0],['SELL','EGG',1])
        self.assertEqual(out[2],['SELL','EGG',1])

    def test_rival_before_stress_can_require_two_units_when_no_rival_needs_one(self):
        obs,base=fixture(shed={'MILK':3},money=50)
        base['market']=[[],['BUY_SEED','STRAWBERRY',2],['SELL','MILK',3]]
        no_rival=MarketPath('MILK',10000,None,[],{},obs['step'],obs['step'])
        self.assertGreaterEqual(
            50+no_rival.joint(10000,1,0,'paired')[0],
            2*m.CROPS['STRAWBERRY']['seed'])
        stressed=MarketPath('MILK',10000,None,[],{},obs['step'],obs['step'])
        self.assertLess(
            50+stressed.joint(10000,1,10,'before')[0],
            2*m.CROPS['STRAWBERRY']['seed'])
        out,info=fund(obs,base,{'MILK'},{'MILK':10})
        self.assertEqual(info['moved_quantity'],2)
        self.assertEqual(out[0],['SELL','MILK',2])
        self.assertTrue(any(row['scenario']=='observed_before'
                            for row in info['sale_stress']))

    def test_existing_same_item_sell_is_enlarged_without_moving_purchase_index(self):
        obs,base=fixture(shed={'MILK':4},money=100)
        base['market']=[['SELL','MILK',1],['BUY_ANIMAL','COW',1],
                        ['SELL','MILK',3]]
        out,info=fund(obs,base,{'MILK'})
        self.assertEqual(out,[['SELL','MILK',2],['BUY_ANIMAL','COW',1],
                              ['SELL','MILK',2]])
        self.assertEqual((info['destination_index'],info['source_index']),(0,2))

    def test_no_empty_or_same_item_prefix_slot_declines_without_reordering(self):
        obs,base=fixture(shed={'MILK':1},money=1)
        base['market']=[['HIRE'],['BUY_SEED','CARROT',1],['SELL','MILK',1]]
        original=deepcopy(base['market'])
        out,info=fund(obs,base,{'MILK'})
        self.assertEqual(out,original)
        self.assertEqual(info['reason'],'no-safe-prefix-sale')

    def test_variable_price_buy_is_a_hard_boundary(self):
        obs,base=fixture(shed={'MILK':1},money=0)
        base['market']=[['BUY_PRODUCT','WHEAT',1],[],
                        ['BUY_SEED','CARROT',1],['SELL','MILK',1]]
        original=deepcopy(base['market'])
        out,info=fund(obs,base,{'MILK'})
        self.assertEqual(out,original)
        self.assertEqual(info['reason'],'unsupported-buy-product')
        self.assertEqual(info['barrier_index'],0)


    def test_sell_after_buy_product_boundary_cannot_move_into_prefix(self):
        obs,base=fixture(shed={'MILK':1},money=0)
        base['market']=[[],['BUY_SEED','CARROT',1],
                        ['BUY_PRODUCT','WHEAT',1],['SELL','MILK',1]]
        original=deepcopy(base['market'])
        out,info=fund(obs,base,{'MILK'})
        self.assertEqual(out,original)
        self.assertEqual(info['reason'],'no-safe-prefix-sale')
        self.assertEqual(info['target_index'],1)
        self.assertEqual(sale_quantities(out),sale_quantities(original))
        self.assertEqual(base['market'],original)

    def test_sell_before_buy_product_boundary_can_still_fund_fixed_buy(self):
        obs,base=fixture(shed={'MILK':2},money=0)
        base['market']=[[],['BUY_SEED','CARROT',1],
                        ['SELL','MILK',2],['BUY_PRODUCT','WHEAT',1]]
        original=deepcopy(base['market'])
        out,info=fund(obs,base,{'MILK'})
        self.assertTrue(info['applied'])
        self.assertEqual((info['target_index'],info['source_index']),(1,2))
        self.assertEqual(out[0],['SELL','MILK',1])
        self.assertEqual(out[1],original[1])
        self.assertEqual(out[2],['SELL','MILK',1])
        self.assertEqual(out[3],original[3])
        self.assertEqual(sale_quantities(out),sale_quantities(original))
        self.assertEqual(base['market'],original)

class CanonicalSameTurnFundingBinding(unittest.TestCase):
    def test_committed_current_release_matches_same_turn_funding_source(self):
        from build_integrated import source_files, verify_current
        receipt = verify_current()
        self.assertEqual(source_files()['frozen_selected.py'], 'frozen_selected.py')
        source = (ROOT/'frozen_selected.py').read_bytes()
        recorded = json.loads((ROOT/'runtime/integrated-selected/CURRENT-SOURCE.json').read_text())['runtime']['frozen_selected.py']
        self.assertEqual(recorded['sha256'], hashlib.sha256(source).hexdigest())
        self.assertEqual(recorded['bytes'], len(source))
        self.assertIn(b'def fund_same_turn_acquisition(', source)
        self.assertEqual(receipt['path'], 'exports/titan-current.tar.gz')
        self.assertEqual(receipt['sha256'], hashlib.sha256((ROOT/receipt['path']).read_bytes()).hexdigest())


if __name__=='__main__':
    unittest.main()
