# SPDX-License-Identifier: Apache-2.0
"""Aggregate exact paired game records without rounding terminal cash."""
from collections import defaultdict
import gzip
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent


def analyze():
    games=[json.loads(gzip.decompress(p.read_bytes())) for p in sorted((HERE/'results/development').glob('*.json.gz'))]
    grouped={(g['seed'],g['opponent'],g['candidate_seat'],g['arm']):g for g in games}
    arms={};pairs=[]
    for arm in ('baseline','pure','mixed'):
        rows=[g for g in games if g['arm']==arm];wtl=defaultdict(lambda:dict(W=0,T=0,L=0))
        for g in rows:
            if g['status']!='complete':continue
            s=g['candidate_seat'];delta=g['scores'][s]-g['scores'][1-s]
            wtl[g['opponent']]['W' if delta>0 else 'L' if delta<0 else 'T']+=1
        actors=[g['actors'][g['candidate_seat']] for g in rows]
        arms[arm]={'games':len(rows),'complete':sum(g['status']=='complete' for g in rows),
            'wtl_by_opponent':dict(wtl),
            'max_call_seconds':max(a['max_call_seconds'] for a in actors),
            'max_rpc_seconds':max(a['max_rpc_seconds'] for a in actors),
            'max_first_call_seconds':max(a.get('first_call_seconds',0) for a in actors),
            'max_episode_wall_seconds':max(g['wall_seconds'] for g in rows),
            'eligible_windows':sum(a.get('t15_counts',{}).get('eligible_windows',0) for a in actors),
            'tables':sum(a.get('t15_counts',{}).get('tables',0) for a in actors),
            'activations':sum(a.get('t15_counts',{}).get('activations',0) for a in actors),
            'aborts':sum(a.get('t15_counts',{}).get('aborts',0) for a in actors)}
        if arm=='baseline':continue
        for g in rows:
            s=g['candidate_seat'];b=grouped[g['seed'],g['opponent'],s,'baseline']
            if g['status']!='complete' or b['status']!='complete':continue
            d=[g['scores'][i]-b['scores'][i] for i in (s,1-s)]
            pairs.append({'arm':arm,'seed':g['seed'],'opponent':g['opponent'],'seat':s,
                'own_cash_delta':d[0],'rival_cash_delta':d[1],'margin_delta':d[0]-d[1],
                'identical_complete_trace':g['trace_sha256']==b['trace_sha256']})
    return {'games':len(games),'arms':arms,'pairs':pairs,
        'selection':'Frozen SELL retained; research interface only',
        'held_seeds_reserved_unconsumed':[9872101,9872119]}


if __name__=='__main__':
    result=analyze();(HERE/'RESULTS.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'games':result['games'],'arms':result['arms'],
        'changed_cash_pairs':sum(p['own_cash_delta']!=0 or p['rival_cash_delta']!=0 for p in result['pairs']),
        'identical_trace_pairs':sum(p['identical_complete_trace'] for p in result['pairs'])},indent=2))
