# SPDX-License-Identifier: Apache-2.0
"""Evaluation-only diagnostic of an already frozen reached-state plan family.

Reads recorded rival receipts/actions only AFTER all runtime inputs, candidate
plans and outputs have been saved. This never calls the producer or selector,
changes a model, supplies an actor input, or runs a full game. Best-in-hindsight
results are explicitly oracle diagnostics, not an executable recommendation.
"""
from __future__ import annotations
from copy import deepcopy
import json
import lzma
from pathlib import Path

from terminal_input_cases import dependencies, own_unit_snapshot, historical_post_units
from terminal_inputs import market_cell, _config, fingerprint


def diagnose(deps, archive, saved_report):
    raw=json.loads(lzma.decompress(Path(archive).read_bytes()))
    frozen=json.loads(Path(saved_report).read_text())
    records=[]
    for saved in frozen['records']:
        name=saved['record']
        if not name.startswith('dev/'):
            raise ValueError('This diagnostic consumes only the saved development slice')
        original=json.loads(raw[name]);frame=original['final_day'][-1]
        obs,cfg=deepcopy(frame['observation']),deepcopy(frame['configuration']);cfg.pop('seed',None)
        if fingerprint({'observation':obs,'configuration':cfg})!=saved['input_sha256']:
            raise ValueError('Saved runtime observation binding changed')
        action=frame['actions'][obs['player']]
        if action!=saved['original_action']:
            raise ValueError('Saved selected-action boundary changed')
        post=own_unit_snapshot(deps.engine,obs,cfg,action)
        farms=deepcopy(obs['farms']);farms[obs['player']]=post['farms'][obs['player']]
        rival={'shed':historical_post_units(original)['shed'],
               'market':frame['actions'][1-obs['player']]['market']}
        baseline=saved['historical_cash'];base_margin=baseline[0]-baseline[1]
        rows=[]
        for plan in saved['packet']['plans']:
            result=market_cell(deps.engine,farms,post['private'],obs['market'],_config(cfg),
                               obs['player'],plan['action'],rival)
            own,other=result['own_cash'],result['rival_cash'];margin=own-other
            rows.append({'plan':plan['id'],'own_cash':own,'rival_cash':other,'margin':margin,
                         'points':1 if margin>0 else .5 if margin==0 else 0,
                         'margin_delta':margin-base_margin})
        if [rows[0]['own_cash'],rows[0]['rival_cash']]!=baseline:
            raise AssertionError('Recorded baseline did not reconcile')
        best=max(rows,key=lambda row:(row['points'],row['margin']))
        records.append({'record':name,'original_points':saved['historical_points'],
                        'original_margin':base_margin,'plans':rows,'oracle_best':best,
                        'oracle_points_improvement':best['points']>saved['historical_points'],
                        'oracle_margin_improvement':best['margin']>base_margin,
                        'runtime_action_changed':saved['action_changed']})
    return {'schema':'titan.terminal-inputs.oracle-diagnostic.v1','records':records,
            'summary':{'reused_development_records':len(records),
                       'native_market_calls':sum(len(r['plans']) for r in records),
                       'family_contains_better_realized_points':sum(r['oracle_points_improvement'] for r in records),
                       'family_contains_better_realized_margin':sum(r['oracle_margin_improvement'] for r in records),
                       'runtime_action_changes':sum(r['runtime_action_changed'] for r in records),
                       'full_games':0,'new_game_seeds':0},
            'scope':'Oracle best among previously saved candidate actions under the recorded final rival queue; evaluation-only, not an available runtime policy or independent game result.'}


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('loader','engine-dir','consumers','core-file','archive','saved-report','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    deps=dependencies(args.loader,args.engine_dir,args.consumers,args.core_file)
    report=diagnose(deps,args.archive,args.saved_report)
    with args.output.open('x',encoding='utf-8') as handle:json.dump(report,handle,indent=2);handle.write('\n')
    print(json.dumps(report['summary'],indent=2))


if __name__=='__main__':main()
