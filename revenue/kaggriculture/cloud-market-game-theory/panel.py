# SPDX-License-Identifier: Apache-2.0
"""Fresh full-game panels through the unchanged process-isolated evaluator."""
import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
import copy
import gzip
import hashlib
import json
from pathlib import Path
import time

from dependencies import HERE, load, official_engine


def run_one(job):
    cache,runtime,arm,seed,rival,seat=job
    ev,engine,hashes=official_engine(cache)
    pending={};events=[]
    class MeasuredActor(ev.Actor):
        def act(self,obs,cfg,timeout):
            reply=super().act(obs,cfg,timeout)
            if reply.get('kind')=='action':
                if 'first_call_seconds' not in self.stats:
                    self.stats['first_call_seconds']=reply['call_seconds']
                meta=reply['action'].pop('__t15_evaluation__',None)
                if meta is not None:
                    self.stats['t15_counts']=meta['counts']
                    if meta.get('activation'):
                        pending[int(obs['step'])]={'step':int(obs['step']),
                            'observation':copy.deepcopy(obs),'metadata':meta}
            return reply
    league=load(HERE.parent/'cloud-market-response/vendor/league_variants.py','t15_league')
    ev.Actor=league.actor_class(MeasuredActor,engine.SHOPS)
    frozen=HERE.parent/'cloud-titan-composition/arms/sell.py'
    candidate=str(frozen) if arm=='baseline' else str(HERE/'evaluation_entry.py')+'::'+arm
    if rival=='sell':other=str(frozen)
    elif rival=='cadence':other=str(Path(runtime)/'arlene-adapter.py')+'|league=sale_cadence'
    else:other=str(Path(runtime)/(rival+'-adapter.py'))
    specs=[candidate,other] if seat==0 else [other,candidate]
    original=engine.interpreter
    def observed(state,env):
        step=state[0].observation.get('step')
        if step in pending:
            row=pending.pop(step)
            row['actions']=copy.deepcopy([s.action for s in state])
            before=[f['money'] for f in state[0].observation.farms]
        else:row=None
        answer=original(state,env)
        if row is not None:
            row['cash_before']=before;row['cash_after']=[f['money'] for f in state[0].observation.farms]
            events.append(row)
        return answer
    engine.interpreter=observed
    result=ev.play(engine,specs,cache,ev.LOADER,seed,seat,action_timeout=1.0,game_timeout=120.0)
    result.update(arm=arm,opponent=rival,activation_events=events,engine_sha256=hashes,
                  evaluator_sha256=hashlib.sha256(Path(ev.__file__).read_bytes()).hexdigest())
    return json.loads(json.dumps(result,allow_nan=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--engine-dir',required=True);p.add_argument('--runtime',required=True)
    p.add_argument('--seeds',required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--workers',type=int,default=3);p.add_argument('--opponents',default='arlene,apex,sell,cadence')
    p.add_argument('--arms',default='baseline,pure,mixed');p.add_argument('--freeze',type=Path,required=True)
    a=p.parse_args()
    frozen=json.loads(a.freeze.read_text())
    def verify():
        for path,digest in frozen['files'].items():
            assert hashlib.sha256((HERE/path).read_bytes()).hexdigest()==digest,path
    verify()
    a.output.mkdir(parents=True,exist_ok=False)
    seeds=list(map(int,a.seeds.split(',')))
    jobs=[(a.engine_dir,a.runtime,arm,seed,rival,seat) for arm in a.arms.split(',')
          for seed in seeds for rival in a.opponents.split(',') for seat in (0,1)]
    (a.output/'manifest.json').write_text(json.dumps({'seeds':seeds,'jobs':len(jobs),
        'freeze_sha256':hashlib.sha256(a.freeze.read_bytes()).hexdigest(),
        'limits':{'action_rpc_seconds':1,'episode_wall_seconds':120,'overage_seconds':0},
        'method':'Unchanged evaluator; diagnostic envelope removed before engine; complete retained legal actions at activations.'},indent=2)+'\n')
    started=time.monotonic()
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        for future in as_completed([pool.submit(run_one,job) for job in jobs]):
            row=future.result();name=f"{row['arm']}-{row['seed']}-{row['opponent']}-{row['candidate_seat']}.json.gz"
            (a.output/name).write_bytes(gzip.compress((json.dumps(row,indent=2)+'\n').encode(),mtime=0))
            print(json.dumps({k:row[k] for k in ('arm','seed','opponent','candidate_seat','status','scores','failure')}
                  |{'counts':row['actors'][row['candidate_seat']].get('t15_counts')}),flush=True)
    verify();print(json.dumps({'games':len(jobs),'seconds':time.monotonic()-started}),flush=True)
