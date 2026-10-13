# SPDX-License-Identifier: Apache-2.0
"""Check actual TITAN SELL recovery on retained own-observation streams.

This does not call the game interpreter, run an opponent, or create new games.
The independent reference actor receives only the returned producer action on
an injected-fallback turn, then advances the public observer without accepting
unreturned SELL planning. No replay seed or future state is supplied to TITAN.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
import sys
import time
import traceback
from unittest.mock import patch
from profile_retained import retained_calls


def snapshot(consumer, player: int):
    previous = consumer.previous
    return deepcopy({
        'planned': consumer.planned,
        'pending': consumer.pending,
        'observed_harvests': consumer.observed_harvests,
        'previous_step': None if previous is None else previous.get('step'),
        'previous_player': None if previous is None else previous.get('player'),
        'previous_rival_tiles': None if previous is None else previous['farms'][1-player]['tiles'],
    })


def same(actual, expected, label: str):
    if actual != expected:
        raise AssertionError(label)


def run_case(T, features, rows, cfg, seat: int, fault_step: int,
             mode: str, suffix_length: int, mutate_subject=None):
    subject, reference = T.TitanAgent(features), T.TitanAgent(features)
    started = time.perf_counter()
    for step in range(fault_step):
        obs, expected = rows[step]
        a = subject.act(deepcopy(obs), cfg)
        b = reference.act(deepcopy(obs), cfg)
        same(a, expected, f'original action mismatch before injection: {step}')
        same(a, b, f'reference mismatch before injection: {step}')
    before = snapshot(reference.consumer, seat)
    if mutate_subject is not None:
        mutate_subject(subject, T)
    obs = deepcopy(rows[fault_step][0])
    original_obs = deepcopy(obs)
    control_selected = None
    if mode != 'prelude_duplicate':
        # Independent reference: producer once; public observer once; no SELL
        # transform, SeedBudget, or speculative plan is executed on fallback.
        control_selected = reference.production.act(deepcopy(obs))
    reference.consumer.observe(deepcopy(obs))
    reference.consumer.previous = deepcopy(obs)
    expected_after = snapshot(reference.consumer, seat)
    timers = []
    timer_class = T.deadline._DeadlineTimer
    def timer_factory(seconds):
        timer = timer_class(seconds)
        timers.append(timer)
        return timer

    if mode == 'prelude_duplicate':
        for _ in range(2):
            returned = subject.act(obs, cfg, entry_started=time.perf_counter()-2)
            same(returned, T.deadline.legal_pass(obs), 'prelude did not return PASS')
            same(subject.diagnostics.get('fallback_stage'), 'entrypoint_prelude', 'wrong prelude stage')
        same(len(subject._seller_fallback_observations), 1, 'repeated step was queued twice')
    else:
        real_transform = subject.consumer.transform
        def interrupted_transform(observation, configuration, selected):
            if mode == 'after_observe':
                subject.consumer.observe(observation)
            else:
                real_transform(observation, configuration, selected)
            # Distinguish discarded unreturned state from an accidentally
            # retained post-transform object, without altering any observation.
            subject.consumer.planned['__UNRETURNED__'] = [(fault_step+1, 999)]
            subject.consumer.pending['__UNRETURNED__'] = 999
            subject.consumer.observed_harvests['__UNRETURNED__'] = [(fault_step, 999)]
            raise timers[-1].expired
        if mode in ('after_observe', 'after_transform'):
            with patch.object(T.deadline, '_DeadlineTimer', side_effect=timer_factory), \
                    patch.object(subject.consumer, 'transform', side_effect=interrupted_transform):
                returned = subject.act(obs, cfg)
        elif mode == 'after_checkpoint_copy':
            real_state = subject._seller_state
            def interrupted_state(consumer):
                real_state(consumer)
                raise timers[-1].expired
            with patch.object(T.deadline, '_DeadlineTimer', side_effect=timer_factory), \
                    patch.object(subject, '_seller_state', side_effect=interrupted_state):
                returned = subject.act(obs, cfg)
        else:
            raise ValueError(f'Unsupported mode {mode}')
        same(returned, control_selected, 'fallback differs from completed producer selection')
        same(subject.diagnostics.get('status'), 'deadline_fallback', 'injection did not use deadline fallback')
    if subject.ready:
        raise AssertionError('Interrupted consumer was retained ready')
    same(obs, original_obs, 'input observation was mutated by runtime')

    # Mutating caller-owned bytes after return must not mutate queued inputs.
    caller_tiles = obs['farms'][1-seat]['tiles']
    caller_tiles[0][0] = {'kind': 'PLANT', 'crop': 'MILK', 'yield_units': 1234567}
    old_controller = subject.controller
    subject._initialize()
    if subject.controller is old_controller:
        raise AssertionError('No reconstruction occurred')
    same(snapshot(subject.consumer, seat), expected_after,
         'reconstructed SELL state differs from independent public-observer reference')
    same(subject.controller.cur, reference.controller.cur, 'route did not survive fallback')
    continuation = []
    for step in range(fault_step+1, min(len(rows), fault_step+1+suffix_length)):
        next_obs = rows[step][0]
        actual = subject.act(deepcopy(next_obs), cfg)
        expected = reference.act(deepcopy(next_obs), cfg)
        same(actual, expected, f'post-recovery action mismatch: {step}')
        same(snapshot(subject.consumer, seat), snapshot(reference.consumer, seat),
             f'post-recovery SELL state mismatch: {step}')
        same(subject.diagnostics.get('status'), 'completed', 'unexpected continuation fallback')
        continuation.append(actual)
    return {
        'case': mode, 'seat': seat, 'fault_step': fault_step,
        'prefix_actions_per_actor': fault_step,
        'continuation_actions_per_actor': len(continuation),
        'independent_reference': 'producer_then_public_observer_without_SELL_transform',
        'pending_plan_present_before_fault': bool(before['planned']),
        'public_harvest_history_present': any(before['observed_harvests'].values()),
        'caller_mutation_isolated': True,
        'continuation_sha256': hashlib.sha256(json.dumps(continuation, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
        'passed': True, 'new_games': 0, 'elapsed_seconds': time.perf_counter()-started,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', required=True, type=Path)
    p.add_argument('--trace', required=True, type=Path)
    p.add_argument('--seat', required=True, type=int, choices=(0, 1))
    p.add_argument('--fault-step', type=int, default=436)
    p.add_argument('--suffix-length', type=int, default=24)
    p.add_argument('--modes', default='after_observe,after_transform,after_checkpoint_copy,prelude_duplicate')
    p.add_argument('--output', required=True, type=Path)
    args = p.parse_args()
    if not 1 <= args.fault_step < 718 or args.suffix_length < 1:
        p.error('fault-step must be 1..717 and suffix-length must be positive')
    rows = retained_calls(args.trace, args.seat)
    spec = json.loads((args.root/'checks/reference/engine/kaggriculture.json').read_text())
    cfg = {k: v.get('default') if isinstance(v, dict) else v for k, v in spec['configuration'].items()}
    cfg['seed'] = None
    sys.path.insert(0, str(args.root.resolve()))
    T = importlib.import_module('titan_runtime')
    features = T.Features(**json.loads((args.root/'TITAN-CONFIG.json').read_text()))
    results = []
    for mode in args.modes.split(','):
        try:
            row = run_case(T, features, rows, cfg, args.seat, args.fault_step, mode, args.suffix_length)
        except Exception as exc:
            row = {'case': mode, 'seat': args.seat, 'fault_step': args.fault_step,
                   'passed': False, 'error': str(exc), 'traceback': traceback.format_exc(), 'new_games': 0}
        results.append(row)
        print(json.dumps(row), flush=True)
    report = {'schema': 1, 'kind': 'retained_inference_recovery_contract', 'new_games': 0,
              'root': str(args.root.resolve()), 'trace_sha256': hashlib.sha256(args.trace.read_bytes()).hexdigest(),
              'runtime_sha256': hashlib.sha256((args.root/'titan_runtime.py').read_bytes()).hexdigest(),
              'results': results, 'passed': all(r['passed'] for r in results)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    raise SystemExit(0 if report['passed'] else 1)

if __name__ == '__main__':
    main()
