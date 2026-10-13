# SPDX-License-Identifier: Apache-2.0
"""Alternating same-workload timings for the exact four-component native stack.

Includes short-horizon controls. Measures optimize_lot only, not win rate or
hosted latency. Garbage collection is enabled; collections before each timed
batch are outside the timer. Source composition and output checks are untimed.
"""
from __future__ import annotations
import argparse
import gc
import json
from pathlib import Path
import statistics
import sys
import time
import types
from compose_optimizer_stack import compose, git_blob


def load(raw, root, name):
    module=types.ModuleType(name);module.__file__=str(root/'selected_sell_core.py')
    exec(compile(raw,module.__file__,'exec'),module.__dict__)
    return module


def workload(horizons):
    for index in range(12):
        now=241; end=now+horizons[index%len(horizons)];quantity=13
        yield dict(item=('WOOL','STRAWBERRY','WHEAT','FERTILIZER')[index%4],
                   quantity=quantity,inventory=(9000,10000,14000)[index%3],
                   params=None,shops=['YARN_STORE','SMOOTHIE_SHOP','FARMERS_MARKET'],
                   config={'sellAcceptanceRule':('strict','expected_downside','minimax_regret')[index%3],
                           'sellDownsideBound':100},now=now,dates=sorted(set([now,now+1,end])),
                   reference=((now,quantity),),rival_quantity=13,last=718)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runtime-root',type=Path,required=True)
    p.add_argument('--components-root',type=Path,default=Path(__file__).parent)
    p.add_argument('--json',type=Path,required=True)
    args=p.parse_args();root=args.runtime_root.resolve();sys.path.insert(0,str(root))
    raw=(root/'selected_sell_core.py').read_bytes();candidate,trace=compose(raw,args.components_root)
    old,new=load(raw,root,'_weave_bench_old'),load(candidate,root,'_weave_bench_new')
    if not gc.isenabled():
        raise RuntimeError('benchmark requires normal garbage collection')
    rows={}
    for cohort,horizons in [('short',[1,3]),('long',[8,24]),('mixed',[1,3,8,24])]:
        inputs=list(workload(horizons))
        reference=[old.optimize_lot(**kw) for kw in inputs]
        if reference != [new.optimize_lot(**kw) for kw in inputs]:
            raise ValueError('pre-timing complete result mismatch')
        samples={'baseline':[],'composed':[]}
        for replicate in range(17):
            for name,core in ([('baseline',old),('composed',new)] if replicate%2==0
                              else [('composed',new),('baseline',old)]):
                gc.collect()
                start=time.perf_counter_ns()
                results=[core.optimize_lot(**kw) for kw in inputs]
                elapsed=(time.perf_counter_ns()-start)/1e9
                if results != reference:
                    raise ValueError('timed complete result mismatch')
                samples[name].append(elapsed)
        before=statistics.median(samples['baseline']);after=statistics.median(samples['composed'])
        rows[cohort]={'calls_per_sample':len(inputs),'samples_seconds':samples,
                      'baseline_median_seconds':before,'composed_median_seconds':after,
                      'speed_ratio':before/after,'fraction_seconds_change':after/before-1}
    report={'schema':'titan-v4-optimizer-stack-timing/v1','optimized':sys.flags.optimize,
            'python':sys.version,'source_git':git_blob(raw),'output_git':git_blob(candidate),
            'cohorts':rows,'scope':'fixed optimizer workload, not whole-agent or economic evidence'}
    with args.json.open('x') as output:json.dump(report,output,indent=2,sort_keys=True);output.write('\n')
    print(json.dumps({name:{key:row[key] for key in ['speed_ratio','fraction_seconds_change']}
                      for name,row in rows.items()},sort_keys=True))

if __name__=='__main__':main()
