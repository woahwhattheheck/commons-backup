# SPDX-License-Identifier: Apache-2.0
"""Summarize preserved paired evidence without running a policy or game."""
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent


def read(path):
    return json.loads(gzip.decompress(path.read_bytes()) if path.suffix=='.gz' else path.read_text())


def summarize():
    output={'selection':'Preserve frozen SELL; liquidity cycle is runnable research with no WTL flips and small paired cash gains recorded below.',
            'panels':{},'first_attempt':'Process-pool return serialization stopped the first development attempt before a score was read. The harness now converts Struct subclasses to plain JSON values; policy stayed unchanged. Original manifest and error retained.'}
    for panel in ('development-recovered','held'):
        paths=list((HERE/'results'/panel).glob('*-*-*-*.json*'))
        paths=[p for p in paths if p.suffix=='.gz' or not p.with_suffix('.json.gz').exists()]
        rows=[read(p) for p in paths]
        by_key={(r['arm'],r['seed'],r['opponent'],r['candidate_seat']):r for r in rows}
        data={'scored_games':len(rows),'evaluation_failures':sum(r['status']!='complete' for r in rows),
              'arms':{},'pairs':[]}
        for arm in ('control','cycle'):
            rr=[r for r in rows if r['arm']==arm]
            opponents={}
            for opponent in ('arlene','apex','sell'):
                wtl=Counter()
                for r in rr:
                    if r['opponent']!=opponent or r['status']!='complete':continue
                    margin=r['scores'][r['candidate_seat']]-r['scores'][1-r['candidate_seat']]
                    wtl['wins' if margin>0 else 'losses' if margin<0 else 'ties']+=1
                opponents[opponent]={k:wtl[k] for k in ('wins','ties','losses')}
            data['arms'][arm]={'opponents':opponents,
                'max_action_seconds':max(r['actors'][r['candidate_seat']]['max_call_seconds'] for r in rr),
                'max_first_action_seconds':max(r['actors'][r['candidate_seat']]['first_call_seconds'] for r in rr),
                'max_startup_seconds':max(r['actors'][r['candidate_seat']]['startup_seconds'] for r in rr),
                'max_episode_wall_seconds':max(r['wall_seconds'] for r in rr),
                'cycle_signature_events':sum(len(r['cycle_signature_events']) for r in rr)}
        for r in rows:
            if r['arm']!='cycle':continue
            seat=r['candidate_seat']; other=by_key['control',r['seed'],r['opponent'],seat]
            own=r['scores'][seat]-other['scores'][seat]
            rival=r['scores'][1-seat]-other['scores'][1-seat]
            data['pairs'].append({'seed':r['seed'],'opponent':r['opponent'],'seat':seat,
                'own_cash_delta':own,'rival_cash_delta':rival,'margin_delta':own-rival})
        output['panels'][panel]=data
    freeze=read(HERE/'SOURCE-FREEZE.json')
    output['frozen_files_unchanged']=all(hashlib.sha256((HERE/name).read_bytes()).hexdigest()==value for name,value in freeze['files'].items())
    output['engine_cases']=len(read(HERE/'results/engine.json.gz' if (HERE/'results/engine.json.gz').exists() else HERE/'results/engine.json')['cases'])
    (HERE/'RESULTS.json').write_text(json.dumps(output,indent=2)+'\n')
    return output


if __name__=='__main__':
    print(json.dumps(summarize(),indent=2))
