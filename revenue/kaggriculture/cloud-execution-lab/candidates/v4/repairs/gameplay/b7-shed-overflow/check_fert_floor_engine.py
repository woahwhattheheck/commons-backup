#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Executable official-engine proof that $1 FERT sales are disposal, not storage."""
from __future__ import annotations
import argparse, copy, hashlib, importlib.util, json, sys, types
from pathlib import Path

EXPECTED_ENGINE_BLOB='3c202c7ee921da239356789e266b694635103fc4'

class Struct(dict):
    __getattr__ = dict.get
    def __setattr__(self,key,value): self[key]=value

def git_blob(path):
    b=path.read_bytes();return hashlib.sha1(f'blob {len(b)}\0'.encode()+b).hexdigest()

def load_engine(path):
    if git_blob(path)!=EXPECTED_ENGINE_BLOB: raise RuntimeError(f'engine drift: {git_blob(path)}')
    pkg=types.ModuleType('kaggle_environments');utils=types.ModuleType('kaggle_environments.utils')
    utils.resolve_episode_seed=lambda env: int(getattr(env,'info',{}).get('seed',0))
    pkg.utils=utils;sys.modules['kaggle_environments']=pkg;sys.modules['kaggle_environments.utils']=utils
    spec=importlib.util.spec_from_file_location('_fert_floor_engine',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def fixture(e, *, stock=(100,0), inventory=10492, cash=100000):
    cfg=Struct({k:(v.get('default') if isinstance(v,dict) else v) for k,v in e.specification['configuration'].items()})
    cfg.weedSpawnChance=0
    farms=[e._new_farm(10,cash),e._new_farm(10,cash)];market=e._new_market();market['inventory']['FERTILIZER']=inventory;e._refresh_prices(market);town=e._new_town();state=[]
    for seat in range(2):
        private=e._new_private();private['shed']['FERTILIZER']=stock[seat]
        state.append(Struct(observation=Struct(player=seat,step=1,day=0,hour=1,farms=farms,private=private,market=market,town=town),action={'farmer':['PASS'],'hands':[],'market':[]},status='ACTIVE',reward=0))
    return state,Struct(configuration=cfg,done=False,info={'seed':9600803})

def sell_then_buy(e, *, two_seat=False):
    state,env=fixture(e,stock=(100,100 if two_seat else 0))
    state[0].action['market']=[['SELL','FERTILIZER',100]]
    if two_seat: state[1].action['market']=[['SELL','FERTILIZER',100]]
    before=[f['money'] for f in state[0].observation.farms];e._process_market(state,env)
    sold_cash=[state[0].observation.farms[i]['money']-before[i] for i in range(2)]
    inventory_after_sale=state[0].observation.market['inventory']['FERTILIZER']
    cash=state[0].observation.farms[0]['money'];state[0].action['market']=[['BUY_PRODUCT','FERTILIZER',100]];state[1].action['market']=[];e._process_market(state,env)
    buyback_cost=cash-state[0].observation.farms[0]['money']
    return {'two_seat':two_seat,'inventory_after_sale':inventory_after_sale,'sale_cash':sold_cash,'buyback_cost_100':buyback_cost,'inventory_after_buyback':state[0].observation.market['inventory']['FERTILIZER']}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--engine',type=Path,required=True);ap.add_argument('--receipt',type=Path);a=ap.parse_args();e=load_engine(a.engine)
    floor=min(i for i in range(10000,10600) if e.market_price('FERTILIZER',i)==1)
    single=sell_then_buy(e,two_seat=False);dual=sell_then_buy(e,two_seat=True)
    assert floor==10493
    assert single['inventory_after_sale']==10493 and single['sale_cash'][0]==101 and single['buyback_cost_100']==1150
    assert dual['inventory_after_sale']==10494 and dual['sale_cash']==[101,101] and dual['buyback_cost_100']==1130
    result={'engine_blob':EXPECTED_ENGINE_BLOB,'fert_floor_inventory':floor,'single_seat':single,'two_seat_lockstep':dual,'conclusion':'floor SELL is paid disposal, not recoverable market custody','warehouse_claim':False}
    text=json.dumps(result,indent=2,sort_keys=True)+'\n';print(text,end='')
    if a.receipt:a.receipt.write_text(text)
if __name__=='__main__':main()
