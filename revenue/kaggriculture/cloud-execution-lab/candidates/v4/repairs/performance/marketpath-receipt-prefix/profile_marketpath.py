# SPDX-License-Identifier: Apache-2.0
"""Local paired timing and allocation profile; not a gameplay-strength gate."""
import argparse, gc, json, statistics, sys, time, tracemalloc
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_marketpath_receipt_prefix as g
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--runtime',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
args_cli=parser.parse_args()
root=args_cli.runtime.resolve()
g.bootstrap(root)
old,new=g.MODULES['selected_sell_core.py']
rows=[]
for item in ['MILK','WOOL','TOMATO']:
 for quantity in [0,1,2,8,30,100]:
  args=dict(item=item,quantity=quantity,inventory=10000,params=None,shops=['SMOOTHIE_SHOP','YARN_STORE','FARMERS_MARKET']*2,config={},now=241,dates=[241,242,245,249],reference=((241,quantity),),rival_quantity=quantity//2,minimum_now=0)
  batch=5 if quantity>=30 else 30
  samples=[[],[]]
  for repetition in range(5):
   for which in ([0,1] if repetition%2==0 else [1,0]):
    gc.collect()
    start=time.perf_counter()
    for _ in range(batch): (old,new)[which].optimize_lot(**args)
    samples[which].append((time.perf_counter()-start)/batch)
  med=[statistics.median(s) for s in samples]
  rows.append(dict(item=item,quantity=quantity,median_seconds=dict(before=med[0],after=med[1]),ratio=med[0]/med[1],samples_seconds=samples))
mem=[]
for module in (old,new):
 gc.collect();tracemalloc.start()
 module.optimize_lot(**args)
 current,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
 mem.append(dict(retained_before_gc=current,peak_bytes=peak))
result=dict(scope='local component profile, synthetic cases, five alternating batches each',cases=rows,memory_last_case={'input':args,'before':mem[0],'after':mem[1]})
with args_cli.output.open('x') as handle:
 json.dump(result,handle,indent=2,allow_nan=False)
 handle.write('\n')
for r in rows: print(r['item'],r['quantity'],round(r['ratio'],3))
print('MEM',mem)
