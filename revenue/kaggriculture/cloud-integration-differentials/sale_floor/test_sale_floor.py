# SPDX-License-Identifier: Apache-2.0
"""Focused official-market checks for the optional sale-floor selector."""
from __future__ import annotations
from copy import deepcopy
import importlib.util, pathlib, sys, types, unittest
from unittest.mock import patch

HERE=pathlib.Path(__file__).resolve().parent
KAG=HERE.parents[1]
sys.path.insert(0,str(HERE.parent))
import seed_funding as BASE
import sale_floor as S
ENGINE=KAG/'cloud-execution-lab/reference/engine/kaggriculture.py'

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
try:
    import kaggle_environments.utils
    M=load('_sale_floor_engine',ENGINE)
except ModuleNotFoundError:
    pkg=types.ModuleType('kaggle_environments');util=types.ModuleType('kaggle_environments.utils')
    util.resolve_episode_seed=lambda *a,**k: (_ for _ in ()).throw(AssertionError('no game seed'))
    with patch.dict(sys.modules,{'kaggle_environments':pkg,'kaggle_environments.utils':util}):M=load('_sale_floor_engine',ENGINE)
CFG={'boardSize':10,'maxMarketOrdersPerTurn':10,'farmHandCostMult':1,'shedCapacity':100}
CALLS=0

def post(cash=310,seat=0,stock=None,hires=12):
    farms=[M._new_farm(10,cash if i==seat else 10000) for i in (0,1)]
    farms[seat]['hires_today']=hires;farms[seat]['hands']=[list(farms[seat]['farmer']) for _ in range(hires)]
    private=M._new_private();private['inventories'].extend({} for _ in range(hires));private['shed'].update(stock if stock is not None else {'MILK':100})
    market=M._new_market();market['inventory']={k:10_000_000 for k in M.PRODUCTS};M._refresh_prices(market)
    return {'player':seat,'step':100,'farms':farms,'private':private,'market':market}

def pair(orders=None,new=3):
    orders=orders or [['BUY_SEED','WHEAT',17],['SELL','MILK',100],['HIRE']]
    a={'farmer':['PASS'],'hands':[],'market':deepcopy(orders)};b=deepcopy(a)
    for i,o in enumerate(b['market']):
        if o and o[0]=='BUY_SEED':b['market'][i]=[] if new==0 else [o[0],o[1],new];break
    return a,b

def market(obs,action):
    global CALLS;CALLS+=1;seat=obs['player'];farms=deepcopy(obs['farms']);priv=[M._new_private(),M._new_private()];priv[seat]=deepcopy(obs['private']);shared=deepcopy(obs['market'])
    state=[types.SimpleNamespace(observation=types.SimpleNamespace(farms=farms,private=priv[i],market=shared),action=deepcopy(action if i==seat else {'market':[]})) for i in (0,1)]
    M._process_market(state,types.SimpleNamespace(configuration=deepcopy(CFG)));return farms,priv,shared

def noncash(result,seat):
    farms,priv,shared=deepcopy(result);farms[seat].pop('money');priv[seat].pop('seeds');return farms,priv,shared

class Tests(unittest.TestCase):
    def certified(self,obs,a,b):
        chosen,r=S.select_sale_funded_seed_queue(M,obs,a,b,CFG);self.assertEqual(chosen,b);self.assertEqual(r['status'],'certified')
        x,y=market(obs,a),market(obs,b);self.assertEqual(noncash(x,obs['player']),noncash(y,obs['player']));self.assertEqual(y[0][obs['player']]['money']-x[0][obs['player']]['money'],r['paired_current_market_cash_delta']);return x,y,r
    def test_sale_then_hire_both_seats(self):
        for seat in (0,1):
            x,y,r=self.certified(post(seat=seat),*pair());self.assertEqual((x[0][seat]['money'],y[0][seat]['money']),(7.0,147.0));self.assertEqual(r['sale_floor_funding']['guaranteed_sale_receipts'],100)
    def test_exact_threshold_and_underfunded(self):
        a,b=pair();self.certified(post(cash=303),a,b);chosen,r=S.select_sale_funded_seed_queue(M,post(cash=302),a,b,CFG);self.assertEqual(chosen,a);self.assertNotEqual(r['status'],'certified')
    def test_later_sale_cannot_fund_hire(self):
        a,b=pair([['BUY_SEED','WHEAT',17],['HIRE'],['SELL','MILK',100]]);chosen,r=S.select_sale_funded_seed_queue(M,post(),a,b,CFG);self.assertEqual(chosen,a);self.assertNotEqual(r['status'],'certified')
    def test_stock_not_double_credited(self):
        a,b=pair([['BUY_SEED','WHEAT',17],['SELL','MILK',40],['SELL','MILK',40],['HIRE']]);chosen,r=S.select_sale_funded_seed_queue(M,post(cash=333,stock={'MILK':40}),a,b,CFG);self.assertEqual(chosen,a);self.assertEqual(r['sale_floor_funding']['guaranteed_sale_receipts'],40)
    def test_carried_goods_add_no_credit(self):
        o=post(stock={});o['private']['inventories'][0]={'MILK':100};a,b=pair();self.assertEqual(S.select_sale_funded_seed_queue(M,o,a,b,CFG)[0],a)
    def test_fully_funded_is_exact_base_result(self):
        o=post(cash=10000);a,b=pair();self.assertEqual(S.select_sale_funded_seed_queue(M,o,a,b,CFG),BASE.select_seed_queue(M,o,a,b,CFG))
    def test_opt_out_is_exact_base_result(self):
        o=post();a,b=pair();self.assertEqual(S.select_seed_queue(M,o,a,b,CFG,guaranteed_sale_credit=False),BASE.select_seed_queue(M,o,a,b,CFG))
    def test_public_product_bound_composes(self):
        a,b=pair([['BUY_SEED','WHEAT',17],['SELL','MILK',100],['BUY_PRODUCT','WHEAT',20],['HIRE']]);chosen,r=S.select_seed_queue(M,post(cash=550),a,b,CFG,public_product_bounds=True,guaranteed_sale_credit=True);self.assertEqual(chosen,b);self.assertEqual(r['status'],'certified')
    def test_sale_rewrite_requires_revalidation(self):
        o=post();a,b=pair();chosen,_=S.select_sale_funded_seed_queue(M,o,a,b,CFG);chosen['market'][1]=[];self.assertEqual(S.select_sale_funded_seed_queue(M,o,a,chosen,CFG)[0],a)
    def test_invalid_numeric_inputs_stay_rejected(self):
        a,b=pair()
        for cash in (True,float('inf'),float('nan'),-1,310.25):o=post();o['farms'][0]['money']=cash;self.assertNotEqual(S.select_sale_funded_seed_queue(M,o,a,b,CFG)[1]['status'],'certified')

if __name__=='__main__':unittest.main(verbosity=2)
