# SPDX-License-Identifier: Apache-2.0
"""Execute packaged history ON/OFF with existing official engine and RPC boundary."""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor,as_completed
from copy import deepcopy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
HERE=Path(__file__).resolve().parent


def load(path,name):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m


def run(job):
    seed,arm,rival,seat,resolution,output=job
    ev=load(resolution['evaluator'],'history_consumer_evaluator')
    engine,hashes=ev.get_engine(resolution['engine'])
    rows=[];counts=Counter();terminal=None
    class Actor(ev.Actor):
        def act(self,obs,cfg,timeout):
            nonlocal terminal
            candidate=self.spec.startswith(str(HERE/'entry.py'))
            record={'step':int(obs['step']),'seat':int(obs['player']),'observation':deepcopy(obs)}
            reply=super().act(obs,cfg,timeout)
            if reply.get('kind')=='action':
                meta=reply['action'].pop('__consumer_evidence__',None)
                if meta:
                    d=meta['diagnostics'];counts[d.get('status','unknown')]+=1
                    counts['parent_calls']+=d.get('parent_calls',0)
                    counts['history_observations']+=bool(d.get('history',{}).get('observed_fills'))
                    if 'family' in d.get('history',{}):terminal=deepcopy(meta)
                    if int(obs['step'])==718:terminal=deepcopy(meta)
                record['metadata']=meta
            record['response']=deepcopy(reply)
            # Exact candidate inputs, both returned actions, and all failed inputs.
            if not candidate and reply.get('kind')=='action':record.pop('observation')
            rows.append(record)
            return reply
    ev.Actor=Actor
    entry=str(HERE/'entry.py')+'::'+arm
    opponent=resolution['opponents'][rival]
    specs=[entry,opponent] if seat==0 else [opponent,entry]
    result=ev.play(engine,specs,resolution['engine'],ev.LOADER,seed,seat,
                   action_timeout=1.0,game_timeout=120.0)
    result.update(arm=arm,opponent=rival,counts=dict(counts),terminal=terminal,engine_sha256=hashes)
    name=f'{arm}-{seed}-{rival}-{seat}'
    tape=gzip.compress(json.dumps(rows,separators=(',',':')).encode(),mtime=0)
    Path(output,name+'.trace.json.gz').write_bytes(tape)
    result['trace_file']=name+'.trace.json.gz';result['trace_file_sha256']=hashlib.sha256(tape).hexdigest()
    Path(output,name+'.json').write_text(json.dumps(result,indent=2)+'\n')
    return {k:result[k] for k in ('seed','arm','opponent','candidate_seat','status','scores','failure','counts')}|{'family':(terminal or {}).get('diagnostics',{}).get('history',{}).get('family',{}).get('status')}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--seeds',required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--jobs',type=int,default=2)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    resolution=json.loads((HERE/'runtime-resolution.json').read_text())
    frozen=json.loads((HERE/'SOURCE-FREEZE.json').read_text())
    for path,digest in frozen['runtime_files'].items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest,path
    for path,digest in frozen['consumer_files'].items():assert hashlib.sha256((HERE/path).read_bytes()).hexdigest()==digest,path
    seeds=list(map(int,a.seeds.split(',')))
    (a.output/'manifest.json').write_text(json.dumps({'seeds':seeds,'jobs':a.jobs,'freeze_sha256':hashlib.sha256((HERE/'SOURCE-FREEZE.json').read_bytes()).hexdigest(),'arms':['history_off','history_on'],'opponents':resolution['opponents'],'seats':[0,1],'limits':{'action_rpc':1,'episode_wall':120,'overage':0}},indent=2)+'\n')
    jobs=[(s,arm,r,seat,resolution,str(a.output)) for s in seeds for arm in ['history_off','history_on'] for r in resolution['opponents'] for seat in [0,1]]
    started=time.monotonic()
    with ProcessPoolExecutor(max_workers=a.jobs) as pool:
        for f in as_completed([pool.submit(run,j) for j in jobs]):print(json.dumps(f.result()),flush=True)
    for path,digest in frozen['runtime_files'].items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest,path
    print(json.dumps({'attempts':len(jobs),'wall_seconds':time.monotonic()-started}),flush=True)
