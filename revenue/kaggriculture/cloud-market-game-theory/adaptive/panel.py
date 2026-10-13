# SPDX-License-Identifier: Apache-2.0
"""Disjoint adaptive-policy full games, retaining reached decisions and losses."""
import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
import sys
import time

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from dependencies import official_engine


def run(job):
    engine_dir, opponents, seed, arm, rival, seat=job
    ev,engine,hashes=official_engine(engine_dir)
    pending={};events=[]
    class Actor(ev.Actor):
        def act(self,obs,cfg,timeout):
            reply=super().act(obs,cfg,timeout)
            if reply.get('kind')=='action':
                self.stats.setdefault('first_call_seconds',reply['call_seconds'])
                meta=reply['action'].pop('__adaptive_evaluation__',None)
                if meta:
                    self.stats['adaptive_counts']=meta['counts']
                    if meta.get('decision'):
                        pending[int(obs['step'])]={'step':int(obs['step']), 'observation':deepcopy(obs),'metadata':meta}
            return reply
    ev.Actor=Actor
    candidate=str(HERE/'evaluation_entry.py')+'::'+arm
    specs=[candidate,opponents[rival]] if seat==0 else [opponents[rival],candidate]
    original=engine.interpreter
    def observed(state,env):
        step=state[0].observation.get('step');row=pending.pop(step,None)
        if row:
            row['actions']=deepcopy([s.action for s in state])
            row['cash_before']=[f['money'] for f in state[0].observation.farms]
        result=original(state,env)
        if row:
            row['cash_after']=[f['money'] for f in state[0].observation.farms]
            events.append(row)
        return result
    engine.interpreter=observed
    result=ev.play(engine,specs,engine_dir,ev.LOADER,seed,seat,action_timeout=1.0,game_timeout=120.0)
    result.update(arm=arm,opponent=rival,events=events,engine_sha256=hashes)
    return json.loads(json.dumps(result,allow_nan=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--engine-dir',required=True)
    p.add_argument('--opponents',type=Path,required=True);p.add_argument('--seeds',required=True)
    p.add_argument('--arms',default='baseline,adaptive');p.add_argument('--seats',default='0,1')
    p.add_argument('--output',type=Path,required=True);p.add_argument('--workers',type=int,default=2)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    files={str(p.relative_to(HERE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in HERE.glob('*.py')}
    manifest={'source_files':files,'seeds':list(map(int,a.seeds.split(','))),'arms':a.arms.split(','),
              'opponents':json.loads(a.opponents.read_text()),'seats':list(map(int,a.seats.split(','))),
              'limits':{'action_rpc_seconds':1,'episode_seconds':120,'overage_seconds':0}}
    (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    jobs=[(a.engine_dir,manifest['opponents'],s,arm,r,seat) for s in manifest['seeds']
          for arm in manifest['arms'] for r in manifest['opponents'] for seat in manifest['seats']]
    start=time.monotonic()
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        for f in as_completed([pool.submit(run,j) for j in jobs]):
            row=f.result();name=f"{row['arm']}-{row['seed']}-{row['opponent']}-{row['candidate_seat']}.json.gz"
            (a.output/name).write_bytes(gzip.compress(json.dumps(row,indent=2).encode(),mtime=0))
            print(json.dumps({k:row[k] for k in ('arm','seed','opponent','candidate_seat','status','scores','failure')}
                             | {'counts':row['actors'][row['candidate_seat']].get('adaptive_counts')}),flush=True)
    assert all(hashlib.sha256((HERE/p).read_bytes()).hexdigest()==h for p,h in files.items())
    print(json.dumps({'games':len(jobs),'seconds':time.monotonic()-start}))
