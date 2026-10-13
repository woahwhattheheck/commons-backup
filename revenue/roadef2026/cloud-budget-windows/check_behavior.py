#!/usr/bin/env python3
"""Checker-backed asymmetric-window control, ablation and compatibility cases."""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess


def score(value):
    if value.get('valid') is not True:
        raise AssertionError('official checker rejected the generated fixture')
    return sorted((r['sat'] for r in value['saturations']), reverse=True)


def fixture(h, left, right, allowance=3, segments=2, ids=None, zero=False):
    ids = ids or list(range(4))
    links = [(0,1,1),(1,3,1),(0,2,2),(2,3,2)]
    links += [(b,a,c) for a,b,c in links[:]]
    net = {'directed':True,'multigraph':False,'nodes':[{'id':v,'name':str(v)} for v in ids],
           'links':[{'id':i,'from':ids[a],'to':ids[b],'metric':c,'capacity':10} for i,(a,b,c) in enumerate(links)]}
    active = [left <= t <= right for t in range(h)]
    tm = {'num_time_slots':h,'demands':[
        {'s':ids[0],'t':ids[3],'v':[0 if zero else 8 if x else 1 for x in active]},
        {'s':ids[2],'t':ids[3],'v':[0 if x else 10 for x in active]},
        {'s':ids[1],'t':ids[3],'v':[1 if x else 0 for x in active]}]}
    scenario = {'max_segments':segments,'budget':[{'t':t,'value':allowance if t in [left,right+1] else 0} for t in range(1,h)],'interventions':[]}
    return net, tm, scenario


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--parent', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, default=Path(__file__).with_name('solver'))
    parser.add_argument('--checker', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    for k in ['parent','candidate','checker','output']:setattr(args,k,getattr(args,k).resolve())
    args.output.mkdir(parents=True,exist_ok=True)
    cases = [('long',17,4,12,3,2,None,False,True),
             ('shifted',17,2,10,3,2,None,False,True),
             ('mirrored',17,6,14,3,2,None,False,True),
             ('longer',21,6,16,3,2,None,False,True),
             ('node-ids',17,4,12,3,2,[10,20,30,40],False,True),
             ('short-budget',17,4,12,2,2,None,False,False),
             ('zero-budget',17,4,12,0,2,None,False,False),
             ('segment-cap',17,4,12,3,1,None,False,False),
             ('zero-target',17,4,12,3,2,None,True,False)]
    rows = []
    for name,h,left,right,allowance,segments,ids,zero,improve in cases:
        folder=args.output/name;folder.mkdir(exist_ok=True)
        inputs=[]
        for suffix,obj in zip(['net','tm','scenario'],fixture(h,left,right,allowance,segments,ids,zero)):
            p=folder/(suffix+'.json');p.write_text(json.dumps(obj));inputs.append(p)
        incumbent=folder/'incumbent.json';incumbent.write_text('{"srpaths":[]}\n')
        results={};stats={}
        for label,exe,boundaries in [('parent',args.parent,4),('candidate',args.candidate,4),('disabled',args.candidate,0),('nearest-only',args.candidate,1)]:
            solution=folder/(label+'.json');stat=folder/(label+'-stats.json')
            env=dict(os.environ,SEDGE_SECONDS='30',SEDGE_MAX_ROUNDS='1000',SEDGE_STATS=str(stat),CLOUD_INITIAL_SOLUTION=str(incumbent),CLOUD_WINDOW_BOUNDARIES=str(boundaries))
            proc=subprocess.run([str(exe),*map(str,inputs),str(solution)],env=env,text=True,capture_output=True,timeout=35)
            (folder/(label+'.log')).write_text(proc.stderr)
            if proc.returncode:raise RuntimeError(proc.stderr)
            check=subprocess.run([str(args.checker),'--net',str(inputs[0]),'--tm',str(inputs[1]),'--scenario',str(inputs[2]),'--srpaths',str(solution),'--max-decimal-places','6'],text=True,capture_output=True,timeout=30)
            (folder/(label+'-checker.json')).write_text(check.stdout)
            if check.returncode:raise RuntimeError(check.stdout+check.stderr)
            results[label]=score(json.loads(check.stdout));stats[label]=json.loads(stat.read_text())
        assert (folder/'parent.json').read_bytes()==(folder/'disabled.json').read_bytes(),(name,'ablation changed parent')
        if improve:
            assert results['candidate']<results['parent'],name
            assert stats['candidate']['window_accepted']>=1 and stats['candidate']['window_last_left']==left and stats['candidate']['window_last_right']==right,name
            assert results['nearest-only']<=results['parent'],name
        else:
            assert results['candidate']==results['parent'],name
            assert stats['candidate']['window_accepted']==0,name
        rank=next((i for i,(a,b) in enumerate(zip(results['parent'],results['candidate'])) if a!=b),None)
        rows.append({'case':name,'valid':True,'strict_improvement':results['candidate']<results['parent'],
                     'rank':rank,'parent_at_rank':None if rank is None else results['parent'][rank],
                     'candidate_at_rank':None if rank is None else results['candidate'][rank],
                     'window_accepted':stats['candidate']['window_accepted'],'ablation_byte_identical':True})
    report={'cases':rows,'candidate_sha256':hashlib.sha256(args.candidate.read_bytes()).hexdigest(),
            'checker_sha256':hashlib.sha256(args.checker.read_bytes()).hexdigest()}
    (args.output/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(rows))
    return 0


if __name__=='__main__':raise SystemExit(main())
