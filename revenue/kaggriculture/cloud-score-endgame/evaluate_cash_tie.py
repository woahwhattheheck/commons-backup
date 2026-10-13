# SPDX-License-Identifier: Apache-2.0
"""Use retained runtime matrices, then separately look up frozen native outcomes.

No engine, model, policy/controller, or new scenario generation is performed.
The optional selector consumes only public/own inputs and its saved hypothetical
receipts. Historical opponent/outcome records are joined AFTER all decisions.
"""
from copy import deepcopy
import gzip
import hashlib
import importlib.util
import json
import lzma
from pathlib import Path
import random
import sys
from fractions import Fraction as F
from full_support import solve_full_table, verify_certificate
from terminal_utility import build_table
from selector import WholePlanSelector
from weighted_selector import make_selector
import score_endgame as score


def digest(b):return hashlib.sha256(b).hexdigest()
def encoded(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def run(root, original_path, output):
    root,output=Path(root),Path(output);output.mkdir(parents=True,exist_ok=True)
    spec=importlib.util.spec_from_file_location('cash_tie_original',original_path)
    original=importlib.util.module_from_spec(spec);spec.loader.exec_module(original)
    saved=json.loads((root/'evidence/reached-first.json').read_bytes())
    inputs=json.loads(lzma.decompress((root/'inputs/development-records.json.xz').read_bytes()))
    decisions=[]
    for record in saved['records']:
        data=json.loads(inputs[record['record']]);frame=data['final_day'][-1]
        obs,cfg=deepcopy(frame['observation']),deepcopy(frame['configuration']);cfg.pop('seed',None)
        # Pass no other frame/record fields across the runtime boundary.
        base=deepcopy(frame['actions'][obs['player']]);packet=record['packet'];doc=packet['document']
        assert digest(json.dumps({'observation':obs,'configuration':cfg},separators=(',', ':'),ensure_ascii=True,allow_nan=False).encode('ascii'))==record['input_sha256']
        assert base==record['original_action'] and packet['complete'] is True
        before=original.solve_absolute(doc,build_table,solve_full_table,verify_certificate)
        default=score.solve_absolute(doc,build_table,solve_full_table,verify_certificate)
        assert before==default,record['record']
        chosen=score.make_score_selector(WholePlanSelector,make_selector,build_table,
                 solve_full_table,verify_certificate,rng=random.Random(71),tie_break='cash_pareto')
        valid={digest(encoded(p['action'])) for p in packet['plans']}
        action=chosen.transform_terminal(obs,cfg,base,document=doc,
                                         feasible=lambda a:digest(encoded(a)) in valid)
        selected_id=chosen.active['plan']['id'] if chosen.active else doc['baseline']
        assert any(p['id']==selected_id and p['action']==action for p in packet['plans'])
        objective=chosen.last_objective
        if objective and objective.get('selection_reason')=='cash_pareto_tie':
            deltas=[F(x) for x in objective['cash_margin_change_by_scenario']]
            assert min(deltas)>=0 and max(deltas)>0
            assert objective['value']==default['value']
        decisions.append({'record':record['record'],'input_sha256':record['input_sha256'],
            'selected_id':selected_id,'action':action,'action_changed':action!=base,
            'objective':objective,'default_unchanged':True,'draws':chosen.draws,
            'provider_calls':chosen.provider_calls})
    # This materialized selection contains no recorded-rival receipt or score.
    decision_bytes=encoded(decisions)+b'\n'
    (output/'decisions.json').write_bytes(decision_bytes)
    # Outcome data is first read AFTER every runtime action above is frozen.
    historical=json.loads((root/'evidence/family-diagnostic.json').read_bytes())
    lookup={r['record']:r for r in historical['records']};results=[]
    for decision in decisions:
        record=lookup[decision['record']]
        rows={r['plan']:r for r in record['plans']}
        baseline=rows['baseline'];selected=rows[decision['selected_id']]
        results.append({'record':decision['record'],'selected_id':decision['selected_id'],
            'action_changed':decision['action_changed'],'baseline':baseline,'selected':selected,
            'point_change':selected['points']-baseline['points'],
            'own_cash_change':selected['own_cash']-baseline['own_cash'],
            'rival_cash_change':selected['rival_cash']-baseline['rival_cash'],
            'margin_change':selected['margin']-baseline['margin']})
    outcome=lambda field: {k:sum(r[field]['points']==v for r in results) for k,v in [('W',1),('T',.5),('L',0)]}
    summary={'source_records':len(results),'default_result_exact_matches':len(decisions),
       'changed_actions':sum(r['action_changed'] for r in results),
       'recorded_counterfactual_baseline':outcome('baseline'),
       'recorded_counterfactual_selected':outcome('selected'),
       'improved_points':sum(r['point_change']>0 for r in results),
       'worsened_points':sum(r['point_change']<0 for r in results),
       'new_engine_calls':0,'new_game_calls':0,'new_scenarios':0,
       'scope':'Frozen runtime rule applied to old development matrices; original native counterfactual receipts reused after selection. Not independent new games or out-of-sample validation.'}
    report={'schema':'titan.cash-tie.retained.v1','summary':summary,'decisions_sha256':digest(decision_bytes),
       'runtime_sha256':digest(Path(score.__file__).read_bytes()),
       'original_runtime_sha256':digest(Path(original_path).read_bytes()),
       'input_hashes':{str(p.relative_to(root)):digest(p.read_bytes()) for p in [root/'evidence/reached-first.json',root/'evidence/family-diagnostic.json',root/'inputs/development-records.json.xz']},
       'results':results}
    (output/'evaluation.json').write_bytes(encoded(report)+b'\n')
    return report


if __name__=='__main__':
    result=run(sys.argv[1],sys.argv[2],sys.argv[3]);print(json.dumps(result['summary'],indent=2))
    print(json.dumps([r for r in result['results'] if r['action_changed']],indent=2))
