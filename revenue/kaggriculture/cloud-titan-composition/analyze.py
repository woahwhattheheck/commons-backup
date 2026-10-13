# SPDX-License-Identifier: MIT
"""Paired terminal outcomes; own cash and rival cash are separate diagnostics."""
import collections
import json
from pathlib import Path
import statistics

HERE=Path(__file__).resolve().parent
key=lambda g:(g['seed'],g['opponent'],g['candidate_seat'])
def cash(g):
    s=g['candidate_seat'];return g['scores'][s],g['scores'][1-s]
def outcome(g):
    own,rival=cash(g);return 'W' if own>rival else 'L' if own<rival else 'T'

def analyze(split):
    reports={p.stem[len(split)+1:]:json.loads(p.read_text()) for p in (HERE/'results').glob(split+'-*.json')}
    base={key(g):g for g in reports['baseline']['games']}
    output={}
    for arm,report in reports.items():
        games=report['games'];valid=[g for g in games if g['status']=='complete']
        paired=[(g,base[key(g)]) for g in valid if key(g) in base and base[key(g)]['status']=='complete']
        output[arm]={'games':len(games),'failures':len(games)-len(valid),
                     'wtl':dict(collections.Counter(map(outcome,valid))),
                     'paired_flips_vs_baseline':dict(collections.Counter(outcome(b)+'→'+outcome(g) for g,b in paired)),
                     'mean_own_cash_delta':statistics.mean(cash(g)[0]-cash(b)[0] for g,b in paired),
                     'mean_rival_cash_delta':statistics.mean(cash(g)[1]-cash(b)[1] for g,b in paired),
                     'mean_game_cash_margin_delta':statistics.mean((cash(g)[0]-cash(g)[1])-(cash(b)[0]-cash(b)[1]) for g,b in paired),
                     'max_candidate_call_seconds':max(g['actors'][g['candidate_seat']]['max_call_seconds'] for g in valid),
                     'opponents':report['summary']}
    if all(a in reports for a in ('baseline','carrot','cap','carrot_cap')):
        maps={a:{key(g):g for g in reports[a]['games']} for a in ('baseline','carrot','cap','carrot_cap')}
        interactions=[]
        for k in base:
            values={a:cash(m[k])[0]-cash(m[k])[1] for a,m in maps.items()}
            interactions.append({'seed':k[0],'opponent':k[1],'seat':k[2],
                'margin_interaction':values['carrot_cap']-values['cap']-values['carrot']+values['baseline']})
        output['factorial_interactions']=interactions
    return output

if __name__=='__main__':
    import sys
    print(json.dumps(analyze(sys.argv[1] if len(sys.argv)>1 else 'dev'),indent=2,ensure_ascii=False))
