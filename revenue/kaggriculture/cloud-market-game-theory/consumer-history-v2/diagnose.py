# SPDX-License-Identifier: Apache-2.0
"""Read retained observations/receipts only; never feed realized rival actions to policy."""
from collections import Counter
import gzip
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent


def scan():
    rows=[]
    for p in sorted((HERE/'results').glob('*/history_on-*.json')):
        r=json.loads(p.read_text());meta=r.get('terminal') or {};h=meta.get('diagnostics',{}).get('history',{})
        family=h.get('family',{});packet=h.get('terminal_inputs',{})
        row={'receipt':str(p.relative_to(HERE)),'seed':r['seed'],'opponent':r['opponent'],'seat':r['candidate_seat'],
             'family_status':family.get('status'),'scenario_count':len(family.get('scenarios',[])),
             'nonquiet_scenarios':sum(bool(s['shed']) for s in family.get('scenarios',[])),
             'cash_pareto_alternatives':[],'actual_rival_market':None,'actual_queue_in_family':None}
        if r['steps']>=719:
            tape=json.loads(gzip.decompress((p.parent/r['trace_file']).read_bytes()))
            terminal=[x for x in tape if x['step']==718]
            rival=next(x for x in terminal if x['seat']!=r['candidate_seat'])
            row['actual_rival_market']=rival['response']['action']['market']
            norm=lambda q:tuple(tuple(o) for o in list(q)+[[]]*(10-len(q)))
            if family.get('ready'):row['actual_queue_in_family']=norm(row['actual_rival_market']) in {norm(s['market']) for s in family['scenarios']}
        if packet.get('complete'):
            d=packet['document'];cells={(x['plan'],x['scenario']):x for x in d['receipts']}
            baseline=[cells[d['baseline'],s] for s in d['scenario_ids']]
            margins=[x['own_cash']-x['rival_cash'] for x in baseline]
            row['modeled_baseline_margin_range']=[min(margins),max(margins)]
            row['modeled_baseline_own_cash_range']=[min(x['own_cash'] for x in baseline),max(x['own_cash'] for x in baseline)]
            row['modeled_baseline_rival_cash_range']=[min(x['rival_cash'] for x in baseline),max(x['rival_cash'] for x in baseline)]
            for plan in d['plan_ids'][1:]:
                changes=[cells[plan,s]['own_cash']-cells[plan,s]['rival_cash']-m for s,m in zip(d['scenario_ids'],margins)]
                if min(changes)>=0 and max(changes)>0:row['cash_pareto_alternatives'].append({'plan':plan,'margin_changes':changes})
            if r['scores']:
                seat=r['candidate_seat'];row['actual_own_cash']=r['scores'][seat];row['actual_rival_cash']=r['scores'][1-seat]
                row['actual_margin']=r['scores'][seat]-r['scores'][1-seat]
        rows.append(row)
    return {'scope':'Offline scan of retained causal native receipts and evaluation-only realized queues; no new games, private-stock inference or counterfactual outcome claim.',
            'games':len(rows),'family_status':dict(Counter(r['family_status'] for r in rows)),
            'ready_nonquiet_families':sum(r['nonquiet_scenarios']>0 for r in rows),
            'ready_realized_queue_included':sum(r['actual_queue_in_family'] is True for r in rows),
            'ready_realized_queue_omitted':sum(r['actual_queue_in_family'] is False for r in rows),
            'cash_pareto_eligible_games':sum(bool(r['cash_pareto_alternatives']) for r in rows),'rows':rows}


if __name__=='__main__':
    r=scan();(HERE/'ACTIVATION-DIAGNOSIS.json').write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps({k:v for k,v in r.items() if k!='rows'}))
