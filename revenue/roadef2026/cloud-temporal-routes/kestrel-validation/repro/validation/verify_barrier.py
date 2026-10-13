#!/usr/bin/env python3
"""Exact rational neighborhood barrier check, independent of either native DP."""
from __future__ import annotations
import argparse
from copy import deepcopy
from itertools import product
import json
from pathlib import Path
from native_screen import evaluate


def solution(routes):
    return {'srpaths':[{'d':d,'t':t,'w':w} for d,row in enumerate(routes) for t,w in enumerate(row) if w]}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--fixture',type=Path,default=Path(__file__).resolve().parent/'fixtures/barrier-094')
    ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    net,tm,scenario,old,new=[json.loads((args.fixture/name).read_text()) for name in
                           ('net.json','tm.json','scenario.json','local-optimum.json','dp-escape.json')]
    before=evaluate(net,tm,scenario,old);after=evaluate(net,tm,scenario,new)
    h=tm['num_time_slots'];ids=[r['id'] for r in net['nodes']]
    interval_checked=0;feasible=0;interval_improvements=[]
    for d,demand in enumerate(tm['demands']):
        pool=[[]]+[[v] for v in ids if v not in (demand['s'],demand['t'])]
        for a in range(h):
            for b in range(a,h):
                for path in pool:
                    routes=deepcopy(before['routes']);routes[d][a:b+1]=[path]*(b-a+1)
                    interval_checked+=1
                    try:ev=evaluate(net,tm,scenario,solution(routes))
                    except (ValueError,AssertionError):continue
                    feasible+=1
                    if ev['vector']<before['vector']:interval_improvements.append([d,a,b,path])
    assert not interval_improvements
    demand=0;pool=[[],[114],[127]];best=None;best_paths=[];schedule_feasible=0
    for path in product(range(len(pool)),repeat=h):
        routes=deepcopy(before['routes']);routes[demand]=[pool[p] for p in path]
        try:ev=evaluate(net,tm,scenario,solution(routes))
        except (ValueError,AssertionError):continue
        schedule_feasible+=1
        if best is None or ev['vector']<best:best=ev['vector'];best_paths=[path]
        elif ev['vector']==best:best_paths.append(path)
    assert after['vector']==best<before['vector']
    assert before['used']==after['used']==[0]*(h-1)+[3]
    assert before['routes'][1:]==after['routes'][1:]
    report={'source':'case 94 from generated seed 8264901; synthetic development only',
            'nodes':len(ids),'demands':len(tm['demands']),'times':h,
            'constant_interval_candidates':interval_checked,'feasible_interval_candidates':feasible,
            'improving_constant_intervals':len(interval_improvements),
            'whole_schedules':len(pool)**h,'feasible_whole_schedules':schedule_feasible,
            'all_optimal_index_paths':best_paths,'pool':pool,
            'old_route':before['routes'][0],'new_route':after['routes'][0],
            'old_budget_use':before['used'],'new_budget_use':after['used'],
            'old_sorted_vector':before['vector'],'new_sorted_vector':after['vector'],
            'first_changed_rank_1based':next(i+1 for i,(a,b) in enumerate(zip(before['vector'],after['vector'])) if a!=b),
            'valid':True,'checker':'Independent exact Fraction ECMP; NOT official Orange checker'}
    args.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
