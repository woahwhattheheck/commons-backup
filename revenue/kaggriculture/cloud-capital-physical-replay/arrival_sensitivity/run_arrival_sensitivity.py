# SPDX-License-Identifier: Apache-2.0
"""Measure buyer-time sensitivity through the existing complete-actor tail executor.

This is an offline conditional experiment, not a new simulator, actor, probability
model or policy. Only the explicitly supplied first-visible YARN time changes.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import asdict
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import random
import sys
import time

PACKAGE_SHA256 = '6f0b1db42c16ded162c748911167e97e9cbdcc16317d5b4f843e0b7d18e9b16e'
ROUTES = ('7015cc00acfa4922', 'dc76e4003029ac51')
CHECKPOINT = 226
ACTOR_SEED = 20260907
ASSUMPTIONS = (
    'One explicitly hypothetical YARN_STORE addition, all other future shop '
    'draws unspecified/held absent as in the original two-scenario sensitivity. '
    'No external rival flow; rival public farms frozen by the existing own-state '
    'oracle. This is not a complete random-game path, posterior probability, '
    'responsive-opponent result, win utility or deployable one-second decision.'
)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def identity(path):
    raw = Path(path).read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
            'git_blob': hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()}


def load(path, name):
    """Execute the already-verified experiment source, without bytecode caches."""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None:
        raise ImportError(str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    exec(compile(Path(path).read_bytes(), str(path), 'exec'), module.__dict__)
    return module


def write_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_bytes(encoded(value) + b'\n')
    temporary.replace(path)


def arrival_times(observation, configuration, capacity=8):
    """Scheduled future slots only; no draw weights or identities are inferred."""
    period = int(configuration.get('turnsPerDay', 24))
    unlock = int(configuration.get('townShopUnlockInterval', 3))
    terminal = int(configuration.get('episodeSteps', 720)) - 2
    if period <= 0 or unlock <= 0:
        raise ValueError('Positive day and shop-unlock periods are required')
    remaining = max(0, capacity - len(observation['town']['unlocked_shops']))
    step = int(observation['step'])
    result = []
    for visible in range((step // period + 1) * period, terminal + 1, period):
        if (visible // period) % unlock == 0:
            if len(result) == remaining:
                break
            result.append(visible)
    return result


def case_cash(case):
    if case.get('status') != 'complete':
        return None
    cash = case.get('final_cash')
    if not isinstance(cash, (int, float)) or isinstance(cash, bool):
        raise ValueError('Completed case is missing numeric terminal cash')
    return cash


def comparison(rows, visible):
    values = {row['offered_route']: row for row in rows}
    if set(values) != set(ROUTES) or len(rows) != 2:
        raise ValueError('Each comparison requires exactly one row per route')
    left, right = [case_cash(values[route]) for route in ROUTES]
    complete = left is not None and right is not None
    return {'first_visible_step': visible, 'complete': complete, 'main_cash': left,
            'sheep_cash': right, 'sheep_minus_main': right - left if complete else None,
            'rival_cash': None, 'win_utility': None}


def prepare(package):
    root = Path(package).resolve()
    manifest = json.loads((root / 'SHA256-MANIFEST.json').read_text())
    for name, expected in manifest.items():
        path = (root / name).resolve()
        if not path.is_relative_to(root):
            raise ValueError('Manifest member escapes the retained package')
        got = identity(path)
        if got['sha256'] != expected['sha256'] or got['bytes'] != expected['bytes']:
            raise ValueError('Retained package member differs: ' + name)
    # The original certificate import has already been restored in this retained
    # package's isolated original-runtime directory. Never edit its archived tree.
    runtime = root / 'original-runtime/revenue/kaggriculture'
    trace = root / 'TITAN-TRACE-DELVE-control-inputs'
    source_map = json.loads((trace / 'SOURCE-MAP.json').read_text())
    receipt = json.loads((trace / 'candidate-inputs-receipt.json').read_text())
    raw = (trace / 'candidate-inputs.jsonl.gz').read_bytes()
    decoded = gzip.decompress(raw)
    if (hashlib.sha256(raw).hexdigest() != receipt['output_file_sha256'] or
        hashlib.sha256(decoded).hexdigest() != receipt['input_jsonl_sha256'] or
        identity(trace / 'SOURCE-MAP.json')['sha256'] != receipt['source_map_sha256']):
        raise ValueError('Retained TRACE byte binding differs')
    bound = {}
    for key, record in source_map.items():
        if key.startswith('runtime/'):
            path = runtime / key.removeprefix('runtime/')
            bound[key] = identity(path)
            if bound[key]['sha256'] != record['sha256']:
                raise ValueError('Original runtime differs: ' + key)
    paths = {
        'rill': root / 'work/revenue/kaggriculture/cloud-capital-physical-replay/reached_integrated.py',
        'replay': root / 'TITAN-KESTREL-replay-deadline-PR10113/physical_replay.py',
        'oracle': root / 'titan-joint-sell-tail-value-evidence-20260907/dependencies/oracle.py',
        'whole_actor_view': root / 'titan-joint-sell-tail-value-evidence-20260907/source/sell_tail_value.py',
        'evaluator': root / 'TITAN-DELVE-funded-seed-evidence/source/tree/revenue/kaggriculture/cloud-eval/evaluate.py',
    }
    original = json.loads((root / 'work/reached-final.json').read_text())
    if original['validation']['runtime_closure'] != bound:
        raise ValueError('Saved baseline uses different runtime source')
    pins = {name: identity(path) for name, path in paths.items()}
    for name in ('replay', 'oracle', 'whole_actor_view'):
        if pins[name] != original['validation']['source_pins'][name]:
            raise ValueError('Saved baseline uses a different ' + name)
    modules = {name: load(path, 'arrival_' + name) for name, path in paths.items()}
    engine_dir = root / 'TITAN-DELVE-funded-seed-evidence/engine/engine'
    engine, engine_hashes = modules['evaluator'].get_engine(engine_dir, prepare=False)
    if engine_hashes != receipt['engine_sha256']:
        raise ValueError('Original engine differs')
    sys.path[:0] = [str(runtime / 'cloud-integration-differentials'),
                    str(runtime / 'cloud-execution-lab')]
    factory = load(runtime / 'cloud-integration-differentials/funded_main.py', 'arrival_original_factory')
    random.seed(ACTOR_SEED)
    actor = factory.make_agent(funded=False)
    rows = [json.loads(line) for line in decoded.splitlines()]
    row, restoration = modules['rill'].restore_prefix(actor, rows)
    if (row != original['validation']['input_row'] or
        restoration != original['validation']['restoration'] or
        actor.controller.cur != ROUTES[0]):
        raise ValueError('Original checkpoint or action prefix differs')
    for case in original['replay']['cases']:
        if case['program_sha256'] != digest(actor.controller.R[case['offered_route']]):
            raise ValueError('Saved route program differs')
    evidence = {'retained_package_sha256': PACKAGE_SHA256,
                'manifest_members_verified': len(manifest),
                'runtime_closure': bound, 'source_pins': pins,
                'engine_sha256': engine_hashes,
                'saved_report': identity(root / 'work/reached-final.json'),
                'input_sha256': digest(row), 'restoration': restoration,
                'configuration': row['configuration'],
                'observation_sha256': digest(row['observation']),
                'source_environment_seed_provenance_only': 9965001,
                'origin': 'retained DELVE9965001/p0 funding OFF, SELL ON at226'}
    return actor, row, original, modules, engine, evidence


def run(args):
    if os.environ.get('PYTHONHASHSEED') != str(ACTOR_SEED):
        raise ValueError('Use PYTHONHASHSEED=20260907 in this fresh process')
    if args.seconds <= 0 or not __import__('math').isfinite(args.seconds):
        raise ValueError('Positive finite per-case cooperative budget required')
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError('Use a new empty output directory; prior attempts stay intact')
    output.mkdir(parents=True, exist_ok=True)
    actor, row, original, modules, engine, evidence = prepare(args.package)
    rill, replay, oracle, tail = [modules[name] for name in ('rill', 'replay', 'oracle', 'whole_actor_view')]
    obs, cfg = row['observation'], row['configuration']
    times = arrival_times(obs, cfg, engine.MAX_SHOP_INSTANCES)
    requested = list(args.visible_steps) if args.visible_steps else times[1:]
    if len(set(requested)) != len(requested) or any(t not in times[1:] for t in requested):
        raise ValueError('Run only distinct later available unlock slots;288 already has saved evidence')
    for key in ('matched_actions', 'through_step'):
        print('RESTORED', key, evidence['restoration'][key], flush=True)
    original_state = rill.state_digest(actor)
    original_obs = digest(obs)
    baseline = original['replay']['cases']
    reused = [comparison([c for c in baseline if c['scenario_id'] == label], visible)
              for label, visible in [('observed_shops_continue_no_rival', None),
                                     ('hypothetical_yarn_288_no_rival', 288)]]
    report = {'schema': 'titan.arrival-sensitivity.v1', 'complete': False,
              'assumptions': ASSUMPTIONS, 'validation': evidence,
              'driver': identity(__file__), 'available_slots': times,
              'requested_slots': requested, 'source_fixed_before_tails': True,
              'reused_comparisons': reused, 'comparisons': [], 'cases': [],
              'new_full_games': 0, 'game_seeds_initialized': [],
              'new_model_decisions': 0, 'new_tail_seconds': 0,
              'selection': None, 'estimated_arrival_probabilities': None}
    write_json(output / 'experiment.json', report)
    facade = tail.SellRouteView(actor, cfg)
    def fork(view):
        return tail.SellRouteView(rill.fork_integrated(view.scheduler), view.configuration)
    for visible in requested:
        name = 'hypothetical_yarn_' + str(visible) + '_no_rival'
        scenario = oracle.Scenario(new_shops={visible - 1: ('YARN_STORE',)},
                                   label=f'Hypothetical single YARN first visible at{visible}; other draws/rival flow absent')
        pair = []
        for route in ROUTES:
            started = time.perf_counter()
            one = replay.replay_routes(
                facade, (route,), obs, cfg, engine, oracle.simulate_bundle,
                scenarios={name: scenario}, end_step=int(cfg['episodeSteps']) - 2,
                fork_controller=fork,
                limits=replay.ReplayLimits(seconds=args.seconds, decisions=493))
            case = one['cases'][0]
            leaf = f'yarn-{visible}-{route}.json.gz'
            payload = encoded({'replay': one, 'scenario': asdict(scenario),
                               'source': report['driver'], 'validation': evidence,
                               'assumptions': ASSUMPTIONS})
            (output / leaf).write_bytes(gzip.compress(payload, mtime=0))
            record = {'offered_route': route, 'scenario_id': name, 'status': case['status'],
                      'final_cash': case.get('final_cash'), 'file': leaf,
                      'sha256': identity(output / leaf)['sha256'],
                      'decoded_sha256': hashlib.sha256(payload).hexdigest(),
                      'new_model_decisions': one['decisions_executed'],
                      'tail_seconds': one['wall_seconds'],
                      'action_sha256': case.get('action_sha256'),
                      'call_wall_seconds': time.perf_counter() - started}
            pair.append(record)
            report['cases'].append(record)
            report['new_model_decisions'] += one['decisions_executed']
            report['new_tail_seconds'] += one['wall_seconds']
            if rill.state_digest(actor) != original_state or digest(obs) != original_obs:
                raise AssertionError('Original actor or observation was mutated')
            report['original_actor_unchanged'] = True
            report['input_unchanged'] = True
            write_json(output / 'experiment.json', report)
            print('CASE', json.dumps(record, sort_keys=True), flush=True)
        report['comparisons'].append(comparison(pair, visible))
        write_json(output / 'experiment.json', report)
        print('PAIR', json.dumps(report['comparisons'][-1], sort_keys=True), flush=True)
    report['complete'] = all(x['complete'] for x in report['comparisons']) and len(report['comparisons']) == len(requested)
    write_json(output / 'experiment.json', report)
    return 0 if report['complete'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--visible-steps', nargs='+', type=int)
    parser.add_argument('--seconds', type=float, default=45.0)
    return run(parser.parse_args())


if __name__ == '__main__':
    raise SystemExit(main())
