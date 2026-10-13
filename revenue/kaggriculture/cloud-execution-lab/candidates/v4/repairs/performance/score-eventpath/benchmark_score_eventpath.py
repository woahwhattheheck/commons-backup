# SPDX-License-Identifier: Apache-2.0
"""Interleaved cold-model optimizer timing; not a gameplay/strength evaluation."""
from __future__ import annotations
import argparse
import gc
import hashlib
import json
import platform
import statistics
import time
from test_score_eventpath import setup, MODULES, SOURCES, PINS, ROOT, git_blob
from build_score_eventpath import compose

def workload(horizon):
    cases=[]
    for now in [3,23,96]:
        for item in ['MILK','WOOL','CARROT','FERTILIZER']:
            for q in [10,40,80]:
                end=now+horizon
                cases.append(dict(item=item,quantity=q,inventory=10030,params=None,
                    shops=['SMOOTHIE_SHOP','YARN_STORE','PET_CAFE'],config={},now=now,
                    dates=sorted({now,min(now+1,end),end}),reference=((now,q),),rival_quantity=18))
    return cases

def run(repeats=7):
    setup()
    report={'scope':'local cold-model optimize_lot timing, not whole-agent/field evidence',
            'python':platform.python_version(),'platform':platform.platform(),
            'input_git_blobs':PINS,'repeats':repeats,'results':[]}
    for filename,(base,candidate) in MODULES.items():
        for horizon in [1,3,8,24]:
            cases=workload(horizon)
            reference=[base.optimize_lot(**case) for case in cases]
            if [candidate.optimize_lot(**case) for case in cases]!=reference:
                raise AssertionError(f'optimizer changed for {filename}/{horizon}')
            values={'base':[],'candidate':[]};cpu={'base':[],'candidate':[]}
            for i in range(repeats):
                order=[('base',base),('candidate',candidate)]
                if i%2:order.reverse()
                for label,mod in order:
                    gc.collect();t=time.perf_counter();p=time.process_time()
                    output=[mod.optimize_lot(**case) for case in cases]
                    cpu[label].append(time.process_time()-p);values[label].append(time.perf_counter()-t)
                    if output!=reference:raise AssertionError(f'optimizer changed during {label}/{i}')
            med={k:statistics.median(v) for k,v in values.items()}
            report['results'].append({'source':filename,'horizon':horizon,'cases':len(cases),
                'wall_seconds':values,'cpu_seconds':cpu,'median_wall_seconds':med,
                'speedup_base_over_candidate':med['base']/med['candidate'],
                'median_elapsed_reduction_percent':100*(1-med['candidate']/med['base']),
                'exact_output_sha256':hashlib.sha256(json.dumps(reference,sort_keys=True).encode()).hexdigest()})
    report['candidate_git_blobs']={f:git_blob(compose(s).encode()) for f,s in SOURCES.items()}
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repeats',type=int,default=7)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    if args.repeats<3:parser.error('at least three interleaved repetitions required')
    report=run(args.repeats)
    with open(args.output,'x',encoding='utf-8') as handle:json.dump(report,handle,indent=2);handle.write('\n')
    for row in report['results']:
        print(row['source'],row['horizon'],round(row['median_elapsed_reduction_percent'],2),'percent',row['median_wall_seconds'])
