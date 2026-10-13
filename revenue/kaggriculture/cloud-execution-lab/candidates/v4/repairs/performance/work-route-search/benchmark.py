# SPDX-License-Identifier: Apache-2.0
"""Alternating exact-tour and actual SpatialTempo.transform microbenchmarks."""
from __future__ import annotations
import argparse
from copy import deepcopy
import json
import random
import statistics
import time
from types import SimpleNamespace
from pathlib import Path
import test_work_route as tests


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    rng=random.Random(917341)
    table={}
    for n in range(1,7):
        cells=[]
        for _ in range(24):
            points=rng.sample([(x,y) for x in range(5) for y in range(5)],n)
            groups=[(p,[['WATER']]) for p in points]
            cells.append(((2,2),(4,4),groups,24))
        samples={'baseline':[],'candidate':[]}
        for origin,goal,groups,length in cells:
            if tests.exhaustive(origin,goal,groups,length)!=tests.CAND._minimum_work_trial(origin,goal,groups,length):
                raise AssertionError('benchmark candidate differs')
        for round_index in range(9):
            for label in (('baseline','candidate') if round_index%2==0 else ('candidate','baseline')):
                function=tests.exhaustive if label=='baseline' else tests.CAND._minimum_work_trial
                start=time.perf_counter_ns()
                for _ in range(4):
                    for cell in cells: function(*cell)
                samples[label].append((time.perf_counter_ns()-start)/1e6)
        medians={k:statistics.median(v) for k,v in samples.items()}
        table[str(n)]={'calls_per_batch':96,'raw_ms':samples,'median_ms':medians,
                       'baseline_over_candidate':medians['baseline']/medians['candidate']}
    tests.NativeTransformTests.setUpClass();fixture=tests.NativeTransformTests()
    native={}
    for n in (2,4,6):
        samples={'baseline':[],'candidate':[]}
        for round_index in range(9):
            for label in (('baseline','candidate') if round_index%2==0 else ('candidate','baseline')):
                module=tests.BASE if label=='baseline' else tests.CAND
                elapsed=0.
                for repeat in range(12):
                    state,env,route=fixture.fixture(n,repeat%2,repeat%2)
                    owner=module.SpatialTempo(tests.mechanics,pathing=True,tempo=False)
                    controller=SimpleNamespace(R={'case':route},cur='case')
                    obs=deepcopy(state[repeat%2].observation);selected=deepcopy(route[24])
                    start=time.perf_counter_ns();owner.transform(obs,selected,controller)
                    elapsed+=(time.perf_counter_ns()-start)/1e6
                samples[label].append(elapsed)
        medians={k:statistics.median(v) for k,v in samples.items()}
        native[str(n)]={'transforms_per_batch':12,'raw_ms':samples,'median_ms':medians,
                       'baseline_over_candidate':medians['baseline']/medians['candidate']}
    report={'scope':'Local batch microbenchmarks; existing pathing ON only. Not default speed, whole-game speed or playing strength.',
            'tour':table,'transform':native}
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:{n:round(d['baseline_over_candidate'],3) for n,d in v.items()} for k,v in report.items() if isinstance(v,dict)}))

if __name__=='__main__': main()
