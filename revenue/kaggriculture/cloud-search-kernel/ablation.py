# SPDX-License-Identifier: Apache-2.0
"""Equal-cap economic transaction fixtures, not held-game strength evidence."""
import argparse,json,time
from dataclasses import asdict
from entrypoint import load_scheduler
from sell_backend import make_optimizer
from search_kernel import Model,Limits,search

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True);args=p.parse_args()
 seller=load_scheduler();rows=[]
 for quantity in (8,20,60):
  for variant,settings in [('full',{}),('no_cache',{'cache':False}),('no_order_or_pv',{'ordering':False}),('fixed_depth',{'iterative':False})]:
   kw=dict(item='CARROT',quantity=quantity,inventory=10000,params=None,shops=['PET_CAFE'],config={},now=716,dates=(716,717,718),reference=((716,quantity),),rival_quantity=quantity,last=718)
   start=time.perf_counter();plan,info=make_optimizer(seller,seconds=0.03,max_transitions=3500,**settings)(**kw)
   rows.append({'quantity':quantity,'variant':variant,'whole_optimizer_seconds':time.perf_counter()-start,'plan':plan,'incremental_gain':info['incremental_gain'],'receipt_vectors':info['scenarios'],'search':info['search']})
 # Controlled event-extension demonstration, separate from the sale fixtures.
 m=Model(lambda s:('WAIT','SELL') if s[1] else ('WAIT',),lambda s,a,c:(s[0]+1,s[1]-(a=='SELL'),s[2]+((100 if s[0] else 1) if a=='SELL' and s[1] else 0)),lambda s,c:s[2],extend=lambda states:states[0][0]==1)
 events={str(e):asdict(search(m,[(0,1,0)],[None],'WAIT',limits=Limits(seconds=.03,max_transitions=3500,max_depth=1,extensions=e))) for e in (0,1)}
 with open(args.output,'w') as f:json.dump({'method':'same 30ms kernel /3500 transition cap per economic fixture; legacy incumbent computation outside kernel cap; no strength claim from fixtures','rows':rows,'controlled_event_extension':events},f,indent=2);f.write('\n')
 print(json.dumps([{'q':r['quantity'],'variant':r['variant'],'transitions':r['search']['transitions'],'depth':r['search']['completed_depth'],'seconds':round(r['whole_optimizer_seconds'],6),'gain':r['incremental_gain']} for r in rows],indent=2))
if __name__=='__main__':main()
