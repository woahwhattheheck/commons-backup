# SPDX-License-Identifier: Apache-2.0
"""Summarize actual packaged games, eligibility and paired cash independently."""
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent


def verdict(r):
    if r['status']!='complete':return 'incomplete'
    s=r['candidate_seat'];d=r['scores'][s]-r['scores'][1-s]
    return 'W' if d>0 else 'L' if d<0 else 'T'


def summarize():
    games=[];evidence={}
    for p in sorted((HERE/'results').glob('*/*.json')):
        r=json.loads(p.read_text())
        if 'candidate_seat' not in r:continue
        r['receipt']=str(p.relative_to(HERE));games.append(r)
        evidence[r['receipt']]=hashlib.sha256(p.read_bytes()).hexdigest()
    controls={(r['seed'],r['opponent'],r['candidate_seat']):r for r in games if r['arm']=='history_off'}
    pairs=[];terminal=[];arms={}
    for arm in sorted({r['arm'] for r in games}):
        rows=[r for r in games if r['arm']==arm]
        actors=[r['actors'][r['candidate_seat']] for r in rows if len(r['actors'])>r['candidate_seat']]
        arms[arm]={'attempts':len(rows),'outcomes':dict(Counter(verdict(r) for r in rows)),
            'by_opponent':{o:dict(Counter(verdict(r) for r in rows if r['opponent']==o)) for o in sorted({r['opponent'] for r in rows})},
            'max_call_seconds':max((a.get('max_call_seconds',0) for a in actors),default=0),
            'max_rpc_seconds':max((a.get('max_rpc_seconds',0) for a in actors),default=0),
            'max_episode_seconds':max((r['wall_seconds'] for r in rows),default=0),
            'counts':dict(sum((Counter(r['counts']) for r in rows),Counter()))}
    for r in games:
        if r['arm']!='history_on':continue
        seat=r['candidate_seat'];base=controls.get((r['seed'],r['opponent'],seat))
        complete=base is not None and base['status']==r['status']=='complete'
        pairs.append({'seed':r['seed'],'opponent':r['opponent'],'seat':seat,'complete':complete,
            'off':verdict(base) if base else None,'on':verdict(r),'same_engine_trace':r['trace_sha256']==base['trace_sha256'] if base else None,
            'own_off':base['scores'][seat] if base and base['scores'] else None,
            'rival_off':base['scores'][1-seat] if base and base['scores'] else None,
            'own_on':r['scores'][seat] if r['scores'] else None,'rival_on':r['scores'][1-seat] if r['scores'] else None,
            'own_delta':r['scores'][seat]-base['scores'][seat] if complete else None,
            'rival_delta':r['scores'][1-seat]-base['scores'][1-seat] if complete else None})
        meta=r.get('terminal') or {};diag=meta.get('diagnostics',{});h=diag.get('history',{});family=h.get('family',{});packet=h.get('terminal_inputs',{})
        records=meta.get('history_records',{})
        excluded={}
        for lag in range(1,6):
            t=718-lag*24
            excluded[str(lag)]={p:records.get(p,{}).get(str(t),{'reason':'missing'}) for p in family.get('observed_products',[]) if not records.get(p,{}).get(str(t),{}).get('exact',False)}
        terminal.append({'seed':r['seed'],'opponent':r['opponent'],'seat':seat,'status':diag.get('status'),
            'family_status':family.get('status'),'joint_support':family.get('joint_support'),'product_support':family.get('product_support'),
            'scenario_count':len(family.get('scenarios',[])),'nonempty_scenarios':sum(bool(s['shed']) for s in family.get('scenarios',[])),
            'input_status':packet.get('status'),'input_complete':packet.get('complete'),
            'changed':h.get('changed'),'selection':h.get('selection'),'excluded_lag_evidence':excluded,
            'history_counts':meta.get('history_counts'),'receipt':r['receipt']})
    return {'attempts':len(games),'complete':sum(r['status']=='complete' for r in games),'arms':arms,'pairs':pairs,'terminal':terminal,'evidence':evidence}


if __name__=='__main__':
    r=summarize();(HERE/'RESULTS.json').write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps({k:r[k] for k in ('attempts','complete','arms')}))
