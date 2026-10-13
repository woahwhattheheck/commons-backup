# SPDX-License-Identifier: Apache-2.0
"""Full native main.py::agent versus the pinned official starter.

One process per native arm avoids module-cache sharing. This is an explicit
interpreter driver, not the hosted competition or a strong-opponent gate.
"""
from __future__ import annotations
import argparse
import collections
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time


def load(name, path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);sys.modules[name]=mod
    spec.loader.exec_module(mod)
    return mod


def digest(root):
    files={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
           for p in sorted(root.rglob('*')) if p.is_file()
           and '__pycache__' not in p.parts and p.suffix!='.pyc'}
    return hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()


def play(native, seed, seat):
    native=Path(native).resolve();sys.path.insert(0,str(native))
    from compose_native import blob, DEPENDENCIES
    pins={'checks/reference/engine/kaggriculture.py':'3c202c7ee921da239356789e266b694635103fc4',
          'checks/reference/engine/kaggriculture.json':'b354d06b742fe48402513792253f1a5c29366b20',
          'checks/reference/engine/utils.py':'91c8822ee6201ba4a5a8416c7dbe34f95dd61c87',
          'checks/reference/evaluator/loader.py':'23948e10cfc3d32f46c9abb1321b0d8fc8db21d5',
          'main.py':'4a8cf7bcda1f0fea231a144692cb84a779a9e73e',**DEPENDENCIES}
    for path, expected in pins.items():
        if blob((native/path).read_bytes())!=expected:
            raise ValueError('source drift: '+path)
    loader=load('f1_field_loader',native/'checks/reference/evaluator/loader.py')
    engine,engine_hashes=loader.get_engine(native/'checks/reference/engine')
    main=load('f1_field_main',native/'main.py')
    cfg=loader.Struct({k:v.get('default') if isinstance(v,dict) else v
                       for k,v in engine.specification['configuration'].items()})
    cfg.seed=seed
    env=loader.Struct(configuration=cfg,done=False,info={})
    state=[loader.Struct(observation=loader.Struct(),action={},status='ACTIVE',reward=0)
           for _ in (0,1)]
    engine.interpreter(state,env)
    events=[];count=collections.Counter();action_hash=hashlib.sha256();state_hash=hashlib.sha256()
    seconds=[];harvested=collections.Counter();active_tiles={}
    for step in range(720):
        pending=[]
        for i,s in enumerate(state):
            s.observation.step=step;obs=copy.deepcopy(s.observation)
            started=time.perf_counter()
            action=main.agent(obs,cfg) if i==seat else engine.starter_agent(obs)
            elapsed=time.perf_counter()-started;s.action=action
            if i!=seat:continue
            seconds.append(elapsed);count['calls']+=1
            instance=main._INSTANCE
            diagnostics={} if instance is None else instance.diagnostics
            count['status_'+diagnostics.get('status','missing')]+=1
            action_hash.update(json.dumps(action,sort_keys=True,separators=(',',':')).encode()+b'\n')
            f=obs['farms'][seat];positions=[f['farmer'],*f['hands']]
            commands=[action.get('farmer',['PASS']),*action.get('hands',[])]
            for actor,cmd in enumerate(commands):
                if actor>=len(positions):
                    count['ignored_nonexistent_actor_rows']+=1
                    continue
                inv=obs['private']['inventories'][actor];x,y=positions[actor]
                tile=f['tiles'][y][x]
                if inv.get('FERTILIZER',0)>0 and cmd==['PASS']:
                    count['idle_fert']+=1
                    if isinstance(tile,dict) and tile.get('crop')=='WHEAT':
                        count['idle_fert_wheat']+=1
                if cmd==['HARVEST'] and isinstance(tile,dict) and tile.get('crop')=='WHEAT':
                    pending.append((actor,inv.get('WHEAT',0),(x,y),tile['planted_day']))
            for record in diagnostics.get('f1_fert_mix',[]):
                count[record['reason']]+=1
                if record['reason']=='proposed':
                    events.append(copy.deepcopy(record));active_tiles[tuple(record['position'])]=step
        engine.interpreter(state,env)
        for actor,prior,position,planted in pending:
            invs=state[seat].observation.private['inventories']
            if step%24!=23 and actor<len(invs):
                gain=max(0,invs[actor].get('WHEAT',0)-prior)
                harvested['wheat_units_observed_non_eod']+=gain
                if position in active_tiles and planted<=active_tiles[position]//24:
                    harvested['treated_tile_wheat_units_observed_non_eod']+=gain
                    if gain:del active_tiles[position]
        state_hash.update(json.dumps([{'farms':s.observation.farms,
            'private':s.observation.private,'market':s.observation.market,
            'town':s.observation.town,'status':s.status} for s in state],
            sort_keys=True,separators=(',',':')).encode()+b'\n')
        if any(s.status=='DONE' for s in state):break
    if [s.status for s in state]!=['DONE','DONE']:raise ValueError('incomplete game')
    return {'seed':seed,'seat':seat,'bank':[s.reward for s in state],
            'counts':dict(count),'harvested':dict(harvested),'events':events,
            'action_sha256':action_hash.hexdigest(),'state_sha256':state_hash.hexdigest(),
            'max_call_seconds':max(seconds),'native_tree_digest':digest(native),
            'config':json.loads((native/'TITAN-CONFIG.json').read_text()),
            'runtime_blob':blob((native/'titan_runtime.py').read_bytes()),
            'engine_sha256':engine_hashes,'method':'explicit full official interpreter vs starter'}


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--native',type=Path,required=True)
    ap.add_argument('--seed',type=int,required=True);ap.add_argument('--seat',type=int,choices=(0,1),required=True)
    ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    result=play(args.native,args.seed,args.seat)
    args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps({k:result[k] for k in ('seed','seat','bank','counts','max_call_seconds')}))
