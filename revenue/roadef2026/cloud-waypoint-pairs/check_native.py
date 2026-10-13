#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Constructed official-checker discriminators for atomic two-waypoint routes.

No public benchmark or hidden instance is used. The baseline is the exact fleet
binary and the candidate differs only by the additive paired-route neighborhood.
Retains full solutions, checker outputs, logs, input and binary identities.
"""
from __future__ import annotations
import argparse
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import time


def digest(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()

def write(p: Path, obj) -> None:
    p.write_text(json.dumps(obj, indent=2, sort_keys=True) + '\n', encoding='utf-8')

def fixture(root: Path, name: str, *, volume=1, capacity=10, segments=3,
            maintenance=False, budget=4, relabel=False):
    root = root / name
    root.mkdir(parents=True, exist_ok=True)
    ids = [107, 29, 503, 71] if relabel else [0, 1, 2, 3]
    # s->t is shortest but congested. Neither s->a->t nor s->b->t
    # avoids it; the complete s->a->b->t segment route does.
    arcs = [(0,3,1,1), (0,1,3,capacity), (1,2,2,capacity),
            (2,3,3,capacity), (1,0,1,capacity), (3,2,1,capacity),
            (3,0,100,capacity), (2,1,100,capacity)]
    network = {'directed': True, 'multigraph': False,
               'nodes': [{'id': x, 'name': f'n{x}'} for x in ids],
               'links': [{'id': i, 'from': ids[u], 'to': ids[v], 'metric': cost, 'capacity': cap}
                         for i, (u,v,cost,cap) in enumerate(arcs)]}
    volumes = [volume, volume*100, volume] if maintenance else [volume]
    traffic = {'num_time_slots': len(volumes), 'demands': [{'s': ids[0], 't': ids[3], 'v': volumes}]}
    scenario = {'max_segments': segments,
                'budget': [{'t': t, 'value': budget} for t in range(1,len(volumes))],
                'interventions': [{'t': 1, 'links': [2]}] if maintenance else []}
    paths = []
    for part, obj in [('net',network),('tm',traffic),('scenario',scenario)]:
        path = root/(part+'.json'); write(path,obj); paths.append(path)
    return root, paths, ids


def vector(report):
    return tuple(sorted((int(Decimal(str(x['sat'])) * 1_000_000)
                         for x in report['saturations']), reverse=True))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline', type=Path, required=True)
    p.add_argument('--candidate', type=Path, required=True)
    p.add_argument('--checker', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=True)
    base, candidate, checker = [x.resolve(strict=True) for x in (a.baseline,a.candidate,a.checker)]
    summary = {'scope': 'constructed source/algorithm discriminators; no benchmark or ranking claim',
               'binaries': {k:digest(v) for k,v in [('baseline',base),('candidate',candidate),('checker',checker)]},
               'cases': [], 'official_checker_calls': 0}

    def check(paths, output, label):
        started = time.perf_counter()
        r = subprocess.run([str(checker),'--net',str(paths[0]),'--tm',str(paths[1]),
                            '--scenario',str(paths[2]),'--srpaths',str(output)],
                           capture_output=True, timeout=30)
        (output.parent/(label+'.checker.json')).write_bytes(r.stdout)
        (output.parent/(label+'.checker.stderr')).write_bytes(r.stderr)
        summary['official_checker_calls'] += 1
        if r.returncode:
            raise AssertionError((label,r.returncode,r.stderr.decode(errors='replace')))
        obj = json.loads(r.stdout)
        if obj.get('valid') is not True:
            raise AssertionError((label,obj))
        return obj, time.perf_counter()-started

    def run(binary, paths, folder, label, *, enabled=True, rounds=100, resume=None, trials=None):
        out = folder/(label+'.solution.json')
        stats = folder/(label+'.stats.json')
        env = {k:v for k,v in os.environ.items() if not k.startswith(('SEDGE_','FLEET_','CEDAR_','CLOUD_INITIAL_'))}
        env.update(SEDGE_SECONDS='10', SEDGE_MAX_ROUNDS=str(rounds), SEDGE_STATS=str(stats),
                   CEDAR_PAIRS='1' if enabled else '0')
        if resume is not None: env['CLOUD_INITIAL_SOLUTION'] = str(resume)
        if trials is not None: env['CEDAR_PAIR_TRIALS'] = str(trials)
        start=time.perf_counter()
        proc = subprocess.run([str(binary),*map(str,paths),str(out)],env=env,capture_output=True,timeout=15)
        elapsed=time.perf_counter()-start
        (folder/(label+'.stdout')).write_bytes(proc.stdout)
        (folder/(label+'.stderr')).write_bytes(proc.stderr)
        if proc.returncode: raise AssertionError((label,proc.returncode,proc.stderr.decode(errors='replace')))
        report, check_elapsed = check(paths,out,label)
        stat=json.loads(stats.read_bytes())
        native={(x['t'],x['from'],x['to']):float(x['sat']) for x in stat['loads']}
        for row in report['saturations']:
            key=(row['t'],row['from'],row['to'])
            if abs(native[key]-float(row['sat'])) > 1.1e-6:
                raise AssertionError((label,key,native[key],row['sat']))
        return {'solution':str(out), 'solution_sha256':digest(out), 'vector':vector(report),
                'peak':max(float(x['sat']) for x in report['saturations']),
                'total_cost':report['total_cost'], 'accepted':stat['accepted'],
                'pair_accepted':stat.get('cedar_pair_accepted',0),
                'pair_checks':stat.get('cedar_pair_checks',0),
                'wall_seconds':elapsed,'checker_seconds':check_elapsed}

    # Full-pair gain, ordinary volume/capacity changes and noncontiguous labels.
    for i, (volume,capacity,relabel) in enumerate([(1,10,False),(3,11,False),(7,13,True)]):
        folder,paths,ids=fixture(a.output,f'barrier-{i}',volume=volume,capacity=capacity,relabel=relabel)
        b=run(base,paths,folder,'baseline'); off=run(candidate,paths,folder,'disabled',enabled=False)
        on=run(candidate,paths,folder,'paired'); repeated=run(candidate,paths,folder,'repeat')
        assert b['solution_sha256']==off['solution_sha256'] and b['vector']==off['vector']
        assert on['solution_sha256']==repeated['solution_sha256']
        assert on['vector'] < b['vector'] and on['pair_accepted'] >= 1
        assert math.isclose(on['peak'],volume/capacity,abs_tol=1.1e-6)
        # Every one-waypoint alternative is checker-valid but not improving.
        single=[]
        for node in ids[1:3]:
            out=folder/f'single-{node}.solution.json'
            write(out,{'srpaths':[{'d':0,'t':0,'w':[node]}]})
            report,_=check(paths,out,f'single-{node}')
            assert vector(report)>=b['vector']
            single.append({'waypoint':node,'vector':vector(report)})
        summary['cases'].append({'case':folder.name,'baseline':b,'disabled':off,'paired':on,'single_waypoints':single,
                                 'fixed_round_repeatability':True})

    # Segment limit is respected even though two waypoints would improve flow.
    for segments in (1,2):
        folder,paths,_=fixture(a.output,f'segment-limit-{segments}',segments=segments)
        b=run(base,paths,folder,'baseline'); on=run(candidate,paths,folder,'paired')
        assert on['vector']==b['vector'] and on['pair_checks']==0
        summary['cases'].append({'case':folder.name,'baseline':b,'paired':on})

    # Exact route-set distance is four at each boundary. A congested maintenance
    # middle slot makes the constant all-horizon detour worse at a lower rank.
    for budget in (0,3,4):
        folder,paths,_=fixture(a.output,f'maintenance-budget-{budget}',maintenance=True,budget=budget)
        b=run(base,paths,folder,'baseline'); off=run(candidate,paths,folder,'disabled',enabled=False)
        on=run(candidate,paths,folder,'paired')
        assert b['solution_sha256']==off['solution_sha256']
        assert on['peak']==b['peak']==100
        if budget < 4:
            assert on['vector']==b['vector'] and on['pair_accepted']==0
        else:
            assert on['vector'] < b['vector'] and on['pair_accepted']>=1
            assert on['total_cost'] <= budget*2
        summary['cases'].append({'case':folder.name,'baseline':b,'disabled':off,'paired':on})

    # Resume consumes exact published route bytes rather than restarting cold.
    folder,paths,_=fixture(a.output,'resume')
    on=run(candidate,paths,folder,'first')
    resumed=run(candidate,paths,folder,'resumed',rounds=0,resume=Path(on['solution']))
    assert on['solution_sha256']==resumed['solution_sha256']
    summary['cases'].append({'case':'resume','paired':on,'resumed':resumed})
    summary['passed']=True
    summary['case_count']=len(summary['cases'])
    summary['input_sha256']={str(x.relative_to(a.output)):digest(x) for x in sorted(a.output.rglob('*.json'))
                            if x.name in ('net.json','tm.json','scenario.json')}
    write(a.output/'summary.json',summary)
    print(json.dumps({k:v for k,v in summary.items() if k not in ('cases','input_sha256')},sort_keys=True))

if __name__=='__main__':
    main()
