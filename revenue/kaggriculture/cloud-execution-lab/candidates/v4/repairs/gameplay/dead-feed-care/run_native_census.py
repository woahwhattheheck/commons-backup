# SPDX-License-Identifier: Apache-2.0
"""Native episode with exact W2 + guarded-starvation engagement evidence."""
from __future__ import annotations
import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import time
from native_support import authenticate, load_engine, load_native, new_world


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def run(package, manifest, *, runtime_sha, enabled=False, composed=False,
        starvation=False, fast_tape=False, seat=0, seed=17, steps=719, instrument=True):
    package = Path(package)
    bindings = authenticate(package, manifest, runtime_sha=runtime_sha,
                            enabled=enabled, composed=composed, starvation=starvation, fast_tape=fast_tape)
    engine, Struct, hashes = load_engine(package)
    main = load_native(package)
    counters, events = Counter(), []
    if enabled and instrument:
        import titan_runtime as runtime
        care = runtime.load('_titan_dead_feed_care', package/'r04_dead_feed_care.py', cache=True)
        original_care = care.apply_dead_feed_care
        def observed_care(action, obs, cfg, *, enabled=False):
            before = encode([action, obs, cfg])
            result = original_care(action, obs, cfg, enabled=enabled)
            if encode([action, obs, cfg]) != before:
                raise AssertionError('CARE helper changed inputs')
            counters['care_calls'] += 1
            changes=[]
            oldrows=[action['farmer'],*action['hands']]; newrows=[result['farmer'],*result['hands']]
            for actor,(old,new) in enumerate(zip(oldrows,newrows)):
                counters['care_input_'+str(old[0])] += 1
                if old != new:
                    counters['care_proposed_rewrites'] += 1
                    changes.append({'actor':actor,'before':old,'after':new})
            if changes: events.append({'kind':'care','step':obs['step'],'changes':changes})
            return result
        care.apply_dead_feed_care=observed_care
        if starvation:
            starve = runtime.load('_titan_uncared_eod_feed_skip', package/'r04_uncared_eod_feed_skip.py', cache=True)
            original_starve = starve.apply_guarded_uncared_eod_feed_skip
            def observed_starve(action, obs, cfg, route, *, enabled=False):
                before = encode([action, obs, cfg])
                result = original_starve(action, obs, cfg, route, enabled=enabled)
                if encode([action, obs, cfg]) != before:
                    raise AssertionError('starvation helper changed action/observation/config')
                counters['starvation_calls'] += 1
                rep=dict(getattr(starve,'last_guard_report',{}) or {})
                counters['starvation_eligible'] += int(rep.get('eligible',0) or 0)
                counters['starvation_admitted'] += int(rep.get('admitted',0) or 0)
                for reason,count in (rep.get('blocked',{}) or {}).items():
                    counters['starvation_block_'+str(reason)] += int(count)
                oldrows=[action['farmer'],*action['hands']]; newrows=[result['farmer'],*result['hands']]
                changes=[{'actor':i,'before':a,'after':b} for i,(a,b) in enumerate(zip(oldrows,newrows)) if a!=b]
                if changes:
                    events.append({'kind':'starvation','step':obs['step'],'changes':changes,
                                   'report':deepcopy(rep),'selected':deepcopy(result)})
                    counters['starvation_proposed_rewrites'] += len(changes)
                return result
            starve.apply_guarded_uncared_eod_feed_skip=observed_starve
    state, env = new_world(engine, Struct, seed=seed)
    action_hash, state_hash = hashlib.sha256(), hashlib.sha256()
    statuses, timings = Counter(), []
    for step in range(steps):
        for s in state: s.observation.step = step
        observation=deepcopy(state[seat].observation)
        started=time.perf_counter(); action=main.agent(observation, env.configuration); timings.append(time.perf_counter()-started)
        if not isinstance(action,dict) or not isinstance(action.get('farmer'),list): raise AssertionError('non-native action schema')
        if len(action.get('market',[])) > env.configuration.maxMarketOrdersPerTurn: raise AssertionError('market cap exceeded')
        statuses[getattr(main._INSTANCE,'diagnostics',{}).get('status','no_instance')] += 1
        for row in [action['farmer'],*action.get('hands',[])]: counters['returned_'+str(row[0])] += 1
        for event in events:
            if event['step']==step and 'returned' not in event:
                event['returned']=deepcopy(action)
                event['surviving_rewrites']=sum(([action['farmer'],*action.get('hands',[])][c['actor']]==c['after']) for c in event['changes'])
                counters[event['kind']+'_surviving_rewrites'] += event['surviving_rewrites']
        state[seat].action=action
        state[1-seat].action=engine.starter_agent(deepcopy(state[1-seat].observation))
        action_hash.update(encode([s.action for s in state])); engine.interpreter(state,env)
        state_hash.update(encode({'state':state,'info':env.info}))
        if any(s.status=='DONE' for s in state): break
    return {'bindings':bindings,'engine_sha256':hashes,'seed':seed,'seat':seat,'callbacks':step+1,
            'scores':[s.reward for s in state],'status':[s.status for s in state],
            'native_status_counts':dict(statuses),'census':dict(counters),'events':events,
            'raw_action_trace_sha256':action_hash.hexdigest(),'full_state_trace_sha256':state_hash.hexdigest(),
            'max_callback_seconds':max(timings),'total_callback_seconds':sum(timings),
            'instrumented':bool(enabled and instrument)}

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--package',type=Path,required=True); p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--runtime-sha256',required=True); p.add_argument('--composed',action='store_true'); p.add_argument('--starvation',action='store_true'); p.add_argument('--fast-tape',action='store_true')
    p.add_argument('--enabled',action='store_true'); p.add_argument('--seat',type=int,choices=(0,1),default=0); p.add_argument('--seed',type=int,default=17)
    p.add_argument('--steps',type=int,default=719); p.add_argument('--no-instrument',action='store_true'); p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); result=run(a.package,a.manifest,runtime_sha=a.runtime_sha256,enabled=a.enabled,composed=a.composed,starvation=a.starvation,fast_tape=a.fast_tape,seat=a.seat,seed=a.seed,steps=a.steps,instrument=not a.no_instrument)
    a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('seat','callbacks','scores','native_status_counts','census','raw_action_trace_sha256','full_state_trace_sha256')}))
