# SPDX-License-Identifier: Apache-2.0
"""Compare recorded development branches with identical entire observations."""
import gzip
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def run():
    root=HERE/'results/broad-development';found=[]
    for path in sorted(root.glob('adaptive-*.json.gz')):
        adaptive=json.loads(gzip.decompress(path.read_bytes()));seat=adaptive['candidate_seat']
        for arm in ('fixed','static'):
            other_path=root/path.name.replace('adaptive-',arm+'-',1)
            if not other_path.exists():continue
            other=json.loads(gzip.decompress(other_path.read_bytes()))
            by_step={e['step']:e for e in other['events']}
            for e in adaptive['events']:
                d=e['metadata']['decision'];b=by_step.get(e['step'])
                if d.get('reason')!='observed_branch' or not b:continue
                bd=b['metadata']['decision']
                if (bd.get('reason')!='observed_branch' or e['observation']!=b['observation']
                        or d['tree']!=bd['tree'] or e['actions'][seat]==b['actions'][seat]):continue
                aa,ba=e['actions'][seat],b['actions'][seat]
                assert {k:v for k,v in aa.items() if k!='market'}=={k:v for k,v in ba.items() if k!='market'}
                found.append({'seed':adaptive['seed'],'opponent':adaptive['opponent'],'seat':seat,
                    'step':e['step'],'comparison':arm,'item':d['window']['item'],
                    'entire_observation_sha256':digest(e['observation']),'tree_sha256':digest(d['tree']),
                    'observation_equal':True,'tree_equal':True,'nonmarket_action_equal':True,
                    'adaptive_plan_index':d['index'],'comparison_plan_index':bd['index'],
                    'adaptive_action':aa,'comparison_action':ba,'adaptive_cash_after':e['cash_after'],
                    'comparison_cash_after':b['cash_after'],
                    'terminal_own_delta':adaptive['scores'][seat]-other['scores'][seat],
                    'terminal_rival_delta':adaptive['scores'][1-seat]-other['scores'][1-seat],
                    'receipts':[str(path.relative_to(HERE)),str(other_path.relative_to(HERE))]})
    return {'development_only':True,'cases':found,
        'interpretation':'Immediate sale receipts also reduce inventory; they are not incremental profit. Terminal deltas compare whole games, and can include subsequent responsive behavior.'}


if __name__=='__main__':
    r=run();(HERE/'CAUSAL-ATTRIBUTION.json').write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps({'same_observation_different_action_cases':len(r['cases']),
        'opponents':sorted({c['opponent'] for c in r['cases']})}))
