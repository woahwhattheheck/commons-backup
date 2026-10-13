#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compile both exact solvers and compare topology reuse without timed-search drift.

No network, public benchmark, or organizer action. --reference is the preserved
pre-optimization main.cpp; --candidate defaults to the containing fleet source.
The only probe edits expose Solver members and rename its CLI main in a separate
translation unit; every production method executes unchanged.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import statistics
import subprocess
import time


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build(source, vendor, out, probe):
    out.mkdir(parents=True, exist_ok=True)
    cpp = Path(source).read_text(encoding='utf-8')
    if cpp.count('class Solver {') != 1 or cpp.count('int main(int argc, char** argv)') != 1:
        raise ValueError('Unexpected solver layout')
    visible = cpp.replace('class Solver {', 'class Solver {\npublic:', 1)
    visible = visible.replace('int main(int argc, char** argv)', 'int solver_cli(int argc, char** argv)', 1)
    (out/'probe-source.cpp').write_text(visible + '\n' + probe, encoding='utf-8')
    for name, path in [('solver', Path(source)), ('probe', out/'probe-source.cpp')]:
        result = subprocess.run(['g++','-std=c++20','-O3','-DNDEBUG','-I',str(vendor),
                                 str(path),'-o',str(out/name)], capture_output=True, text=True)
        (out/(name+'-build.log')).write_text(result.stdout+result.stderr)
        result.check_returncode()


