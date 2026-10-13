# SPDX-License-Identifier: Apache-2.0
"""Compare reused market transitions with the pinned official interpreter."""
import argparse, importlib.util, json, sys
from pathlib import Path
from entrypoint import load_scheduler


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--engine-dir',type=Path,required=True)
 p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 root=Path(__file__).resolve().parent.parent
 spec=importlib.util.spec_from_file_location('t06_conformance_eval',root/'cloud-eval/evaluate.py')
 ev=importlib.util.module_from_spec(spec);sys.modules[spec.name]=ev;spec.loader.exec_module(ev)
 engine,hashes=ev.get_engine(a.engine_dir);seller=load_scheduler();count=0
 for item in ('CARROT','MELON','MILK'):
  for inventory in (9800,10000,10400,12000):
   for quantities in ((0,7),(7,0),(12,12),(3,15)):
    for alignment in ('paired','after','before'):
     market=engine._new_market();market['inventory'][item]=inventory;engine._refresh_prices(market)
     farms=[{'money':0},{'money':0}]
     own=[['SELL',item,quantities[0]]];rival=[['SELL',item,quantities[1]]]
     if alignment=='after':rival=[[],*rival]
     if alignment=='before':own=[[],*own]
     obs=ev.structify({'market':market,'farms':farms,'town':{'unlocked_shops':['PET_CAFE','PET_CAFE']}})
     state=[ev.Struct(observation=ev.Struct(obs,private={'shed':{item:q}}),action={'market':orders}) for q,orders in zip(quantities,(own,rival))]
     cfg=ev.Struct(boardSize=10,maxMarketOrdersPerTurn=10,shedCapacity=100)
     env=ev.Struct(configuration=cfg)
     path=seller.MarketPath(item,inventory,market.get('params'),[],{},716,718)
     x,y,inv=path.joint(inventory,*quantities,alignment)
     engine._process_market(state,env)
     actual=(state[0].observation.farms[0]['money'],state[0].observation.farms[1]['money'],state[0].observation.market['inventory'][item])
     assert (x,y,inv)==actual,(item,inventory,quantities,alignment,(x,y,inv),actual)
     before=actual[2];engine._town_consume(env,state,716)
     consumed=before-state[0].observation.market['inventory'][item]
     assert consumed==seller.absorption(item,716,['PET_CAFE','PET_CAFE'],{})
     count+=1
 a.output.write_text(json.dumps({'cases':count,'passed':count,'engine_sha256':hashes,'scope':'exact paired/ordered SELL, floor supply admission, duplicate-shop consumption; no game simulation substitute'},indent=2)+'\n')
 print(count,'official-engine transaction/consumption cases passed')
if __name__=='__main__':main()
