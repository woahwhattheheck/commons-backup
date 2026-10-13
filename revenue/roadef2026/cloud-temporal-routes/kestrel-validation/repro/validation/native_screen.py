#!/usr/bin/env python3
"""Real native solver comparison on generated network instances.

The independent evaluator uses exact rational ECMP and segment-set budgets.
This is NOT Orange's official checker or an official benchmark corpus.
"""
from __future__ import annotations
from collections import defaultdict
from fractions import Fraction
import argparse
import heapq
import itertools
import json
import math
import os
from pathlib import Path
import random
import subprocess
import time


def forwarding(net, scenario, t, source, target):
    edges=net['links']; banned={e for x in scenario['interventions'] if x['t']==t for e in x['links']}
    incoming=defaultdict(list); outgoing=defaultdict(list)
    for i,e in enumerate(edges):
        if e['id'] not in banned:
            incoming[e['to']].append((i,e)); outgoing[e['from']].append((i,e))
    dist={target:0}; heap=[(0,target)]
    while heap:
        value,v=heapq.heappop(heap)
        if value!=dist[v]:continue
        for _,e in incoming[v]:
            nv=value+e['metric']; u=e['from']
            if nv<dist.get(u,math.inf):dist[u]=nv;heapq.heappush(heap,(nv,u))
    if source not in dist:raise ValueError('Unreachable segment')
    flow=defaultdict(Fraction); received=defaultdict(Fraction); received[source]=Fraction(1)
    for u in sorted(dist,key=lambda x:dist[x],reverse=True):
        if not received[u] or u==target:continue
        nxt=[(i,e) for i,e in outgoing[u] if e['to'] in dist and dist[u]==e['metric']+dist[e['to']]]
        if not nxt:raise ValueError('No forwarding edge')
        amount=received[u]/len(nxt)
        for i,e in nxt:flow[i]+=amount/e['capacity'];received[e['to']]+=amount
    return dict(flow)


def route_flow(net,scenario,t,demand,waypoints):
    path=[demand['s'],*waypoints,demand['t']]; result=defaultdict(Fraction)
    for a,b in zip(path,path[1:]):
        for i,value in forwarding(net,scenario,t,a,b).items():result[i]+=value
    return dict(result)


def distance(demand,a,b):
    def segments(w):
        p=[demand['s'],*w,demand['t']];return set(zip(p,p[1:]))
    return len(segments(a)^segments(b))


def evaluate(net,tm,scenario,solution):
    h=tm['num_time_slots']; ds=tm['demands']; nids={n['id'] for n in net['nodes']}
    routes=[[[] for _ in range(h)] for _ in ds]; seen=set()
    for row in solution['srpaths']:
        d,t,w=row['d'],row['t'],row['w']
        assert type(d)is int and type(t)is int and 0<=d<len(ds) and 0<=t<h
        assert (d,t) not in seen;seen.add((d,t))
        assert len(w)+1<=scenario['max_segments'] and len(set(w))==len(w)
        assert all(x in nids and x not in (ds[d]['s'],ds[d]['t']) for x in w)
        routes[d][t]=w
    budgets={r['t']:r['value'] for r in scenario['budget']}; used=[0]*h
    loads=[[Fraction(0)]*len(net['links']) for _ in range(h)]
    for d,demand in enumerate(ds):
        for t in range(h):
            if t:used[t]+=distance(demand,routes[d][t-1],routes[d][t])
            for e,value in route_flow(net,scenario,t,demand,routes[d][t]).items():
                loads[t][e]+=Fraction(demand['v'][t])*value
    assert all(used[t]<=budgets.get(t,0) for t in range(1,h)),(used,budgets)
    vector=sorted((int(x*1000000) for row in loads for x in row),reverse=True)
    return {'valid':True,'vector':vector,'used':used,'routes':routes,
            'loads':[[float(x) for x in row] for row in loads]}


