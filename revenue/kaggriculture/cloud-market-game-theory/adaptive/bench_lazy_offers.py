# SPDX-License-Identifier: Apache-2.0
"""Compare exact prior/current runtime classes on constructed component inputs.

This is not a full-controller benchmark, policy game, or Kaggle time-budget
claim. It uses the supplied-parent fixture and real compiler/ledger/selection.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import platform
import statistics
import time
import test_lazy_offers as test


def hashes(path):
    value=Path(path).read_bytes()
    return {'bytes':len(value), 'sha256':hashlib.sha256(value).hexdigest(),
            'git_blob':hashlib.sha1(b'blob '+str(len(value)).encode()+b'\0'+value).hexdigest()}


def run(original, samples=31):
    if samples<3:
        raise ValueError('At least three timing pairs are required')
    before=test.runtime(original); after=test.runtime()
    parity=0
    for seat in (0,1):
        for mode in ('adaptive','fixed','static'):
            for inventory in (0,40,200):
                for quantity in (2,6):
                    rows=[test.record(p,inventory=inventory,quantity=quantity)
                          for p in ('EGG','MILK','WOOL')]
                    a,o,c=test.scenario(rows,module=before,seat=seat,mode=mode)
                    b,bo,bc=test.scenario(rows,module=after,seat=seat,mode=mode)
                    assert test.observable(a,a.act(o,c))==test.observable(b,b.act(bo,bc))
                    parity+=1
    malformed=[test.record('EGG'),test.record('MILK')]
    malformed[1][1][0]['sales'][0][1]+=1
    old,o,c=test.scenario(malformed,module=before);old.act(o,c)
    new,o,c=test.scenario(malformed,module=after);new.act(o,c)
    assert old.last=={'reason':'ValueError'} and new.last['reason']=='admitted'
    workloads=[]
    for label,n,inv in (('one_window_first_accepted',1,40),
                        ('three_windows_first_accepted',3,40),
                        ('six_windows_first_accepted',6,40),
                        ('three_windows_no_admission',3,100000)):
        products=('EGG','MILK','WOOL','TOMATO','CARROT','STRAWBERRY')[:n]
        records=[test.record(p,inventory=inv) for p in products]
        timings={'eager':[],'lazy':[]};last={}
        for i in range(samples+2):
            cases={name:test.scenario(records,module=module)
                   for name,module in (('eager',before),('lazy',after))}
            snapshots={}
            for name in (('eager','lazy') if i%2 else ('lazy','eager')):
                agent,obs,cfg=cases[name]
                start=time.perf_counter_ns();out=agent.act(obs,cfg);elapsed=time.perf_counter_ns()-start
                snapshots[name]=test.observable(agent,out)
                if i>=2: timings[name].append(elapsed)
                last[name]={'compiled':agent.counts['tables'],
                            'admissions':agent.transformer.counts['admissions']}
            assert snapshots['eager']==snapshots['lazy']
        expected=1 if inv==40 else n
        assert last['eager']['compiled']==n and last['lazy']['compiled']==expected
        summary={k:{'median_ms':statistics.median(v)/1e6,
                    'p95_ms':sorted(v)[int(.95*(len(v)-1))]/1e6,
                    'samples_ns':v} for k,v in timings.items()}
        workloads.append({'name':label,'windows':n,'work':last,'timing':summary,
                          'median_speedup':summary['eager']['median_ms']/summary['lazy']['median_ms']})
    sources=[test.HERE/'runtime.py',test.HERE/'recourse.py',test.HERE.parent/'selector.py',
             test.ROOT/'cloud-plan-continuation/continuation.py',test.LAB/'selected_sell_core.py',
             test.LAB/'selected_action_sell.py',test.LAB/'mechanics.py',
             test.LAB/'reference/decision/decision.py',test.HERE/'test_lazy_offers.py',Path(__file__)]
    return {'scope':'constructed component workloads; supplied parent; no games',
            'python':platform.python_version(),'timed':'Agent.act with fixture parent and real compiler/ledger/selection; excludes import and actor setup',
            'source':{str(p.relative_to(test.ROOT)):hashes(p) for p in sources},
            'original_runtime':hashes(original),'exact_original_parity_cases':parity,
            'negative_control':{'original_reason':old.last['reason'],'lazy_reason':new.last['reason'],
                                'case':'real compiler, malformed second plan after admissible first window'},
            'samples_per_arm':samples,'warmup_pairs':2,'workloads':workloads}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--original-runtime',type=Path,required=True)
    parser.add_argument('--samples',type=int,default=31)
    parser.add_argument('--report',type=Path)
    args=parser.parse_args()
    result=run(args.original_runtime,args.samples)
    content=json.dumps(result,indent=2,sort_keys=True)+'\n'
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(content)
    else:
        print(content,end='')
