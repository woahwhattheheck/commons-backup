#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Bind FERT floor-disposal analysis to the authenticated current native ABI."""
from __future__ import annotations
import argparse, copy, hashlib, importlib.util, json, sys, types
from pathlib import Path
from fert_floor_disposal import analyze_floor_disposal

EXPECTED_RUNTIME='b952c9c228ecbde592bf3d2df01638677abb0d24'
EXPECTED_SCHEDULER='a483b24dd72b580d7d8811636b54d2d44f391575'
EXPECTED_ENGINE='3c202c7ee921da239356789e266b694635103fc4'

class Struct(dict):
    __getattr__=dict.get
    def __setattr__(self,k,v):self[k]=v

def git_blob(path):
    b=path.read_bytes();return hashlib.sha1(f'blob {len(b)}\0'.encode()+b).hexdigest()

def load_engine(path):
    if git_blob(path)!=EXPECTED_ENGINE:raise RuntimeError('engine drift')
    pkg=types.ModuleType('kaggle_environments');utils=types.ModuleType('kaggle_environments.utils');utils.resolve_episode_seed=lambda env:0;pkg.utils=utils
    sys.modules['kaggle_environments']=pkg;sys.modules['kaggle_environments.utils']=utils
    spec=importlib.util.spec_from_file_location('_fert_floor_engine_abi',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def fixture(e,seat):
    cfg=Struct({k:(v.get('default') if isinstance(v,dict) else v) for k,v in e.specification['configuration'].items()});cfg.weedSpawnChance=0
    farms=[e._new_farm(10,0),e._new_farm(10,0)];market=e._new_market();market['inventory']['FERTILIZER']=10493;e._refresh_prices(market);town=e._new_town();state=[]
    for i in range(2):
        private=e._new_private()
        if i==seat:
            private['shed']['FERTILIZER']=20;private['shed']['CARROT']=70;private['inventories']=[{'WHEAT':20}]
        state.append(Struct(observation=Struct(player=i,step=23,day=0,hour=23,farms=farms,private=private,market=market,town=town),action={'farmer':['PASS'],'hands':[],'market':[]},status='ACTIVE',reward=0))
    return state,Struct(configuration=cfg,done=False,info={'seed':1})

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--runtime-root',type=Path,required=True);ap.add_argument('--receipt',type=Path);a=ap.parse_args();root=a.runtime_root
    if git_blob(root/'titan_runtime.py')!=EXPECTED_RUNTIME:raise RuntimeError('runtime drift')
    if git_blob(root/'scheduler.py')!=EXPECTED_SCHEDULER:raise RuntimeError('scheduler drift')
    sys.path.insert(0,str(root));import scheduler
    e=load_engine(root/'checks/reference/engine/kaggriculture.py')
    seats=[]
    for seat in (0,1):
        base,be=fixture(e,seat);cand=copy.deepcopy(base);ce=copy.deepcopy(be);obs=cand[seat].observation;parent=copy.deepcopy(cand[seat].action)
        report=analyze_floor_disposal(obs,parent,ce.configuration,post_units_fn=scheduler.post_units,market_price_fn=scheduler.m.market_price)
        assert report['eligible'] and report['proposal']==['SELL','FERTILIZER',10] and report['immediate_round_trip_gap']>0
        cand[seat].action=copy.deepcopy(parent);cand[seat].action['market'].append(report['proposal'])
        e.interpreter(base,be);e.interpreter(cand,ce)
        b=base[seat].observation.private['shed'];c=cand[seat].observation.private['shed']
        assert b['WHEAT']==10 and c['WHEAT']==20
        assert b['FERTILIZER']==20 and c['FERTILIZER']==10
        assert cand[0].observation.market['inventory']['FERTILIZER']==10493
        assert cand[0].observation.farms[seat]['money']==10
        seats.append({'seat':seat,'proposal':report['proposal'],'baseline_eod_wheat':b['WHEAT'],'candidate_eod_wheat':c['WHEAT'],'candidate_fertilizer':c['FERTILIZER'],'public_inventory_after_floor_sale':10493,'cash':10})
    result={'runtime_blob':EXPECTED_RUNTIME,'scheduler_blob':EXPECTED_SCHEDULER,'engine_blob':EXPECTED_ENGINE,'seats':seats,'calls':2,'fallbacks':0,'scope':'current ABI + constructed EOD capacity witness; no economics/default activation'}
    text=json.dumps(result,indent=2,sort_keys=True)+'\n';print(text,end='')
    if a.receipt:a.receipt.write_text(text)
if __name__=='__main__':main()
