# SPDX-License-Identifier: Apache-2.0
"""Keep per-game outcomes, own/rival cash, activations and timing distinct."""
from collections import Counter,defaultdict
import gzip
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent


def outcome(row):
    if row['status']!='complete':return 'incomplete'
    s=row['candidate_seat'];d=row['scores'][s]-row['scores'][1-s]
    return 'W' if d>0 else 'L' if d<0 else 'T'


def summarize():
    games=[];evidence={}
    for path in sorted((HERE/'results').glob('*/*.json.gz')):
        row=json.loads(gzip.decompress(path.read_bytes()))
        if 'candidate_seat' not in row:continue
        row['receipt']=str(path.relative_to(HERE));games.append(row)
        evidence[row['receipt']]=hashlib.sha256(path.read_bytes()).hexdigest()
    baselines={(r['seed'],r['opponent'],r['candidate_seat']):r for r in games if r['arm']=='baseline'}
    summary={};pairs=[]
    for arm in sorted({r['arm'] for r in games}):
        rows=[r for r in games if r['arm']==arm]
        groups=defaultdict(Counter);times=[];rpc=[];cold=[];counts=Counter();episodes=[]
        for r in rows:
            groups[str(r['seed'])][outcome(r)]+=1
            actor=r['actors'][r['candidate_seat']]
            times.append(actor.get('max_call_seconds',0));rpc.append(actor.get('max_rpc_seconds',0))
            cold.append(actor.get('first_call_seconds',0));counts.update(actor.get('adaptive_counts',{}))
            for key in ('elapsed_seconds','wall_seconds','seconds'):
                if key in r:episodes.append(r[key]);break
            key=(r['seed'],r['opponent'],r['candidate_seat']);base=baselines.get(key)
            if arm!='baseline' and base:
                seat=r['candidate_seat'];complete=r['status']==base['status']=='complete'
                pair={'arm':arm,'seed':r['seed'],'opponent':r['opponent'],'seat':seat,
                      'outcome':outcome(r),'control_outcome':outcome(base),'complete':complete,
                      'own_cash':r['scores'][seat] if r['scores'] is not None else None,
                      'rival_cash':r['scores'][1-seat] if r['scores'] is not None else None,
                      'control_own_cash':base['scores'][seat],'control_rival_cash':base['scores'][1-seat],
                      'own_delta':r['scores'][seat]-base['scores'][seat] if complete else None,
                      'rival_delta':r['scores'][1-seat]-base['scores'][1-seat] if complete else None,
                      'failure':r['failure'],'receipt':r['receipt']}
                pairs.append(pair)
        summary[arm]={'games':len(rows),'outcomes':dict(Counter(outcome(r) for r in rows)),
                      'by_seed':{k:dict(v) for k,v in groups.items()},'counts':dict(counts),
                      'max_policy_seconds':max(times,default=0),'max_rpc_seconds':max(rpc,default=0),
                      'max_first_call_seconds':max(cold,default=0),'max_episode_seconds':max(episodes,default=0)}
    return {'unique_attempts':len(games),'completed':sum(r['status']=='complete' for r in games),
            'source_checkpoint':'0419f0393d13b4c7eda55d84a0d0b63dce512c77',
            'summary':summary,'cash_pairs':pairs,'evidence':evidence,
            'scope':'Independent development/held seeds; public-bank greedy and SciPy are one lonespear lineage. Discovery v0 diagnostic aborts include inactive projection fallbacks; decision source is preserved.'}


if __name__=='__main__':
    r=summarize();(HERE/'RESULTS.json').write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps({k:v for k,v in r.items() if k not in ('cash_pairs','evidence')}))
