# SPDX-License-Identifier: Apache-2.0
"""Two-stage saved-development comparison; select before opening evaluation data.

The select stage uses old native receipts without executing them again. Only
new columns invoke the existing terminal producer. The evaluate stage is a
separate CLI invocation and joins already-written actions to recorded rival
outcomes. No actor or full game is run. Detailed output belongs in private
project storage, never a public source or policy input.
"""
from copy import deepcopy
import argparse
import hashlib
import json
import lzma
from pathlib import Path
import time

import terminal_input_cases as cases
import terminal_inputs as ti
from interior_liquidation import interior_liquidation_scenarios


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_records(archive):
    raw = json.loads(lzma.decompress(Path(archive).read_bytes()))
    return {key: json.loads(value) for key, value in raw.items() if key.startswith('dev/')}


def extend_packet(saved, extra):
    """Join same-state new columns; never present partial results as complete."""
    if saved['plans'] != extra['plans']:
        raise ValueError('Original candidate plans changed; this is not a column-only comparison')
    if saved['source']['observation_and_post_units_sha256'] != extra['source']['observation_and_post_units_sha256']:
        raise ValueError('New native columns do not bind the original state')
    result = deepcopy(saved)
    old_ids = {r['id'] for r in saved['scenarios']}
    if any(r['id'] in old_ids for r in extra['scenarios']):
        raise ValueError('Repeated scenario ID across old and new receipts')
    result['scenarios'] += deepcopy(extra['scenarios'])
    by_cell = {(r['plan'],r['scenario']): r for r in saved['document']['receipts'] + extra['document']['receipts']}
    doc = result['document']
    doc['scenario_ids'] = [s['id'] for s in result['scenarios']]
    doc['receipts'] = [deepcopy(by_cell[p,s]) for p in doc['plan_ids'] for s in doc['scenario_ids']]
    complete = saved['complete'] and extra['complete']
    result.update(complete=complete, status='complete' if complete else extra['status'],
                  native_market_calls=extra['native_market_calls'],
                  required_cells=len(doc['receipts']), reused_market_cells=len(saved['document']['receipts']))
    doc['source']['hypothesis_family'] = 'predeclared-original-plus-interior-terminal-stress'
    result['source'] = deepcopy(doc['source'])
    return result


def select(deps, archive, saved_report):
    records = load_records(archive)
    saved = json.loads(Path(saved_report).read_bytes())
    rows=[]; new_cells=0; reused_cells=0; calls=0
    for old in saved['records']:
        record=records[old['record']]
        frame=record['final_day'][-1]
        obs,cfg,action=deepcopy(frame['observation']),deepcopy(frame['configuration']),deepcopy(old['original_action'])
        cfg.pop('seed',None)
        family=interior_liquidation_scenarios(deps.engine,obs,cfg)
        if family[:len(old['packet']['scenarios'])] != old['packet']['scenarios']:
            raise ValueError('Old stress-family identity changed')
        post=cases.own_unit_snapshot(deps.engine,obs,cfg,action)
        extras=family[len(old['packet']['scenarios']):]
        started=time.perf_counter()
        extra=ti.build_terminal_inputs(deps.engine,obs,cfg,action,post_unit_observation=post,scenarios=extras)
        packet=extend_packet(old['packet'],extra)
        old_out,old_actor=cases.choose(deps,obs,cfg,action,old['packet'])
        if old_out != old['output_action']:
            raise ValueError('Current default consumer differs on unchanged old receipts')
        out,actor=cases.choose(deps,obs,cfg,action,packet)
        elapsed=time.perf_counter()-started
        new_cells+=extra['native_market_calls'];reused_cells+=len(old['packet']['document']['receipts']);calls+=2
        rows.append({'record':old['record'],'player':obs['player'],
                     'input_sha256':ti.fingerprint({'observation':obs,'configuration':cfg,'action':action}),
                     'original_action':action,'old_output':old_out,'output':out,
                     'changed':out!=old_out,'objective':actor.last_objective,
                     'old_objective':old_actor.last_objective,'decision':actor.last_decision,
                     'draws':actor.draws,'packet':packet,'elapsed_seconds':elapsed})
    return {'schema':'titan.interior-liquidation.decisions.v1',
            'stage':'selection_only','source':{'generator_sha256':sha(Path(__file__).with_name('interior_liquidation.py')),
                'runner_sha256':sha(__file__),'archive_sha256':sha(archive),'saved_report_sha256':sha(saved_report)},
            'summary':{'records':len(rows),'new_native_market_cells':new_cells,
                       'reused_native_market_cells':reused_cells,'own_unit_boundary_captures':len(rows),
                       'selector_calls':calls,'changed_actions':sum(r['changed'] for r in rows),
                       'new_games':0,'new_game_seeds':0},'records':rows}