def generate(rng,index):
    n=rng.randint(4,8); ids=[101+13*i for i in range(n)]; edges=[]
    for a in range(n):
        for b in range(n):
            if a!=b:
                edges.append({'id':500+len(edges)*7,'from':ids[a],'to':ids[b],
                              'metric':rng.randint(1,9),'capacity':rng.choice([10,20,25,40,50,100])})
    h=rng.randint(3,9); num=rng.randint(2,7); demands=[]
    for _ in range(num):
        s,t=rng.sample(ids,2)
        demands.append({'s':s,'t':t,'v':[rng.choice([0,10,20,40,60,80,100]) for _ in range(h)]})
    # Preserve a directed ring to keep every period strongly connected.
    removable=[e['id'] for e in edges if (ids.index(e['from'])+1)%n!=ids.index(e['to'])]
    interventions=[{'t':t,'links':rng.sample(removable,rng.randint(0,min(3,len(removable))))} for t in range(h)]
    return ({'nodes':[{'id':i,'name':f'n{i}'} for i in ids], 'links':edges,'directed':True,'multigraph':False},
            {'num_time_slots':h,'demands':demands},
            {'max_segments':4,'budget':[{'t':t,'value':rng.choice([0,3,4,6,8,12])} for t in range(1,h)],
             'interventions':interventions})


def execute(binary,paths,out,*,enabled,rounds):
    env=dict(os.environ,SEDGE_SECONDS='30',SEDGE_MAX_ROUNDS=str(rounds),SEDGE_STATS=str(out.with_suffix('.stats.json')),
             KESTREL_TEMPORAL=str(int(enabled)),KESTREL_DP_ROUTES='32',KESTREL_DP_DEMANDS='100')
    start=time.perf_counter()
    run=subprocess.run([str(Path(binary).resolve()),*map(str,paths),str(out)],env=env,text=True,
                       capture_output=True,timeout=35,check=True)
    elapsed=time.perf_counter()-start
    out.with_suffix('.log').write_text(run.stdout+run.stderr)
    return json.loads(out.read_text()),json.loads(out.with_suffix('.stats.json').read_text()),elapsed


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--baseline',required=True);ap.add_argument('--candidate',required=True)
    ap.add_argument('--output',type=Path,required=True);ap.add_argument('--count',type=int,default=160)
    ap.add_argument('--rounds',type=int,default=64);args=ap.parse_args()
    args.output.mkdir(parents=True,exist_ok=True);rng=random.Random(8264901);records=[]
    for i in range(args.count):
        folder=args.output/f'case-{i:03d}';folder.mkdir(exist_ok=True)
        net,tm,scenario=generate(rng,i);paths=[]
        for name,data in zip(('net','tm','scenario'),(net,tm,scenario)):
            path=folder/f'{name}.json';path.write_text(json.dumps(data,sort_keys=True)+'\n');paths.append(path)
        a,sa,ta=execute(args.baseline,paths,folder/'baseline.json',enabled=False,rounds=args.rounds)
        b,sb,tb=execute(args.candidate,paths,folder/'candidate.json',enabled=True,rounds=args.rounds)
        ea,eb=evaluate(net,tm,scenario,a),evaluate(net,tm,scenario,b)
        assert eb['vector']<=ea['vector'],('REGRESSION',i)
        for result,stats in ((ea,sa),(eb,sb)):
            actual=[x for row in result['loads'] for x in row]
            assert len(actual)==len(stats['loads'])
            assert all(abs(x-y['sat'])<1e-8 for x,y in zip(actual,stats['loads']))
            assert result['used']==stats['budget_used']
        if i<12:
            disabled,_,_=execute(args.candidate,paths,folder/'disabled.json',enabled=False,rounds=args.rounds)
            assert disabled==a,('DISABLED_CHANGED',i)
        first=next((j for j,(x,y) in enumerate(zip(ea['vector'],eb['vector'])) if x!=y),None)
        record={'case':i,'improved':first is not None,'first_changed_rank':first,
                'old_load':None if first is None else ea['vector'][first]/1e6,
                'new_load':None if first is None else eb['vector'][first]/1e6,
                'baseline_seconds':ta,'candidate_seconds':tb,
                'baseline_vector':ea['vector'],'candidate_vector':eb['vector'],
                'baseline_used':ea['used'],'candidate_used':eb['used'],
                'accepted_delta':sb['accepted']-sa['accepted']}
        records.append(record)
        (args.output/'records.json').write_text(json.dumps(records,indent=2)+'\n')
        if (i+1)%20==0:print(f"{i+1}: {sum(r['improved'] for r in records)} improved",flush=True)
    summary={'generated_instances':args.count,'generator_seed':8264901,'improved':sum(r['improved'] for r in records),
             'equal':sum(not r['improved'] for r in records),'regressed':0,'independent_feasibility_checks':2*args.count,
             'disabled_parity_cases':min(args.count,12),'rounds':args.rounds,
             'scope':'Synthetic network development screen; rational independent evaluator, NOT official checker or set B'}
    (args.output/'SUMMARY.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