def fixture(root, seed, n=12, h=12, groups=3, disconnected=False):
    rng = random.Random(seed)
    ids = [101+13*i for i in range(n)]
    pairs = [(u,v) for u in range(n) for v in range(n) if u != v]
    if disconnected:
        pairs = [(u,v) for u,v in pairs if (u<n//2)==(v<n//2)]
    links = [dict(id=17+3*i, **{'from':ids[u]}, to=ids[v],
                  metric=rng.choice([1,1,2,3]), capacity=rng.choice([50,100,150]))
             for i,(u,v) in enumerate(pairs)]
    # Remove distinct non-ring edges. Repeated masks are deliberately nonadjacent.
    removable = [i for i,(u,v) in enumerate(pairs) if v!=(u+1)%n and u!=(v+1)%n]
    choices = [set()]
    for k in range(1, groups):
        choices.append({removable[(67+k)%len(removable)]})
    masks = [choices[(t*7)%groups] for t in range(h)]
    if groups == h:
        masks = choices
    demands=[]
    bound=n//2 if disconnected else n
    for d in range(min(12,bound*(bound-1))):
        u=d%bound; v=(u+1+d//bound) % bound
        if u==v: v=(v+1)%bound
        demands.append({'s':ids[u],'t':ids[v],'v':[rng.randint(20,140) for _ in range(h)]})
    values=[{'nodes':[{'id':x} for x in ids], 'links':links},
            {'num_time_slots':h,'demands':demands},
            {'max_segments':8,'budget':[{'t':t,'value':rng.choice([0,4,12,30])} for t in range(1,h)],
             'interventions':[{'t':t,'links':[links[i]['id'] for i in sorted(mask)]} for t,mask in enumerate(masks)]}]
    root.mkdir(parents=True,exist_ok=True)
    paths=[]
    for kind,value in zip(('net','tm','scenario'),values):
        path=root/(kind+'.json'); path.write_text(json.dumps(value,sort_keys=True)+'\n'); paths.append(path)
    return paths, len(set(tuple(sorted(m)) for m in masks)), sum(masks[t]==masks[u] for t in range(h) for u in range(t))


def invoke(binary, paths, output, rounds, mode=None):
    env=dict(os.environ,SEDGE_MAX_ROUNDS=str(rounds),SEDGE_SECONDS='3600',SEDGE_STATS=str(output)+'.stats.json')
    for key in ('CLOUD_INITIAL_SOLUTION','FLEET_WAYPOINT_LIMIT','FLEET_JOINT','FLEET_DIRECTED'):
        env.pop(key,None)
    command=[str(binary),*map(str,paths),str(output)]
    if mode: command.append(mode)
    started=time.perf_counter()
    result=subprocess.run(command,env=env,text=True,capture_output=True,timeout=90)
    elapsed=time.perf_counter()-started
    output.with_suffix(output.suffix+'.stdout').write_text(result.stdout)
    output.with_suffix(output.suffix+'.stderr').write_text(result.stderr)
    result.check_returncode()
    return result.stdout,elapsed


def stats(path):
    result=json.loads(Path(str(path)+'.stats.json').read_text())
    result.pop('seconds')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference',type=Path,required=True)
    parser.add_argument('--candidate',type=Path,default=Path(__file__).resolve().parents[1]/'main.cpp')
    parser.add_argument('--vendor',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--skip-performance',action='store_true')
    args=parser.parse_args(); out=args.output.resolve(); out.mkdir(parents=True,exist_ok=True)
    vendor=args.vendor.resolve()
    probe=Path(__file__).with_name('probe.cpp').read_text()
    for tag,source in [('reference',args.reference.resolve()),('candidate',args.candidate.resolve())]:
        build(source,vendor,out/tag,probe)
    checks=[]
    specs=[(1,12,12,1,False),(2,12,12,3,False),(3,12,12,12,False),
           (4,12,12,3,True),(5,5,1,1,False)] + [(k,8,9,3,False) for k in range(6,12)]
    for seed,n,h,groups,disconnected in specs:
        paths,unique,aliases=fixture(out/f'case-{seed}',seed,n,h,groups,disconnected)
        runs=[]
        for tag in ('reference','candidate'):
            text,_=invoke(out/tag/'probe',paths,out/f'case-{seed}'/(tag+'-probe.json'),0,'dump')
            body,summary=text.rsplit('summary ',1)
            fields=list(map(int,summary.split()))
            runs.append((body,fields))
        assert runs[0][0]==runs[1][0], f'Flow mismatch at seed {seed}'
        assert runs[0][1][:2]==runs[1][1][:2]
        assert runs[1][1][2:]==[unique*n,unique*n*n,aliases,0], runs[1][1]
        assert runs[0][1][2:]==[h*n,h*n*n,0,0], runs[0][1]
        # Search ordering and all numeric state must agree when the clock cannot
        # select a different neighborhood. Include zero-round and iterative runs.
        for rounds in (0,8):
            targets=[]
            for tag in ('reference','candidate'):
                target=out/f'case-{seed}'/(tag+f'-r{rounds}.json')
                invoke(out/tag/'solver',paths,target,rounds); targets.append(target)
            assert targets[0].read_bytes()==targets[1].read_bytes(), (seed,rounds,'routes')
            assert stats(targets[0])==stats(targets[1]), (seed,rounds,'state')
        checks.append({'seed':seed,'nodes':n,'slots':h,'topologies':unique,
                       'exact_segment_queries':h*n*n,'flow_bytes_sha256':hashlib.sha256(runs[1][0].encode()).hexdigest(),
                       'reference_cache':runs[0][1][2:],'candidate_cache':runs[1][1][2:],
                       'fixed_rounds':[0,8],'full_state_equal':True})
    performance=[]
    if not args.skip_performance:
        for label,groups in [('repeated',3),('unique',24)]:
            paths,unique,aliases=fixture(out/('perf-'+label),812,60,24,groups,False)
            samples={'reference':[],'candidate':[]}; last={}
            for iteration in range(5):
                order=('reference','candidate') if iteration%2==0 else ('candidate','reference')
                for tag in order:
                    target=out/('perf-'+label)/(tag+f'-{iteration}.json')
                    text,elapsed=invoke(out/tag/'probe',paths,target,0,'digest')
                    fields=list(map(int,text.split('summary ')[1].split()))
                    samples[tag].append(elapsed); last[tag]=fields
                assert last['reference'][:2]==last['candidate'][:2]
            performance.append({'label':label,'nodes':60,'slots':24,'topologies':unique,
                                'samples_seconds':samples,'median_seconds':{k:statistics.median(v) for k,v in samples.items()},
                                'probe_summary':last})
    report={'schema':'kestrel.topology-cache-check.v1','reference_sha256':digest(args.reference),
            'candidate_sha256':digest(args.candidate),'compiler':subprocess.check_output(['g++','--version'],text=True).splitlines()[0],
            'checks':checks,'performance':performance,
            'scope':'Generated native workloads, not official benchmark or competitive score evidence'}
    (out/'RESULTS.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps(report,indent=2,sort_keys=True))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