def evaluate(deps, archive, decisions):
    selected=json.loads(Path(decisions).read_bytes())
    records=load_records(archive);rows=[];calls=0
    for chosen in selected['records']:
        record=records[chosen['record']];frame=record['final_day'][-1]
        obs,cfg=deepcopy(frame['observation']),deepcopy(frame['configuration']);cfg.pop('seed',None)
        original=chosen['original_action']
        if ti.fingerprint({'observation':obs,'configuration':cfg,'action':original})!=chosen['input_sha256']:
            raise ValueError('Evaluation frame differs from the frozen decision input')
        actual_other=deepcopy(frame['actions'][1-obs['player']])
        # Evaluation-only reverse of the retained successful market operations.
        other_private=cases.historical_post_units(record)
        scenario={'shed':other_private['shed'],'market':actual_other.get('market',[])}
        outcomes=[]
        for action in [original,chosen['output']]:
            state,env=cases.make_state(obs,cfg,action,scenario,rival_private=other_private)
            deps.engine.interpreter(state,env);calls+=1
            outcomes.append([state[obs['player']].reward,state[1-obs['player']].reward])
        expected=[record['scores'][obs['player']],record['scores'][1-obs['player']]]
        if outcomes[0] != expected:
            raise ValueError('Historical native baseline did not reconcile')
        rows.append({'record':chosen['record'],'changed':chosen['changed'],'cash':outcomes,
                     'points':[str(deps.terminal.win_points(*x)) for x in outcomes]})
    return {'schema':'titan.interior-liquidation.evaluation.v1','decisions_sha256':sha(decisions),
            'evaluation_only_interpreter_calls':calls,'records':rows,'new_games':0,
            'scope':'Counterfactual final transitions on already-exposed development states, not new game results.'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('stage',choices=['select','evaluate']);p.add_argument('--archive',type=Path,required=True)
    p.add_argument('--saved-report',type=Path);p.add_argument('--decisions',type=Path)
    p.add_argument('--loader',type=Path,required=True);p.add_argument('--engine-dir',type=Path,required=True)
    p.add_argument('--consumers',type=Path,required=True);p.add_argument('--score-file',type=Path,required=True)
    p.add_argument('--core-file',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();deps=cases.dependencies(a.loader,a.engine_dir,a.consumers,a.core_file)
    deps.score=cases.load(a.score_file,'_interior_score_current')
    if a.stage=='select':
        if a.saved_report is None:p.error('select requires --saved-report')
        result=select(deps,a.archive,a.saved_report)
    else:
        if a.decisions is None:p.error('evaluate requires --decisions')
        result=evaluate(deps,a.archive,a.decisions)
    with a.output.open('x',encoding='utf-8') as out:json.dump(result,out,ensure_ascii=True,separators=(',',':'));out.write('\n')
    print(json.dumps(result['summary'] if 'summary' in result else {'evaluation_only_interpreter_calls':result['evaluation_only_interpreter_calls']},indent=2))


if __name__=='__main__':main()
