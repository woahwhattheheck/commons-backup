# SPDX-License-Identifier: Apache-2.0
"""Consume PRISM's saved prefix, then evaluate an explicitly declared tail grid.

The prefix is replayed through the actor only, not the engine. Future saved
opponent actions are never converted to runtime scenarios. No new games run.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import sys
from time import perf_counter

from sell_tail_value import evaluate_sell_tails

MAIN = '7015cc00acfa4922'
MILK_EXIT = 'a84d06f1d12add7c'
SCHEDULER_SHA = '32c8610c9827d1686a6f831e2c4b6af4c00d32d2aa04dcf25699d976d6d97dd9'
RILL_BLOB = '7955b2c6683420f4b580e30dca15ca8c752f5560'
ORACLE_BLOB = '49640c27862d3d132c828fbafc6a8b4957527736'


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def source(path):
    data = Path(path).read_bytes()
    return dict(sha256=hashlib.sha256(data).hexdigest(),
                git_blob=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest(),
                size=len(data))


def restore_prefix(actor, trace_path, configuration, *, seat=0, checkpoint=577):
    """Restore one actor by its original observations and check expected actions.

    The post-transition rows retain the previous step. Apply the exact existing
    evaluator's next-decision clock normalization, not inferred engine steps.
    Only player `seat`'s own observation enters the actor. No engine is called.
    """
    count = 0
    digest = hashlib.sha256()
    with gzip.open(trace_path, 'rt', encoding='utf-8') as f:
        previous = json.loads(next(f))
        if previous['step'] != -1:
            raise ValueError('Expected retained engine initialization row')
        for step in range(checkpoint):
            current = json.loads(next(f))
            if current['step'] != step:
                raise ValueError('Retained trace is not a continuous prefix')
            observation = deepcopy(previous['observations'][seat])
            observation.update(step=step, remainingOverageTime=0)
            result = actor.act(observation, configuration)
            if result != current['actions'][seat]:
                raise ValueError(f'Restored actor differs from saved action at {step}')
            digest.update(encoded({'step': step, 'observation': observation, 'action': result})+b'\n')
            count += 1
            previous = current
        observation = deepcopy(previous['observations'][seat])
        observation.update(step=checkpoint, remainingOverageTime=0)
    return observation, {'matched_prefix_actions': count, 'prefix_sha256': digest.hexdigest(),
                         'engine_calls': 0, 'checkpoint': checkpoint, 'seat': seat}


def run(args):
    root = args.source_root
    sell_dir = root/'cloud-titan-composition/vendor/sell'
    pins = {'scheduler': source(sell_dir/'scheduler.py'),
            'physical_replay': source(args.rill/'physical_replay.py'),
            'oracle': source(args.oracle),
            'evaluator': source(root/'cloud-eval/evaluate.py'),
            'loader': source(root/'20260907-offline-agent/evaluate.py')}
    if pins['scheduler']['sha256'] != SCHEDULER_SHA:
        raise ValueError('Use the retained frozen SELL source')
    if pins['physical_replay']['git_blob'] != RILL_BLOB or pins['oracle']['git_blob'] != ORACLE_BLOB:
        raise ValueError('Use the documented existing RILL/T04 source')
    sys.path.insert(0, str(sell_dir))
    scheduler = load(sell_dir/'scheduler.py', 'joint_frozen_scheduler')
    evaluator = load(root/'cloud-eval/evaluate.py', 'joint_existing_evaluator')
    oracle = load(args.oracle, 'joint_existing_oracle')
    physical = load(args.rill/'physical_replay.py', 'joint_existing_physical')
    engine, engine_hashes = evaluator.get_engine(args.engine_dir, prepare=False)
    cfg = {k: v.get('default') if isinstance(v, dict) else v
           for k,v in engine.specification['configuration'].items()}
    cfg['seed'] = None
    random.seed(20260907)  # Original actor RNG, not an environment seed.
    actor = scheduler.SellScheduler()
    started = perf_counter()
    observation, restore = restore_prefix(actor, args.trace, cfg, seat=args.seat)
    restore['wall_seconds'] = perf_counter() - started
    input_document = json.loads(args.input.read_text())
    if input_document['observation'] != observation:
        raise ValueError('Restored checkpoint differs from retained player input')
    if input_document['source_trace_sha256'] != source(args.trace)['sha256']:
        raise ValueError('Retained player input is bound to a different trace')
    before = deepcopy({**actor.__dict__, 'controller': actor.controller.__dict__})
    input_before = deepcopy(observation)
    scenarios = {'known_shops_no_external_flow': oracle.Scenario()}
    # Explicit public-flow stress cases, not actual later opponent actions.
    # All own crop/livestock production continues through the real actor.
    for product in ('MILK', 'WHEAT', 'STRAWBERRY'):
        scenarios['external_'+product.lower()+'_one_per_step'] = oracle.Scenario(
            market_deltas={step: {product: 1} for step in range(577, 719)},
            label=f'Explicit hypothetical external {product}+1 before each market; known shops')
    report = evaluate_sell_tails(actor, (actor.controller.cur, MAIN), observation, cfg,
        engine, replay_routes=physical.replay_routes, simulate_bundle=oracle.simulate_bundle,
        scenarios=scenarios, end_step=718,
        limits=physical.ReplayLimits(seconds=args.seconds, decisions=8*142))
    if {**actor.__dict__, 'controller': actor.controller.__dict__} != before or observation != input_before:
        raise AssertionError('Original actor or input changed')
    report['validation'] = {'restore': restore, 'source_pins': pins,
        'engine_sha256': engine_hashes, 'trace_file': source(args.trace),
        'input_file': source(args.input), 'original_actor_unchanged': True,
        'input_unchanged': True, 'configuration': cfg,
        'game_panels': 0, 'new_game_seeds': [],
        'classification': 'Retained PRISM577 observation; explicit conditional tail evaluations',
        'actor_state_at_checkpoint': {k: deepcopy(v) for k,v in before.items() if k != 'controller'},
        'controller_route': actor.controller.cur}
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-root', type=Path, required=True)
    p.add_argument('--rill', type=Path, required=True)
    p.add_argument('--oracle', type=Path, required=True)
    p.add_argument('--engine-dir', type=Path, required=True)
    p.add_argument('--trace', type=Path, required=True)
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--seat', type=int, default=0)
    p.add_argument('--seconds', type=float, default=30)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    result = run(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(encoded(result)+b'\n')
    print(json.dumps({'complete': result['complete'], 'comparisons': result['comparisons'],
                      'restore': result['validation']['restore'],
                      'tail_seconds': result['replay']['wall_seconds']}))
    raise SystemExit(0 if result['complete'] else 1)
