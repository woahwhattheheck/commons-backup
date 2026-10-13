# SPDX-License-Identifier: MIT
"""Offline explicit-WOOL experiment over previously reconciled public histories.

No inference, controller, game runner, outcome join, or new policy is added.
Read only saved prior-flow records and their matching public/own runtime inputs.
Use the existing JOINT, POLY, PORT, LARCH, PRISM and native-engine consumers.
"""
from __future__ import annotations
from collections import Counter
from copy import deepcopy
import argparse
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import sys
import time

SETTINGS = {
    'unobserved_products': ['WOOL'],
    'wool_units': [0, 25, 50],
    'operating_lots': [{'WHEAT': 0, 'FERTILIZER': 0}, {'WHEAT': 5, 'FERTILIZER': 5}],
    'slot_templates': ['canonical-with-gap', 'reverse'],
    'objectives': ['baseline', 'cash_pareto'],
    'max_scenarios': 32,
    'max_cells': 256,
    'meaning': 'Finite explicit current-stock/slot hypotheses, not recovered floor sales, calibrated probabilities, or exhaustive support.',
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def restore_history(saved, flow, now, period):
    """Use already-reconciled intervals; do not repeat native history inference."""
    history = flow.FlowHistory(period=period)
    seen = set()
    keys = ('step', 'product', 'lower', 'upper', 'admitted_lower', 'admitted_upper', 'reason')
    for row in sorted(saved['training'], key=lambda r: r['step']):
        step = row['step']
        if step in seen or step >= now:
            raise ValueError('History requires distinct completed prior steps')
        seen.add(step)
        for product, value in row.get('intervals', {}).items():
            if not all(key in value for key in keys):
                continue  # Missing/unidentified inputs are not zero intervals.
            if value['step'] != step or value['product'] != product:
                raise ValueError('Saved interval identity mismatch')
            history.add(flow.FlowInterval(**{key: value[key] for key in keys}))
    return history


def arguments(products):
    templates = [
        {'id': 'canonical-with-gap', 'origin': 'existing fixed engine-product ordering hypothesis, not inferred',
         'slots': [None, *products]},
        {'id': 'reverse', 'origin': 'existing fixed reverse product ordering hypothesis, not inferred',
         'slots': list(reversed(products))},
    ]
    lots = []
    for wool in SETTINGS['wool_units']:
        for i, operating in enumerate(SETTINGS['operating_lots']):
            lots.append({'id': f'wool-{wool}-operating-{i}',
                         'origin': 'predeclared explicit unknown current stock; not a measured censored sale',
                         'stock': {**operating, 'WOOL': wool}})
    return {'slot_templates': templates, 'unobserved_products': ['WOOL'],
            'unobserved_lots': lots, 'max_scenarios': SETTINGS['max_scenarios']}


def selected_action(deps, ti, obs, cfg, action, packet, tie):
    selector = deps.score.make_score_selector(deps.selector.WholePlanSelector,
        deps.weighted.make_selector, deps.terminal.build_table, deps.core.solve_full_table,
        deps.core.verify_certificate, rng=random.Random(5307), tie_break=tie)
    valid = {ti.fingerprint(p['action']) for p in packet['plans']} if packet['complete'] else set()
    result = selector.transform_terminal(obs, cfg, action, document=packet['document'],
                                        feasible=lambda value: ti.fingerprint(value) in valid)
    return result, deepcopy(selector.last_objective)


def evaluate_saved(saved, payload, raw, compressed, deps, cases, ti, flow, joint):
    if sha(raw) != saved['input_decoded_sha256'] or sha(compressed) != saved['input_compressed_sha256']:
        raise ValueError('Saved inference and public input have different identities')
    if payload.get('schema') != 'titan.public-own-history.v1':
        raise ValueError('Public-own runtime payload required, not an offline outcome index')
    cfg, obs, action = payload['configuration'], payload['observation'], payload['selected_action']
    if cfg.get('seed') is not None or action != saved['original_action']:
        raise ValueError('Seed-free matching supplied action required')
    now = obs['step']
    if now != cfg['episodeSteps'] - 2:
        raise ValueError('Final actionable boundary required')
    history = restore_history(saved, flow, now, cfg['turnsPerDay'])
    start = time.perf_counter()
    family = joint.build_joint_terminal_scenarios(history, deps.engine.PRODUCTS, now,
        capacity=cfg['shedCapacity'], max_orders=cfg['maxMarketOrdersPerTurn'],
        **arguments(deps.engine.PRODUCTS))
    family_s = time.perf_counter() - start
    out = {'input_sha256': sha(raw), 'old_family_status': saved['family']['status'],
           'family': family, 'original_action': deepcopy(action), 'by_objective': {},
           'counts': {'unit_captures': 0, 'native_market_cells': 0, 'score_calls': 0,
                      'native_selected_checks': 0, 'history_inference_calls': 0,
                      'production_controller_calls': 0, 'full_games': 0, 'new_game_seeds': 0},
           'timing_s': {'family': family_s}, 'recorded_rival_outcome_used': False}
    if not family['ready']:
        out['fallback_action'] = deepcopy(action)
        return out
    post = cases.own_unit_snapshot(deps.engine, obs, cfg, action)
    out['counts']['unit_captures'] = 1
    start = time.perf_counter()
    packet = ti.build_terminal_inputs(deps.engine, obs, cfg, action,
        post_unit_observation=post, scenarios=family['scenarios'], max_cells=SETTINGS['max_cells'])
    out['timing_s']['producer'] = time.perf_counter() - start
    out['counts']['native_market_cells'] = packet['native_market_calls']
    out['packet'] = packet
    for tie in SETTINGS['objectives']:
        start = time.perf_counter()
        chosen, objective = selected_action(deps, ti, obs, cfg, action, packet, tie)
        out['timing_s']['score_' + tie] = time.perf_counter() - start
        out['counts']['score_calls'] += 1
        out['by_objective'][tie] = {'action': chosen, 'changed': chosen != action, 'objective': objective}
    # Check each distinct selected action against EVERY included hypothesis.
    # These are conditional native references, not the recorded current rival.
    scenarios = {r['id']: r for r in packet['scenarios']}
    checked = set()
    for choice in out['by_objective'].values():
        chosen = choice['action']; key = ti.fingerprint(chosen)
        if key in checked or not packet['complete']:
            continue
        checked.add(key)
        expected = [r for r in packet['document']['receipts'] if ti.fingerprint(r['own_action']) == key]
        if len(expected) != len(scenarios):
            raise AssertionError('Selected action has no complete retained receipt row')
        for receipt in expected:
            state, env = cases.make_state(obs, cfg, chosen, scenarios[receipt['scenario']])
            deps.engine.interpreter(state, env)
            pair = [state[obs['player']].reward, state[1-obs['player']].reward]
            if pair != [receipt['own_cash'], receipt['rival_cash']]:
                raise AssertionError('Selected full native transition differs from table')
            out['counts']['native_selected_checks'] += 1
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--saved-reports', required=True, type=Path)
    parser.add_argument('--runtime-dir', required=True, type=Path)
    parser.add_argument('--poly-package', required=True, type=Path)
    parser.add_argument('--joint', required=True, type=Path)
    parser.add_argument('--flow', required=True, type=Path)
    parser.add_argument('--score', required=True, type=Path)
    parser.add_argument('--freeze', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    freeze = json.loads(args.freeze.read_text())
    if freeze['settings'] != SETTINGS:
        raise ValueError('Experiment settings differ from the retained freeze')
    source_files = {'experiment': Path(__file__), 'joint': args.joint, 'flow': args.flow, 'score': args.score}
    hashes = {name: sha(path.read_bytes()) for name, path in source_files.items()}
    if hashes != freeze['source_sha256']:
        raise ValueError('Experiment sources differ from the retained freeze')
    sys.path.insert(0, str(args.poly_package/'source'))
    ti = load(args.poly_package/'source/terminal_inputs.py', 'terminal_inputs')
    cases = load(args.poly_package/'source/terminal_input_cases.py', '_wool_native_cases')
    deps = cases.dependencies(args.poly_package/'dependencies/engine_loader.py', args.poly_package/'engine',
        args.poly_package/'dependencies', args.poly_package/'dependencies/full_support.py')
    deps.score = load(args.score, '_wool_score')
    flow = load(args.flow, '_wool_flow')
    joint = load(args.joint, '_wool_joint')
    saved_doc = json.loads(args.saved_reports.read_text())
    if sha(args.saved_reports.read_bytes()) != freeze['saved_reports_sha256']:
        raise ValueError('Saved-history checkpoint differs from freeze')
    reports = []
    for saved in saved_doc['reports']:
        path = args.runtime_dir/(saved['input_decoded_sha256'] + '.json.gz')
        compressed = path.read_bytes(); raw = gzip.decompress(compressed)
        reports.append(evaluate_saved(saved, json.loads(raw), raw, compressed, deps, cases, ti, flow, joint))
    totals = Counter()
    for report in reports: totals.update(report['counts'])
    summary = {'retained_payloads': len(reports), 'old_ready': sum(r['old_family_status'] == 'ready' for r in reports),
        'new_ready': sum(r['family']['ready'] for r in reports),
        'statuses': dict(Counter(r['family']['status'] for r in reports)),
        'changed_by_tie': {tie: sum(r['by_objective'].get(tie, {}).get('changed', False) for r in reports)
                           for tie in SETTINGS['objectives']}, 'counts': dict(totals),
        'meaning': 'Existing development inputs under explicit finite hypotheses. No actual current rival outcomes or policy-strength claims.'}
    args.output.write_text(json.dumps({'summary': summary, 'freeze': freeze, 'reports': reports}, indent=2, allow_nan=False)+'\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
