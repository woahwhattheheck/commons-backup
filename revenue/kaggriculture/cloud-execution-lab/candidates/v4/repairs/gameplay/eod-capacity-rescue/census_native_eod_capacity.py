# SPDX-License-Identifier: Apache-2.0
"""One isolated native-parent shadow census, not a performance/strength panel.

The official starter is a weak mechanical engagement opponent. No intervention
is sent to the real trajectory: candidate effects are forked for one real turn
only. Invoke a new process for every seed/seat to isolate all agent globals.
"""
from __future__ import annotations
import argparse
from collections import Counter
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import time

from test_native_eod_capacity import NativeEodCapacity as Fixture, ROOT, PINS, RECEIPT
from port_native_eod_capacity import git_blob


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed',type=int,required=True)
    parser.add_argument('--seat',type=int,choices=(0,1),required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    Fixture.setUpClass()
    ev,e=Fixture.ev,Fixture.engine
    cfg=ev.Struct({k:v.get('default') if isinstance(v,dict) else v
                   for k,v in e.specification['configuration'].items()})
    cfg.seed=args.seed
    env=ev.Struct(configuration=cfg,done=False,info={})
    state=[ev.Struct(observation=ev.Struct(),action={},status='ACTIVE',reward=0) for _ in range(2)]
    e.interpreter(state,env)
    if cfg.get('seed') is not None: raise ValueError('Engine did not hide environment seed')
    features=json.loads((ROOT/'TITAN-CONFIG.json').read_text())
    owner=Fixture.original.TitanAgent(Fixture.original.Features(**features))
    trace=hashlib.sha256();statuses=Counter();hours=[];engagements=[];drop_losses=[];start=time.perf_counter()
    original_drop=e._drop_inventories_to_shed
    def record_drop(private, capacity):
        own = private is state[args.seat].observation.private
        before=Counter(private['shed'])
        for inventory in private['inventories']: before.update(inventory)
        result=original_drop(private, capacity)
        if own:
            lost={p:n-private['shed'].get(p,0) for p,n in before.items()
                  if n-private['shed'].get(p,0)>0}
            drop_losses.append({'step':state[args.seat].observation.step,
                                'discarded':lost,'units':sum(lost.values())})
        return result
    # Pass-through telemetry: original pinned drop is still the only transition.
    # Forked worlds have different private identities and never enter this log.
    e._drop_inventories_to_shed=record_drop
    for step in range(cfg.episodeSteps):
        for row in state:
            row.observation.step=step
            row.observation.remainingOverageTime=0
        public=copy.deepcopy(state[args.seat].observation)
        action=owner.act(public,dict(cfg))
        statuses[owner.diagnostics.get('status','missing')]+=1
        state[args.seat].action=copy.deepcopy(action)
        state[1-args.seat].action=e.starter_agent(copy.deepcopy(state[1-args.seat].observation))
        if step%24==23:
            obs=state[args.seat].observation
            Fixture.lane.telemetry.clear()
            candidate=Fixture.lane.apply_eod_capacity_rescue(action,obs,cfg,enabled=True)
            data={'step':step,'carried':sum(sum(x.values()) for x in obs.private['inventories']),
                  'shed':sum(obs.private['shed'].values()),'actors':len(obs.private['inventories']),
                  'market':action['market'],'unit_heads':[a[0] if a else None for a in [action['farmer'],*action['hands']]],
                  'eligible':candidate is not action,'gate_telemetry':dict(Fixture.lane.telemetry)}
            hours.append(data)
            if candidate is not action:
                base,be=copy.deepcopy((state,env));cand,ce=copy.deepcopy((state,env))
                cand[args.seat].action=candidate
                e.interpreter(base,be);e.interpreter(cand,ce)
                own=(cand[0].observation.farms[args.seat]['money']-base[0].observation.farms[args.seat]['money'])
                rival=(cand[0].observation.farms[1-args.seat]['money']-base[0].observation.farms[1-args.seat]['money'])
                engagements.append({'step':step,'sale':candidate['market'][-1],'own_cash_delta':own,
                    'margin_delta':own-rival,'own_private_equal':base[args.seat].observation.private==cand[args.seat].observation.private})
        e.interpreter(state,env)
        trace.update(ev.encoded({'step':step,'actions':[x.action for x in state],
                                 'bank':[f['money'] for f in state[0].observation.farms]}))
        if all(s.status=='DONE' for s in state): break
    source_files={str(p.relative_to(ROOT)):git_blob(p.read_bytes()) for p in sorted(ROOT.rglob('*.py'))}
    source_files['TITAN-CONFIG.json']=git_blob((ROOT/'TITAN-CONFIG.json').read_bytes())
    receipt={'schema':'titan-eod-native-shadow/v1','seed':args.seed,'seat':args.seat,
        'optimized':not __debug__,'native_runtime_blob':PINS['titan_runtime.py'],
        'package_source_files':source_files,'package_source_manifest_sha256':hashlib.sha256(ev.encoded(source_files)).hexdigest(),
        'entrypoint_used':'TitanAgent.act directly; artifact main.py NOT used',
        'opponent':'pinned official starter; engagement only, NOT gauntlet/strength',
        'source_snapshot':'existing artifact10123395668; not whole-current-main certification',
        'status':'complete' if all(s.status=='DONE' for s in state) else 'incomplete',
        'steps':step+1,'scores':[s.reward for s in state],'statuses':dict(statuses),
        'trace_sha256':trace.hexdigest(),'hour23_count':len(hours),'hour23':hours,
        'engagements':engagements,'engagement_count':len(engagements),
        'actual_eod_drop_losses':drop_losses,'actual_discarded_units':sum(x['units'] for x in drop_losses),
        'elapsed_seconds':time.perf_counter()-start,'policy_changes':0}
    args.output.write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n')
    print(json.dumps({k:receipt[k] for k in ('seed','seat','status','steps','statuses','hour23_count','engagement_count','actual_discarded_units','elapsed_seconds')}),flush=True)
    return 0 if receipt['status']=='complete' else 1

if __name__=='__main__': raise SystemExit(main())
