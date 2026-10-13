# SPDX-License-Identifier: Apache-2.0
"""Additive panel over the unchanged process-isolated Commons evaluator."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import copy
import hashlib
import json
from pathlib import Path
import time

from official_cases import HERE, ROOT, load_engine


def plain_record(value):
    """Remove evaluator Struct subclasses before process-pool serialization."""
    return json.loads(json.dumps(value, allow_nan=False))


def run_one(job):
    engine_dir, runtime, arm, seed, opponent, seat = job
    ev, engine, hashes = load_engine(engine_dir)
    class TimedActor(ev.Actor):
        def _measure(self, message):
            if message.get('kind') == 'action' and 'first_call_seconds' not in self.stats:
                self.stats['first_call_seconds'] = message['call_seconds']
            super()._measure(message)
    ev.Actor = TimedActor
    frozen = ROOT / 'revenue/kaggriculture/cloud-titan-composition/arms/sell.py'
    candidate = HERE/'main.py' if arm == 'cycle' else frozen
    other = frozen if opponent == 'sell' else Path(runtime)/(opponent+'-adapter.py')
    specs = [str(candidate),str(other)] if seat == 0 else [str(other),str(candidate)]
    original = engine.interpreter
    events = []
    def observe(state,env):
        action = state[seat].action
        queue = action.get('market',[]) if isinstance(action,dict) else []
        matches = (len(queue)==2 and queue[0][0:1]==['SELL'] and
                   queue[1][0:1]==['BUY_PRODUCT'] and queue[0][1:]==queue[1][1:] and
                   queue[0][2]==1)
        record=None
        if state[0].observation.get('farms') and matches:
            obs=state[seat].observation
            record={'step':obs.get('step'),'action':copy.deepcopy(action),
                    'rival_action':copy.deepcopy(state[1-seat].action),
                    'own_observation':copy.deepcopy(obs),
                    'before_cash':[f['money'] for f in obs.farms]}
        result=original(state,env)
        if record is not None:
            record['after_cash']=[f['money'] for f in state[0].observation.farms]
            events.append(record)
        return result
    engine.interpreter=observe
    game=ev.play(engine,specs,engine_dir,ev.LOADER,seed,seat,
                 action_timeout=1.0,game_timeout=120.0)
    game.update(arm=arm,opponent=opponent,cycle_signature_events=events,
                engine_sha256=hashes,evaluator_sha256=ev.sha256(ev.__file__))
    return plain_record(game)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--engine-dir',type=Path,required=True)
    p.add_argument('--runtime',type=Path,required=True)
    p.add_argument('--seeds',required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--workers',type=int,default=3)
    p.add_argument('--arms',default='control,cycle')
    a=p.parse_args()
    if a.output.exists():
        raise FileExistsError(a.output)
    a.output.mkdir(parents=True)
    seeds=[int(s) for s in a.seeds.split(',')]
    jobs=[(str(a.engine_dir.resolve()),str(a.runtime.resolve()),arm,seed,opponent,seat)
          for arm in a.arms.split(',') for seed in seeds
          for opponent in ('arlene','apex','sell') for seat in (0,1)]
    files={str(f.relative_to(HERE)):hashlib.sha256(f.read_bytes()).hexdigest()
           for f in HERE.glob('*.py')}
    (a.output/'manifest.json').write_text(json.dumps({'seeds':seeds,'jobs':len(jobs),
      'files':files,'workers':a.workers,'limits':{'action_rpc_seconds':1.0,'episode_wall_seconds':120.0,
      'remainingOverageTime':0},'method':'Unchanged official interpreter and cloud-eval.play; passive cycle-signature events only.'},indent=2)+'\n')
    started=time.monotonic()
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        futures=[pool.submit(run_one,job) for job in jobs]
        for future in as_completed(futures):
            game=future.result()
            name=f"{game['arm']}-{game['seed']}-{game['opponent']}-{game['candidate_seat']}.json"
            (a.output/name).write_text(json.dumps(game,indent=2)+'\n')
            print(json.dumps({k:game[k] for k in ('arm','seed','opponent','candidate_seat','status','scores','failure')}),flush=True)
    print(json.dumps({'games':len(jobs),'seconds':time.monotonic()-started}),flush=True)


if __name__=='__main__':
    main()
