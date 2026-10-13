#!/usr/bin/env python3
"""Predeclared four-case temporal-on/off public continuation; no network I/O."""
from __future__ import annotations
import argparse
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def save(p, data):
    p.write_text(json.dumps(data, indent=2, allow_nan=False) + '\n')


def call(command, directory, label, env=None, timeout=40):
    start=time.perf_counter()
    p=subprocess.Popen(command, cwd=directory, env=env, stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, start_new_session=True)
    expired=False
    try:
        stdout,stderr=p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        expired=True
        try: os.killpg(p.pid,signal.SIGTERM)
        except ProcessLookupError: pass
        try: stdout,stderr=p.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            try: os.killpg(p.pid,signal.SIGKILL)
            except ProcessLookupError: pass
            stdout,stderr=p.communicate()
    (directory/(label+'.stdout')).write_bytes(stdout)
    (directory/(label+'.stderr')).write_bytes(stderr)
    result={'command':command,'returncode':p.returncode,'seconds':time.perf_counter()-start,'timed_out':expired}
    save(directory/(label+'.process.json'),result)
    return result,stdout


def vector(data):
    obj=json.loads(data,parse_float=Decimal)
    if obj.get('valid') is not True: raise ValueError('Official checker rejected output')
    result=tuple(sorted((Decimal(str(r['sat'])) for r in obj['saturations']),reverse=True))
    if not result or not all(v.is_finite() and v>=0 for v in result):
        raise ValueError('Invalid saturation coordinates')
    return result,obj


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('screen','control','candidate','checker','output'):
        p.add_argument('--'+name,required=True,type=Path)
    args=p.parse_args()
    screen=args.screen.resolve(strict=True)
    binaries={name:getattr(args,name).resolve(strict=True) for name in ('control','candidate','checker')}
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    manifest=json.loads((screen/'MANIFEST.json').read_text())
    entries=manifest['files']
    if isinstance(entries,dict): entries=[dict(path=k,**v) if isinstance(v,dict) else dict(path=k,sha256=v) for k,v in entries.items()]
    for item in entries:
        assert sha(screen/item['path'])==item['sha256'],item['path']
    cases=['setB-01','setB-04','setB-07','setB-10']
    clean={k:v for k,v in os.environ.items() if not k.startswith(('DOCK_','SEDGE_','FLEET_','CLOUD_INITIAL_'))}
    experiment={'cases':cases,'seconds_per_arm':10,'workers':1,'round_limit':None,
                'candidate_source_commit':'03d4ecd032accfdb3bc1cc8978b368a22f2096ed',
                'parent_source_commit':'2885d176373c33410148829fef93c310c3752c0b',
                'source_screen_sha256':'0fed26e0260aad3c3c840c3e2c38b035f21ce6d3cac5544428f4f8a5f2959d9d',
                'manifest_verified_files':len(entries),'binaries':{k:sha(v) for k,v in binaries.items()},
                'method':'new matched-time native continuations from same saved SEDGE incumbent; no supplied route menu',
                'scope':'public development comparison, no new official contest/hidden-instance score'}
    save(out/'EXPERIMENT.json',experiment)
    rows=[]
    for index,case in enumerate(cases):
        root=out/case;root.mkdir()
        inputs={name:screen/'inputs/setB'/(case+'-'+name+'.json') for name in ('net','tm','scenario')}
        incumbent=screen/'screen30'/case/'sedge/solution.json'
        identities={k:sha(v) for k,v in inputs.items()};identities['incumbent']=sha(incumbent)
        save(root/'INPUTS.json',identities)
        checks={};reports={}
        order=('control','candidate') if index%2==0 else ('candidate','control')
        for arm in order:
            d=root/arm;d.mkdir()
            env=dict(clean,SEDGE_SECONDS='10',SEDGE_STATS=str(d/'stats.json'),CLOUD_INITIAL_SOLUTION=str(incumbent))
            if arm=='candidate': env['DOCK_TEMPORAL']='1'
            command=['/usr/bin/time','-o',str(d/'usage.json'),'-f','{"max_rss_kib":%M,"user_seconds":%U,"system_seconds":%S,"elapsed_seconds":%e,"exit":%x}',str(binaries[arm]),*[str(inputs[n]) for n in ('net','tm','scenario')],str(d/'solution.json')]
            result,_=call(command,d,'solver',env,timeout=40)
            reports[arm]={'process':result,'usage':json.loads((d/'usage.json').read_text()) if (d/'usage.json').exists() else None}
            if result['returncode']!=0 or result['timed_out']:
                raise RuntimeError(f'{case}/{arm} did not complete; retained all streams/checkpoint')
            for precision in (6,12):
                cmd=[str(binaries['checker']),'--net',str(inputs['net']),'--tm',str(inputs['tm']),'--scenario',str(inputs['scenario']),'--srpaths',str(d/'solution.json'),'--max-decimal-places',str(precision)]
                checked,stdout=call(cmd,d,'checker-'+str(precision),timeout=40)
                if checked['returncode']!=0: raise RuntimeError(f'{case}/{arm} checker failed')
                val,obj=vector(stdout)
                if precision==6: checks[arm]=val
                stats=json.loads((d/'stats.json').read_text())
                if precision==12:
                    internal={(x['t'],x['from'],x['to']):x['sat'] for x in stats['loads']}
                    error=max(abs(float(x['sat'])-internal[x['t'],x['from'],x['to']]) for x in obj['saturations'])
                    assert error<2e-9,(case,arm,error)
                    assert int(obj['total_cost'])==sum(stats['budget_used'])
                    reports[arm].update(load_error=error,total_cost=int(obj['total_cost']),accepted=stats['accepted'],attempted=stats['attempted'],maximum=float(val[0]),solution_sha256=sha(d/'solution.json'))
        a,b=checks['control'],checks['candidate']
        rank=next((i+1 for i,(x,y) in enumerate(zip(a,b)) if x!=y),None)
        assert len(a)==len(b)
        row={'case':case,'outcome':'W' if b<a else 'L' if a<b else 'T','first_difference_rank':rank,
             'control_at_difference':str(a[rank-1]) if rank else None,'candidate_at_difference':str(b[rank-1]) if rank else None,
             'coordinates':len(a),'run_order':order,'arms':reports}
        rows.append(row)
        save(out/'SUMMARY.json',{'experiment':experiment,'completed_cases':len(rows),'results':rows})
        print(json.dumps({k:v for k,v in row.items() if k!='arms'}),flush=True)
        assert all(sha(v)==identities[k] for k,v in inputs.items()) and sha(incumbent)==identities['incumbent']
    print(json.dumps({'W':sum(r['outcome']=='W' for r in rows),'T':sum(r['outcome']=='T' for r in rows),'L':sum(r['outcome']=='L' for r in rows)}),flush=True)

if __name__=='__main__':main()
