# SPDX-License-Identifier: Apache-2.0
"""Stress frozen terminal choices without inference, optimization or outcomes.

This is an offline consumer of an existing JH result and its exact public-own
payload. It compares that same chosen queue to its original under the already
published current-snapshot family. It creates no replacement policy or release.
"""
from copy import deepcopy
from fractions import Fraction
import argparse
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

import terminal_inputs as ti
import terminal_input_cases as cases
from interior_liquidation import interior_liquidation_scenarios


def sha(data):
    return hashlib.sha256(data).hexdigest()


def _margin(receipt):
    return Fraction(str(receipt['own_cash'])) - Fraction(str(receipt['rival_cash']))


def compare_frozen(engine, report, raw_payload):
    """Bind the prior result before native work; retain separate family labels."""
    if sha(raw_payload) != report['input_sha256']:
        raise ValueError('Frozen choice and runtime payload identities differ')
    payload = json.loads(raw_payload)
    if payload.get('schema') != 'titan.public-own-history.v1':
        raise ValueError('Expected an existing public-own runtime payload')
    cfg, obs = deepcopy(payload['configuration']), deepcopy(payload['observation'])
    base = deepcopy(payload['selected_action'])
    packet = report['packet']
    if cfg.get('seed') is not None or obs['step'] != cfg['episodeSteps'] - 2:
        raise ValueError('Expected seed-free final-action input')
    if base != report['original_action'] or base != packet['fallback_action']:
        raise ValueError('Frozen original action differs from input')
    if report.get('recorded_rival_outcome_used') is not False:
        raise ValueError('This consumer requires the outcome-free JH experiment')
    if packet.get('complete') is not True or report['family'].get('ready') is not True:
        raise ValueError('Incomplete prior family is not a frozen supported choice')
    choice = deepcopy(report['choices']['cash_pareto']['action'])
    if {k:v for k,v in choice.items() if k!='market'} != {k:v for k,v in base.items() if k!='market'}:
        raise ValueError('Frozen choice changes the selected own-unit stage')
    plans = packet['plans']
    ids = [p['id'] for p in plans]
    if len(set(ids)) != len(ids) or packet['document']['baseline'] != 'baseline':
        raise ValueError('Ambiguous original plan identities')
    original_ids = [p['id'] for p in plans if p['action'] == base]
    selected_ids = [p['id'] for p in plans if p['action'] == choice]
    if original_ids != ['baseline'] or len(selected_ids) != 1:
        raise ValueError('Frozen selected action is not one original complete plan')
    selected_id = selected_ids[0]
    if packet['source']['selected_action_sha256'] != ti.fingerprint(base):
        raise ValueError('Frozen selected-action binding differs')
    # This is a native boundary capture, not another producer/controller call.
    post = cases.own_unit_snapshot(engine, obs, cfg, base)
    cfg, player, step, farms, private, bound = ti._current(obs, cfg, post)
    state_hash = ti.fingerprint(bound)
    if state_hash != packet['source']['observation_and_post_units_sha256']:
        raise ValueError('Current selected-unit state differs from frozen receipts')
    expected_plans = ti.sale_plans(engine, base, private, obs['market'], cfg, max_plans=len(plans))
    if expected_plans != plans:
        raise ValueError('Frozen plan family differs from its original physical inputs')
    old_scenarios = {s['id']:s for s in packet['scenarios']}
    old_cells = {}
    for cell in packet['document']['receipts']:
        if cell['plan'] not in ('baseline', selected_id):
            continue
        scenario = old_scenarios.get(cell['scenario'])
        if scenario is None or cell.get('done') is not True:
            raise ValueError('Prior selected-row receipt is incomplete')
        action = base if cell['plan']=='baseline' else choice
        if (cell['own_action'] != action or cell['plan_sha256'] != ti.fingerprint(action)
                or cell['scenario_sha256'] != ti.fingerprint(scenario)
                or cell['public_state_sha256'] != state_hash):
            raise ValueError('Prior receipt binding differs')
        key=(cell['plan'], cell['scenario'])
        if key in old_cells:
            raise ValueError('Duplicate prior selected-row receipt')
        old_cells[key]=cell
    if len(old_cells) != len(set(('baseline',selected_id))) * len(old_scenarios):
        raise ValueError('Prior selected rows are not complete')
    prior_deltas=[_margin(old_cells[selected_id,s])-_margin(old_cells['baseline',s]) for s in old_scenarios]
    family=interior_liquidation_scenarios(engine,obs,cfg)
    output=[]; native=0; reused=0
    lookup={ti.fingerprint((s['shed'],s['market'])):s['id'] for s in old_scenarios.values()}
    for scenario in family:
        prior_id=lookup.get(ti.fingerprint((scenario['shed'],scenario['market'])))
        receipts={}
        for identity,action in [('baseline',base),(selected_id,choice)]:
            if identity in receipts:
                continue
            if prior_id is not None:
                receipt=deepcopy(old_cells[identity,prior_id]);reused+=1
                pair={k:receipt[k] for k in ('own_cash','rival_cash')}
            else:
                receipt=ti.market_cell(engine,farms,private,obs['market'],cfg,player,action,scenario)
                native+=1
                pair={k:receipt[k] for k in ('own_cash','rival_cash')}
            receipts[identity]=pair
        baseline, candidate=receipts['baseline'],receipts[selected_id]
        delta=_margin(candidate)-_margin(baseline)
        output.append({'scenario':deepcopy(scenario),'baseline':baseline,'candidate':candidate,
                       'margin_change':str(delta),'reused_prior_scenario_id':prior_id})
    deltas=[Fraction(row['margin_change']) for row in output]
    return {'input_sha256':report['input_sha256'],'selected_plan_id':selected_id,'choice_changed':choice!=base,
            'original_action':base,'frozen_action':choice,'state_sha256':state_hash,
            'prior_minimum_margin_change':str(min(prior_deltas)),
            'prior_maximum_margin_change':str(max(prior_deltas)),
            'expanded_minimum_margin_change':str(min(deltas)),
            'expanded_maximum_margin_change':str(max(deltas)),
            'expanded_cash_dominating':all(d>=0 for d in deltas) and any(d>0 for d in deltas),
            'expanded_negative_columns':sum(d<0 for d in deltas),
            'rows':output,'native_market_calls':native,'reused_receipt_cells':reused,
            'unit_boundary_captures':1,'optimization_calls':0,'history_inference_calls':0,
            'actual_rival_outcome_used':False,'new_games':0}


