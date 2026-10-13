# SPDX-License-Identifier: Apache-2.0
"""Final version-separated evidence, including reused exact control records."""
from collections import defaultdict
from fractions import Fraction
import gzip
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent


def read(name):
    return [json.loads(gzip.decompress(p.read_bytes())) for p in sorted((HERE/'results'/name).glob('*.json.gz'))]


def summarize(rows):
    summaries={};pairs=[]
    controls={(r['seed'],r['opponent'],r['candidate_seat']):r for r in rows if r['arm']=='baseline'}
    for arm in ('baseline','pure','mixed'):
        games=[r for r in rows if r['arm']==arm];wtl=defaultdict(lambda:{'W':0,'T':0,'L':0})
        actors=[g['actors'][g['candidate_seat']] for g in games]
        for g in games:
            if g['status']!='complete':continue
            s=g['candidate_seat'];d=g['scores'][s]-g['scores'][1-s]
            wtl[g['opponent']]['W' if d>0 else 'L' if d<0 else 'T']+=1
            if arm=='baseline':continue
            b=controls[g['seed'],g['opponent'],s]
            delta=[g['scores'][i]-b['scores'][i] for i in (s,1-s)]
            bd=b['scores'][s]-b['scores'][1-s]
            pairs.append({'arm':arm,'seed':g['seed'],'opponent':g['opponent'],'seat':s,
                'own_cash_delta':delta[0],'rival_cash_delta':delta[1],'margin_delta':delta[0]-delta[1],
                'outcome_changed':(d>0)-(d<0)!=(bd>0)-(bd<0),
                'identical_complete_trace':g['trace_sha256']==b['trace_sha256']})
        summaries[arm]={'games':len(games),'complete':sum(g['status']=='complete' for g in games),
            'wtl_by_opponent':dict(wtl),
            'max_policy_seconds':max(a['max_call_seconds'] for a in actors),
            'max_rpc_seconds':max(a['max_rpc_seconds'] for a in actors),
            'max_first_policy_seconds':max(a.get('first_call_seconds',0) for a in actors),
            'max_episode_wall_seconds':max(g['wall_seconds'] for g in games),
            'activations':sum(a.get('t15_counts',{}).get('activations',0) for a in actors),
            'nondegenerate_mixtures':sum(sum(Fraction(x)>0 for x in e['metadata']['activation']['commitment']['weights'])>1
                for g in games for e in g['activation_events']),
            'tables':sum(a.get('t15_counts',{}).get('tables',0) for a in actors)}
    return {'arms':summaries,'pairs':pairs}


def main():
    dev1,held1,dev2,held2=map(read,('development','held','development-v2','held-v2'))
    baseline=[r for r in dev1 if r['arm']=='baseline']
    result={'unique_games_executed':len(dev1)+len(held1)+len(dev2)+len(held2),
        'completed_games':sum(r['status']=='complete' and r['steps']==719 for r in dev1+held1+dev2+held2),
        'all_complete':all(r['status']=='complete' and r['steps']==719 for r in dev1+held1+dev2+held2),
        'execution_failures':[{'version':v,'phase':phase,'seed':r['seed'],'arm':r['arm'],
                              'opponent':r['opponent'],'seat':r['candidate_seat'],'failure':r['failure']}
            for v,phase,rows in (('v1','development',dev1),('v1','held',held1),('v2','development',dev2),('v2','held',held2))
            for r in rows if r['status']!='complete'],
        'versions':{
            'v1':{'source':'4d97474b0188b0373be1b52b610c0114ceb033c8','development':summarize(dev1),'held':summarize(held1)},
            'v2':{'freeze_sha256':hashlib.sha256((HERE/'SOURCE-FREEZE.json').read_bytes()).hexdigest(),
                  'reused_development_baseline_games':len(baseline),'new_games':len(dev2)+len(held2),
                  'development':summarize(dev2+baseline),'held':summarize(held2)}},
        'engine_tables':11,'serialized_official_transitions':7074,'tests':11,
        'selection':'v2 research only; selected frozen SELL unchanged',
        'interpretation':'No nondegenerate mixture was selected in these full games. V1 endpoint timing gains and three held pure-arm RPC timeouts remain preserved. Restored causal streams remove the v1 development choice\'s strictly positive bound. V2 held endpoint choices lost four own cash per Apex seat without changing outcomes.'}
    (HERE/'RESULTS.json').write_text(json.dumps(result,indent=2)+'\n')
    files=list((HERE/'results').rglob('*.gz'))+list((HERE/'results').rglob('manifest.json'))
    evidence={str(p.relative_to(HERE)):{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(files)}
    (HERE/'EVIDENCE.json').write_text(json.dumps(evidence,indent=2)+'\n')
    print(json.dumps({'unique_games':result['unique_games_executed'],'all_complete':result['all_complete'],
        'evidence_files':len(evidence),'v2':result['versions']['v2']},indent=2))


if __name__=='__main__':main()
