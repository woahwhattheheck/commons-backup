# SPDX-License-Identifier: Apache-2.0
"""Fresh-process main.agent/official-interpreter trace equivalence.

Each invocation executes one arm and seat. Compare emitted trace hashes across
baseline/candidate for the same seed/seat. Candidate source is constructed only
inside a temporary copy; the supplied current package is never changed. This is
an explicit local driver, NOT Kaggle hosted evaluation or a strength claim.
"""
from __future__ import annotations
import argparse
from collections import Counter
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time
from patch_selected_incumbent import git_blob, transform

SOURCE_SHA256='e87d70dd3bcf5aea1e929f1a5dbdc86f3cc33d8a0b3492986f2970fc8e774be2'


def verify(root):
    content=(root/'SOURCE.json').read_bytes()
    if hashlib.sha256(content).hexdigest()!=SOURCE_SHA256:
        raise ValueError('SOURCE.json does not match current b567 archive')
    manifest=json.loads(content)
    for name,pin in manifest['runtime'].items():
        path=(root/name).resolve()
        if not path.is_relative_to(root.resolve()):raise ValueError('manifest path escapes root')
        data=path.read_bytes()
        if len(data)!=pin['bytes'] or hashlib.sha256(data).hexdigest()!=pin['sha256']:
            raise ValueError('package input mismatch: '+name)
    return len(manifest['runtime'])


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def run(root,arm,seat,seed,steps):
    if seat not in (0,1) or arm not in ('baseline','candidate'):
        raise ValueError('invalid arm or seat')
    pins=verify(root)
    original=(root/'selected_sell_core.py').read_bytes()
    with tempfile.TemporaryDirectory(prefix='titan-sieve-') as directory:
        runtime=Path(directory)/'runtime';shutil.copytree(root,runtime)
        if arm=='candidate':(runtime/'selected_sell_core.py').write_bytes(transform(original))
        sys.path.insert(0,str(runtime))
        ev=load('sieve_evaluator',runtime/'checks/reference/evaluator/evaluate.py')
        engine,hashes=ev.get_engine(runtime/'checks/reference/engine',
                                  runtime/'checks/reference/evaluator/loader.py')
        main=load('sieve_main',runtime/'main.py');S=ev.Struct
        cfg=S({k:v.get('default') if isinstance(v,dict) else v
               for k,v in engine.specification['configuration'].items()})
        cfg.seed=seed
        env=S(configuration=cfg,done=False,info={})
        state=[S(observation=S(),action={},status='ACTIVE',reward=0) for _ in range(2)]
        engine.interpreter(state,env)
        trace=hashlib.sha256();statuses=Counter();calls=[];extra_hands=0
        # Wrap the exact active optimizer only to count calls; no alternate model.
        import selected_sell_core
        optimizer=selected_sell_core.optimize_lot;optimizations=[0]
        def counted(**kwargs):
            optimizations[0]+=1
            return optimizer(**kwargs)
        selected_sell_core.optimize_lot=counted
        for step in range(min(steps,int(cfg.episodeSteps))):
            for player,s in enumerate(state):
                s.observation.step=step
                observation=copy.deepcopy(s.observation)
                if player==seat:
                    start=time.perf_counter();s.action=main.agent(observation,cfg)
                    calls.append(time.perf_counter()-start)
                    instance=main._INSTANCE
                    status='no_instance' if instance is None else instance.diagnostics.get('status','missing')
                    statuses[status]+=1
                    if len(s.action.get('hands',[]))>len(observation.farms[seat]['hands']):
                        extra_hands+=1
                else:s.action=engine.starter_agent(observation)
            # Preserve every raw row, including nonexistent-actor PLANT demand.
            actions=copy.deepcopy([s.action for s in state])
            engine.interpreter(state,env)
            frame={'step':step,'actions':actions,'states':[dict(s) for s in state]}
            trace.update(json.dumps(frame,sort_keys=True,separators=(',',':')).encode()+b'\n')
            if any(s.status=='DONE' for s in state):
                env.done=True;break
        return {'arm':arm,'seat':seat,'seed':seed,'steps':step+1,
            'status':[s.status for s in state],'reward':[s.reward for s in state],
            'trace_sha256':trace.hexdigest(),'native_diagnostics':dict(statuses),
            'optimizer_calls':optimizations[0],'extra_hands_preserved':extra_hands,
            'max_agent_seconds':max(calls),'total_agent_seconds':sum(calls),
            'source_manifest_sha256':SOURCE_SHA256,'verified_runtime_files':pins,
            'selected_core_blob':git_blob((runtime/'selected_sell_core.py').read_bytes()),
            'official_engine_sha256':hashes,'optimized':not __debug__,
            'qualification':'One native-versus-official-starter trace, not a strength gate.'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('runtime',type=Path);p.add_argument('arm',choices=('baseline','candidate'))
    p.add_argument('--seat',type=int,choices=(0,1),default=0)
    p.add_argument('--seed',type=int,default=9922999)
    p.add_argument('--steps',type=int,default=720)
    args=p.parse_args()
    if not 1<=args.steps<=720:p.error('steps must be in 1..720')
    print(json.dumps(run(args.runtime.resolve(),args.arm,args.seat,args.seed,args.steps),sort_keys=True))
