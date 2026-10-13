# SPDX-License-Identifier: Apache-2.0
"""Inspect completed sensitivity outputs without executing an actor or simulator."""
from __future__ import annotations
import argparse
from fractions import Fraction
import gzip
import hashlib
import json
from pathlib import Path


def inspect(package, results):
    package, results = Path(package), Path(results)
    raw = (results/'experiment.json').read_bytes()
    experiment = json.loads(raw)
    original = json.loads((package/'work/reached-final.json').read_text())
    baseline = {c['offered_route']:c for c in original['replay']['cases']
                if c['scenario_id']=='observed_shops_continue_no_rival'}
    if not experiment['complete']:
        raise ValueError('The saved experiment is not complete')
    start, end = original['replay']['start_step'], original['replay']['end_step']
    initial_cash = original['validation']['input_row']['observation']['farms'][0]['money']
    witnesses, comparisons = [], []
    for record in experiment['cases']:
        path = (results/record['file']).resolve()
        if not path.is_relative_to(results.resolve()):
            raise ValueError('Output member is outside the experiment directory')
        compressed = path.read_bytes()
        decoded = gzip.decompress(compressed)
        if (hashlib.sha256(compressed).hexdigest()!=record['sha256'] or
            hashlib.sha256(decoded).hexdigest()!=record['decoded_sha256']):
            raise ValueError('Output member byte binding differs')
        document = json.loads(decoded)
        if document['validation'] != experiment['validation'] or document['source'] != experiment['driver']:
            raise ValueError('Output uses another source/input binding')
        case = document['replay']['cases'][0]
        if case['status']!='complete' or case['final_cash']!=record['final_cash']:
            raise ValueError('Incomplete or inconsistent terminal result')
        visible = int(next(iter(document['scenario']['new_shops'])))+1
        old = baseline[case['offered_route']]
        rows = case['market_rows']
        if [r['step'] for r in rows] != list(range(start,end+1)):
            raise ValueError('Market trajectory is not complete/ordered')
        actions, old_actions = case['result']['actions'], old['result']['actions']
        prefix = visible-start
        if (rows[:prefix]!=old['market_rows'][:prefix] or
            any(actions[str(t)]!=old_actions[str(t)] for t in range(start,visible))):
            raise ValueError('A trajectory differs before the changed environment input')
        if initial_cash+sum(r['cash_delta'] for r in rows)!=case['final_cash']:
            raise ValueError('Cash ledger does not reconcile')
        witnesses.append({
            'offered_route':case['offered_route'],'first_visible_step':visible,
            'identical_prefix_actions':prefix,'identical_prefix_market_rows':prefix,
            'first_changed_action':next((t for t in range(start,end+1)
                                        if actions[str(t)]!=old_actions[str(t)]),None),
            'first_changed_market_row':next((a['step'] for a,b in zip(rows,old['market_rows']) if a!=b),None),
            'cash_rows_reconciled':len(rows),'terminal_cash':case['final_cash'],
            'discarded_stock':case['result']['discarded_stock'],'case_file':record['file']})
    complete_rows=experiment['reused_comparisons']+experiment['comparisons']
    no_buyer=next(row['sheep_minus_main'] for row in complete_rows if row['first_visible_step'] is None)
    for row in complete_rows:
        delta=row['sheep_minus_main']
        threshold=None
        if row['first_visible_step'] is not None and delta>0 and no_buyer<0:
            value=-Fraction(no_buyer)/(Fraction(delta)-Fraction(no_buyer))
            threshold={'numerator':value.numerator,'denominator':value.denominator,
                       'decimal':float(value),'scope':'arithmetic mixture of THIS one-buyer case and no-buyer case only'}
        comparisons.append(dict(row,two_case_break_even_weight=threshold))
    return {'schema':'titan.arrival-sensitivity-inspection.v1',
            'experiment_sha256':hashlib.sha256(raw).hexdigest(),
            'source':experiment['driver'],'comparison_table':comparisons,
            'new_complete_tails':len(witnesses),
            'new_model_decisions':sum(w['cash_rows_reconciled'] for w in witnesses),
            'identical_pre_arrival_action_pairs':sum(w['identical_prefix_actions'] for w in witnesses),
            'identical_pre_arrival_market_row_pairs':sum(w['identical_prefix_market_rows'] for w in witnesses),
            'witnesses':witnesses,'assumptions':experiment['assumptions'],
            'new_actor_calls':0,'new_native_transitions':0,'new_full_games':0,
            'estimated_arrival_probabilities':None,'policy_selection':None}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package',type=Path,required=True)
    parser.add_argument('--results',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=inspect(args.package,args.results)
    args.output.write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('new_complete_tails','new_model_decisions',
                        'identical_pre_arrival_action_pairs','comparison_table')},indent=2))


if __name__=='__main__':
    main()
