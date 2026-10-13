# SPDX-License-Identifier: Apache-2.0
"""Build wrappers over exact unchanged Arlene; reuse already prepared opponents."""
import argparse,hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parent.parent

def main():
    p=argparse.ArgumentParser();p.add_argument('--runtime',type=Path,required=True);a=p.parse_args()
    parent=ROOT/'cloud-frontier-policy/next-panel/vendor/arlene.py'
    assert hashlib.sha256(parent.read_bytes()).hexdigest()=='1dc166ae2bf0c56a44fac4482f469b8812968c4cb32459cb9860f5077897a7d4'
    # Reuse LARK's standalone transfer helper and existing forecast price mechanics.
    common=f'''import sys, importlib.util
from pathlib import Path
sys.path.insert(0,{str(ROOT/'cloud-frontier-policy/next-panel')!r})
from offline import restrict
restrict()
sys.path.insert(0,{str(HERE)!r})
sys.path.insert(0,{str(ROOT/'cloud-market-forecast')!r})
from execution import SellExecution
import ordered_shed
from forecast_market_mechanics import market_price, SHOPS, TOWN_CENTER_PRODUCTS
spec=importlib.util.spec_from_file_location('intact_arlene',{str(parent)!r})
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
ordered_shed.ANIMALS=base.ANIMALS
ordered_shed._shed_adjacent=base._shed_adjacent
A=None
E=None

def agent(obs,cfg=None):
    global A,E
    cfg=cfg or {{}}
    if A is None or obs['step']==0:
        A=base.Agent();E=SellExecution(MODE)
    action=A.act(obs)
    farm=obs['farms'][obs['player']]
    positions=[farm['farmer'],*farm.get('hands',[])]
    acts=[action.get('farmer',['PASS']),*action.get('hands',[])]
    post,carried=ordered_shed._ordered_shed_projection(obs['private'].get('shed',{{}}),obs['private'].get('inventories',[]),positions,acts,farm['tiles'],int(cfg.get('shedCapacity',100)))
    def quote(p,inv): return market_price(p,inv,obs['market'].get('params'))
    def demand(p,t):
        n=0
        if t%max(1,int(cfg.get('townShopSellInterval',4)))==0:
            for shop in obs.get('town',{{}}).get('unlocked_shops',[]):
                goods=SHOPS[shop]
                if p in goods:n+=2 if len(goods)==1 else 1
        if t%max(1,int(cfg.get('townCenterSellInterval',24)))==0 and p in TOWN_CENTER_PRODUCTS:n+=1
        return n
    future=A.R[A.cur][int(obs['step'])+1:int(obs['step'])+5]
    result=E.transform(obs,cfg,action,post,carried,quote,demand,future)
    assert result['farmer']==action['farmer'] and result['hands']==action['hands']
    return result
'''
    a.runtime.mkdir(parents=True,exist_ok=True)
    for mode in ('baseline','cap','demand'):
        (a.runtime/(mode+'-execution.py')).write_text('MODE='+repr(mode)+'\n'+common)
    manifest={'parent_sha256':hashlib.sha256(parent.read_bytes()).hexdigest(),
              'sources':{str(x.relative_to(ROOT)):hashlib.sha256(x.read_bytes()).hexdigest() for x in [HERE/'execution.py',HERE/'ordered_shed.py',ROOT/'cloud-market-forecast/forecast_market_mechanics.py',parent]},
              'modes':['baseline','cap','demand'],'theta':.05,'alpha':.5,'max_delay_turns':4,
              'development':[9600701,9600719],'reserved':[9600751,9600769]}
    (a.runtime/'execution-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(manifest,indent=2))
if __name__=='__main__':main()
