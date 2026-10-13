# SPDX-License-Identifier: Apache-2.0
"""Offline full-native games and assertion-based fault controls.

Use a separate process per game. The checked main.py::agent and full official
interpreter run unchanged; no action trimming, budget/config or GC changes.
Helper counting is a separate candidate replay, never throughput evidence.
"""
from __future__ import annotations
import argparse
from collections import Counter
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from compose_scoped_constructor import compose, authenticate_helper, git_blob
from check_scoped_construction import authenticate_runtime, SURFACES

MUTANTS = {
    'strong_owner': 'Construction.test_09_success_release_and_explicit_disposal',
    'wrong_limit': 'Construction.test_07_cache_results_statistics_and_owner_isolation',
    'wrong_result': 'Construction.test_07_cache_results_statistics_and_owner_isolation',
    'swallow': 'Construction.test_08_subclass_overrides_and_exception_identity',
    'retain_single': 'Construction.test_03_all_cache_install_boundaries',
    'retain_joint': 'Construction.test_09_success_release_and_explicit_disposal',
}


def load(path, name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def dumps(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def verify_pair(baseline, candidate, helper, weave=None):
    members=authenticate_runtime(baseline)
    authenticate_helper(helper)
    if weave is not None and git_blob(weave)!='16dde00627effa5d0ae4d73a8e05a295e9534e1f':
        raise ValueError('WEAVE source identity mismatch')
    if (candidate/'SOURCE.json').read_bytes() != (baseline/'SOURCE.json').read_bytes():
        raise ValueError('candidate source manifest mutated')
    sources=json.loads((baseline/'SOURCE.json').read_bytes())['runtime']
    for name in sources:
        original=weave if weave is not None and name=='selected_sell_core.py' else (baseline/name).read_bytes()
        expected=compose(original,helper)[0] if name in SURFACES else original
        if (candidate/name).read_bytes()!=expected:
            raise ValueError('candidate delta mismatch: '+name)
    if (candidate/'scoped_method_cache.py').read_bytes()!=helper:
        raise ValueError('candidate helper mismatch')
    return members


def game(args):
    members=verify_pair(args.baseline,args.candidate,args.helper.read_bytes(),
                        args.weave.read_bytes() if args.weave else None)
    root=args.baseline if args.arm=='baseline' else args.candidate
    sys.path.insert(0,str(root))
    counters=Counter()
    if args.instrument:
        if args.arm!='candidate': raise ValueError('count only a separate candidate replay')
        helper=load(root/'scoped_method_cache.py','scoped_method_cache')
        sys.modules['scoped_method_cache']=helper
        original=helper.scoped_method_cache
        def counted(method,**kw):
            filename=Path(method.__func__.__globals__['__file__']).name
            counters[filename+':'+method.__func__.__name__]+=1
            return original(method,**kw)
        helper.scoped_method_cache=counted
    loader=load(root/'checks/reference/evaluator/loader.py','_spindle_official_loader')
    engine,hashes=loader.get_engine(root/'checks/reference/engine')
    agent=load(root/'main.py','_spindle_native_entrypoint')
    cfg=loader.Struct()
    for key,value in engine.specification['configuration'].items():
        cfg[key]=value.get('default') if isinstance(value,dict) else value
    cfg.seed=args.seed
    env=loader.Struct(configuration=cfg,done=False,info={})
    state=[loader.Struct(observation=loader.Struct(),action={},status='ACTIVE',reward=0) for _ in range(2)]
    engine.interpreter(state,env)
    frames,actions=hashlib.sha256(),hashlib.sha256()
    statuses=Counter();maximum=0.0;started=time.perf_counter()
    for step in range(int(cfg.episodeSteps)):
        for seat,player in enumerate(state):
            player.observation.step=step
            public=copy.deepcopy(player.observation)
            before=copy.deepcopy(public)
            if seat==args.seat:
                at=time.perf_counter();player.action=agent.agent(public,cfg)
                maximum=max(maximum,time.perf_counter()-at)
                instance=agent._INSTANCE
                status=None if instance is None else instance.diagnostics.get('status')
                statuses[str(status)]+=1
                if status!='completed':raise AssertionError('native status: '+str(status))
            else:player.action=engine.starter_agent(public)
            if public!=before:raise AssertionError('agent mutated observation')
            if not isinstance(player.action,dict):raise AssertionError('non-object action')
        actions.update(dumps([step,[s.action for s in state]])+b'\n')
        engine.interpreter(state,env)
        frames.update(dumps([step,state,env])+b'\n')
        if any(s.status=='DONE' for s in state):break
    else:raise AssertionError('official episode did not terminate')
    if step+1!=719:raise AssertionError('expected 719 callbacks')
    result=dict(arm=args.arm,seed=args.seed,seat=args.seat,instrumented=args.instrument,
        optimized=not __debug__,weave=bool(args.weave),steps=step+1,bank=[s.reward for s in state],
        action_sha256=actions.hexdigest(),full_engine_trace_sha256=frames.hexdigest(),
        final_state_sha256=hashlib.sha256(dumps([state,env])).hexdigest(),
        statuses=dict(statuses),helper_constructions=dict(counters),
        elapsed_seconds=time.perf_counter()-started,max_native_call_seconds=maximum,
        runtime_members=members,engine_sha256=hashes)
    args.out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,sort_keys=True))
    return 0


