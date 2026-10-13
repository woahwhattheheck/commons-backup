# SPDX-License-Identifier: Apache-2.0
"""One isolated archived-native main.agent game; no hosted-runner claim."""
from __future__ import annotations
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time
from compose import NATIVE_BLOB, compose_source, git_blob


def load(path, name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module
    spec.loader.exec_module(module)
    return module


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--package',type=Path,required=True)
    p.add_argument('--arm',choices=('baseline','candidate'),required=True)
    p.add_argument('--seat',type=int,choices=(0,1),required=True)
    p.add_argument('--seed',type=int,default=9922999)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    root=args.package.resolve()
    data=(root/'frozen_selected.py').read_bytes()
    if git_blob(data)!=NATIVE_BLOB:
        raise SystemExit('Not checked native frozen source; no game started')
    inputs={str(f.relative_to(root)):hashlib.sha256(f.read_bytes()).hexdigest()
            for f in root.rglob('*') if f.is_file() and '__pycache__' not in f.parts}
    with tempfile.TemporaryDirectory(prefix='represented-native-') as tmp:
        package=Path(tmp)/'package'
        shutil.copytree(root,package,ignore=shutil.ignore_patterns('__pycache__'))
        if args.arm=='candidate':
            (package/'frozen_selected.py').write_text(compose_source(data.decode()))
        sys.path.insert(0,str(package))
        ev=load(package/'checks/reference/evaluator/evaluate.py','represented_game_eval')
        engine,hashes=ev.get_engine(package/'checks/reference/engine',
                                  package/'checks/reference/evaluator/loader.py')
        entry=load(package/'main.py','represented_native_entry')
        import frozen_selected
        counts={'market_calls':0,'event_calls':0,'non_null_events':0}
        real_market=frozen_selected.apply_represented_market
        real_event=frozen_selected.represented_shed_event
        def market(*a,**kw):
            counts['market_calls']+=1
            return real_market(*a,**kw)
        def event(*a,**kw):
            counts['event_calls']+=1
            result=real_event(*a,**kw)
            counts['non_null_events']+=result is not None
            return result
        frozen_selected.apply_represented_market=market
        frozen_selected.represented_shed_event=event
        S=ev.Struct
        cfg=S({k:v.get('default') if isinstance(v,dict) else v
               for k,v in engine.specification['configuration'].items()})
        cfg.seed=args.seed
        env=S(configuration=cfg,done=False,info={})
        state=[S(observation=S(),action={},status='ACTIVE',reward=0) for _ in range(2)]
        engine.interpreter(state,env)
        trace=hashlib.sha256();action_hash=hashlib.sha256()
        statuses={};walls=[];started=time.perf_counter()
        for step in range(int(cfg.episodeSteps)):
            for s in state:s.observation.step=step
            start=time.perf_counter()
            own=entry.agent(copy.deepcopy(state[args.seat].observation),cfg)
            walls.append(time.perf_counter()-start)
            diag=dict(entry._INSTANCE.diagnostics) if entry._INSTANCE else {}
            status=diag.get('status','missing');statuses[status]=statuses.get(status,0)+1
            state[args.seat].action=own
            state[1-args.seat].action=engine.starter_agent(copy.deepcopy(state[1-args.seat].observation))
            raw=json.dumps([s.action for s in state],sort_keys=True,separators=(',',':'),allow_nan=False).encode()
            action_hash.update(raw+b'\n')
            engine.interpreter(state,env)
            trace.update(raw+b'\n'+json.dumps([s.observation for s in state],sort_keys=True,
                         separators=(',',':'),allow_nan=False).encode()+b'\n')
            if all(s.status=='DONE' for s in state):break
        result={'arm':args.arm,'seat':args.seat,'seed':args.seed,'opponent':'pinned official starter',
                'optimized':not __debug__,'calls':len(walls),'statuses':statuses,'activation':counts,
                'scores':[s.reward for s in state],'complete':all(s.status=='DONE' for s in state),
                'action_sha256':action_hash.hexdigest(),'state_trace_sha256':trace.hexdigest(),
                'max_callback_seconds':max(walls),'wall_seconds':time.perf_counter()-started,
                'native_input_sha256':inputs,'engine_sha256':hashes,
                'frozen_blob':git_blob((package/'frozen_selected.py').read_bytes()),
                'release_authorized':False,
                'limits':['archived-native local run, not latest whole-V4 assembly',
                          'passive-rival projection is not guaranteed under rival trades',
                          'starter is not a leaderboard-strength opponent']}
        args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
        print(json.dumps({k:v for k,v in result.items() if k!='native_input_sha256'},sort_keys=True))
        if not result['complete'] or len(walls)!=int(cfg.episodeSteps)-1 or set(statuses)!={'completed'}:
            raise SystemExit(1)


if __name__=='__main__':
    main()