def run(engine, reports, payload_zip):
    output=[]
    with zipfile.ZipFile(payload_zip) as archive:
        for report in reports['reports']:
            # Read ONLY the hash-named runtime member, not the outcome/index file.
            key=report['input_sha256']
            if len(key)!=64 or any(c not in '0123456789abcdef' for c in key):
                raise ValueError('Invalid runtime payload identity')
            raw=gzip.decompress(archive.read('runtime/'+key+'.json.gz'))
            output.append(compare_frozen(engine,report,raw))
    changed=[r for r in output if r['choice_changed']]
    return {'schema':'titan.frozen-terminal-cross-family.v1',
            'summary':{'records':len(output),'previously_changed_actions':len(changed),
                       'changed_actions_still_cash_dominating':sum(r['expanded_cash_dominating'] for r in changed),
                       'changed_actions_with_negative_columns':sum(r['expanded_negative_columns']>0 for r in changed),
                       'native_market_calls':sum(r['native_market_calls'] for r in output),
                       'reused_receipt_cells':sum(r['reused_receipt_cells'] for r in output),
                       'unit_boundary_captures':len(output),'optimization_calls':0,'history_inference_calls':0,
                       'new_games':0,'recorded_rival_outcome_lookups':0},
            'records':output,'scope':'Frozen conditional actions under a second finite assumption family; no outcome or promotion claim.'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reports',type=Path,required=True);p.add_argument('--payload-zip',type=Path,required=True)
    p.add_argument('--loader',type=Path,required=True);p.add_argument('--engine-dir',type=Path,required=True)
    p.add_argument('--freeze',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();freeze=json.loads(a.freeze.read_bytes())
    actual={'runner':sha(Path(__file__).read_bytes()),'reports':sha(a.reports.read_bytes()),
            'payload_zip':sha(a.payload_zip.read_bytes()),'family':sha(Path(__file__).with_name('interior_liquidation.py').read_bytes())}
    if actual!=freeze['inputs']:
        raise ValueError('Inputs/source differ from pre-execution freeze')
    spec=importlib.util.spec_from_file_location('_poly_cross_engine_loader',a.loader)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    engine,hashes=module.get_engine(a.engine_dir)
    result=run(engine,json.loads(a.reports.read_bytes()),a.payload_zip)
    result['source']={'freeze':freeze,'engine_hashes':hashes}
    with a.output.open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps(result['summary'],indent=2))


if __name__=='__main__':main()
