"""Summarize saved fixed-flow outcomes by first hypothetical YARN reveal.

No probabilities, route policy, further pricing calls or simulations. All cash
bounds are over complete retained shop-identity sequences for one input only.
"""
from __future__ import annotations
import argparse,hashlib,json,csv
from pathlib import Path


def build_map(summary,run):
    if summary.get('complete') is not True or run.get('complete') is not True:
        raise ValueError('Completed source-bound enumeration is required')
    times=[s+1 for s in run['future_draw_after_steps']]
    rows=[]
    for first in list(range(len(times)))+[None]:
        groups=[(sig,g) for sig,g in summary['groups'].items()
                if (sig.find('1') if '1' in sig else None)==first]
        lo=min(g['min_gain'] for _,g in groups);hi=max(g['max_gain'] for _,g in groups)
        rows.append({'first_yarn_visible_step':None if first is None else times[first],
                     'identity_paths':sum(g['count'] for _,g in groups),
                     'wool_patterns':len(groups),'minimum_sheep_minus_main':lo,
                     'maximum_sheep_minus_main':hi,
                     'conditional_sign':'positive_in_all' if lo>0 else 'negative_in_all' if hi<0 else 'depends_on_other_shops'})
    return {'schema':'town-demand.fixed-flow-arrival-boundary.v1',
            'scope':run['scope'],'input_sha256':run['input_sha256'],
            'probabilities':None,'physical_counterfactual':False,'rows':rows,
            'mixed_wool_patterns':[{ 'signature':k,**g } for k,g in summary['groups'].items()
                                    if g['min_gain']<0<g['max_gain']],
            'new_pricing_calls':0,'new_actor_calls':0,'new_games':0}

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--scan',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    summary=json.loads((a.scan/'SUMMARY.json').read_text());run=json.loads((a.scan/'RUN.json').read_text())
    result=build_map(summary,run);a.output.write_text(json.dumps(result,indent=2)+'\n')
    for row in result['rows']:print(row)
    with a.output.with_suffix('.csv').open('w',newline='') as f:
        out=csv.DictWriter(f,fieldnames=list(result['rows'][0]));out.writeheader();out.writerows(result['rows'])