def panel(args):
    rows=[]
    with tempfile.TemporaryDirectory(prefix='spindle-games-') as temp:
        for seat in (0,1):
            for arm,instrument in (('baseline',False),('candidate',False),('candidate',True)):
                output=Path(temp)/(str(len(rows))+'.json')
                command=[sys.executable]+(['-O'] if not __debug__ else [])+[str(Path(__file__).resolve()),
                    '--mode','game','--baseline',str(args.baseline),'--candidate',str(args.candidate),
                    '--helper',str(args.helper),'--arm',arm,'--seed',str(args.seed),'--seat',str(seat),'--out',str(output)]
                if instrument:command+=['--instrument']
                if args.weave:command+=['--weave',str(args.weave)]
                child=subprocess.run(command,text=True,capture_output=True)
                if child.returncode:raise RuntimeError('game failed:\n'+child.stdout+child.stderr)
                rows.append(json.loads(output.read_text()))
                print(json.dumps(rows[-1],sort_keys=True),flush=True)
            reference=rows[-3]
            for row in rows[-2:]:
                for field in ('steps','bank','action_sha256','full_engine_trace_sha256','final_state_sha256','statuses'):
                    if row[field]!=reference[field]:raise AssertionError('native parity: '+field)
            if not rows[-1]['helper_constructions']:raise AssertionError('zero helper engagement')
    report=dict(mode='panel',optimized=not __debug__,games=len(rows),rows=rows,
        disposition='CHECKED_ARCHIVE_ACTION_STATE_PARITY_ONLY',
        limitations=['not current-HEAD complete V4','not economic uplift',
                     'no throughput/hosted-deadline guarantee','instrumented replays separately labeled'])
    args.out.write_text(json.dumps(report,indent=2)+'\n')
    return 0


def faults(args):
    rows=[]
    with tempfile.TemporaryDirectory(prefix='spindle-faults-') as temp:
        for mutant,test in MUTANTS.items():
            target=Path(temp)/(mutant+'.json')
            command=[sys.executable]+(['-O'] if not __debug__ else [])+[
                str(Path(__file__).with_name('check_scoped_construction.py')),
                '--runtime',str(args.baseline),'--helper',str(args.helper),'--test',test,'--out',str(target)]
            control=subprocess.run(command,text=True,capture_output=True)
            good=json.loads(target.read_text())
            if control.returncode!=0 or good['tests']!=1 or good['failures'] or good['errors'] or good['skips']:
                raise AssertionError('selected control not green: '+test)
            bad=subprocess.run(command+['--mutant',mutant],text=True,capture_output=True)
            result=json.loads(target.read_text())
            if bad.returncode!=1 or result['failures']<1 or result['errors'] or result['skips']:
                raise AssertionError('fault not assertion-rejected: '+mutant+'\n'+bad.stdout)
            rows.append(dict(mutant=mutant,control=good,result=result))
            print(mutant+': ASSERTION_REJECTED',flush=True)
    args.out.write_text(json.dumps(dict(mode='faults',optimized=not __debug__,rows=rows),indent=2)+'\n')
    return 0


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=['panel','game','faults'],required=True)
    parser.add_argument('--baseline',required=True,type=Path)
    parser.add_argument('--candidate',type=Path)
    parser.add_argument('--helper',required=True,type=Path)
    parser.add_argument('--out',required=True,type=Path)
    parser.add_argument('--weave',type=Path)
    parser.add_argument('--arm',choices=['baseline','candidate'])
    parser.add_argument('--seed',type=int,default=17)
    parser.add_argument('--seat',type=int,choices=[0,1],default=0)
    parser.add_argument('--instrument',action='store_true')
    args=parser.parse_args()
    args.baseline=args.baseline.resolve();args.helper=args.helper.resolve()
    if args.candidate:args.candidate=args.candidate.resolve()
    if args.weave:args.weave=args.weave.resolve()
    args.out.parent.mkdir(parents=True,exist_ok=True)
    try:
        if args.mode=='faults':return faults(args)
        if args.candidate is None:raise ValueError('--candidate is required for games')
        return game(args) if args.mode=='game' else panel(args)
    except (ValueError,OSError) as error:parser.exit(2,'REFUSED: '+str(error)+'\n')


if __name__=='__main__':raise SystemExit(main())
