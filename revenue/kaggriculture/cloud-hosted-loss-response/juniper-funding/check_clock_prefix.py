# SPDX-License-Identifier: Apache-2.0
"""Compare original explicit-clock and repaired sparse-clock saved-input actors.

This replays observations into two actual policy instances, not into the engine.
No new game result or runtime-performance claim is inferred from the comparison.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time


def load(path, name, data):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    exec(compile(data, str(path), 'exec'), module.__dict__)
    return module


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def state(run):
    scheduler = getattr(run.policy, 'scheduler', run.policy)
    return {'route': run.controller.cur,
            'planned': scheduler.planned, 'pending': scheduler.pending,
            'previous': scheduler.previous, 'observed_harvests': scheduler.observed_harvests,
            'budget_events': run.budget.events, 'funding': run.seed_funding}


def instrument_factory(module, counts):
    original = module.make_agent
    def factory(*args, **kwargs):
        run = original(*args, **kwargs)
        counts['actors'] += 1
        policy_act, controller_act = run.policy.act, run.controller.act
        def policy_call(*a, **k):
            counts['policy_calls'] += 1
            return policy_act(*a, **k)
        def controller_call(*a, **k):
            counts['controller_calls'] += 1
            return controller_act(*a, **k)
        run.policy.act, run.controller.act = policy_call, controller_call
        return run
    module.make_agent = factory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--baseline-dir', type=Path, required=True,
                        help='Original seed_main.py, arms.py, capital_arms.py (published source pins)')
    parser.add_argument('--frames', type=Path, required=True)
    parser.add_argument('--kind', choices=('frozen', 'capital'), required=True)
    parser.add_argument('--position', type=int, choices=(0, 1), required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve(); t13 = root/'cloud-hosted-loss-response'
    name = 'arms.py' if args.kind == 'frozen' else 'capital_arms.py'
    seed_path, arms_path = t13/'seed_main.py', t13/'juniper-funding'/name
    original_seed = (args.baseline_dir/'seed_main.py').read_bytes()
    original_arms = (args.baseline_dir/name).read_bytes()
    new_seed, new_arms = seed_path.read_bytes(), arms_path.read_bytes()
    subjects = [load(seed_path, '_clock_prefix_old_seed', original_seed),
                load(seed_path, '_clock_prefix_new_seed', new_seed)]
    actors = [load(arms_path, '_clock_prefix_old_arm', original_arms),
              load(arms_path, '_clock_prefix_new_arm', new_arms)]
    counts = [{'actors': 0, 'policy_calls': 0, 'controller_calls': 0} for _ in actors]
    for module, count in zip(actors, counts):
        instrument_factory(module, count)
    data = args.frames.read_bytes()
    frames = [json.loads(line) for line in gzip.decompress(data).splitlines()]
    action_hashes = [hashlib.sha256(), hashlib.sha256()]
    state_hashes = [hashlib.sha256(), hashlib.sha256()]
    transitions, funding, completed = [], [], 0
    previous_route = None
    start = time.perf_counter()
    failure = None
    try:
        for step, (before, after) in enumerate(zip(frames, frames[1:])):
            observation = deepcopy(before['state'][args.position]['observation'])
            observation.update(step=step, remainingOverageTime=0)
            sparse = deepcopy(observation); sparse.pop('step')
            cfg = deepcopy(before['configuration'])
            inputs_before = deepcopy((observation, sparse, cfg))
            outputs, states = [], []
            for index, obs in enumerate((observation, sparse)):
                sys.modules['seed_main'] = subjects[index]
                output = actors[index].agent(obs, cfg)
                outputs.append(output)
                states.append(deepcopy(state(actors[index]._INSTANCES['funded'])))
                action_hashes[index].update(canonical(output)+b'\n')
                state_hashes[index].update(canonical(states[-1])+b'\n')
            if outputs[0] != outputs[1] or outputs[1] != after['state'][args.position]['action']:
                raise AssertionError(f'Action mismatch at step {step}')
            if states[0] != states[1]:
                raise AssertionError(f'Persistent state mismatch at step {step}')
            if inputs_before != (observation, sparse, cfg):
                raise AssertionError(f'Caller input mutated at step {step}')
            for count in counts:
                if count != {'actors': 1, 'policy_calls': step+1, 'controller_calls': step+1}:
                    raise AssertionError(f'Actor dispatch mismatch at step {step}: {count}')
            route = states[1]['route']
            if route != previous_route:
                transitions.append({'step': step, 'route': route})
                previous_route = route
            if states[1]['funding'] is not None:
                funding.append({'step': step, 'report': states[1]['funding']})
            completed += 1
    except Exception as exc:
        failure = {'type': type(exc).__name__, 'detail': str(exc)}
    report = {'schema': 'juniper-seed-clock-prefix-v1', 'kind': args.kind, 'seat': args.position,
              'complete': completed == len(frames)-1 and failure is None,
              'compared_decisions': completed, 'expected_decisions': len(frames)-1,
              'dispatch_counts': counts, 'action_sha256': [h.hexdigest() for h in action_hashes],
              'state_sha256': [h.hexdigest() for h in state_hashes],
              'route_changes': transitions, 'funding': funding, 'failure': failure,
              'input_sha256': hashlib.sha256(data).hexdigest(),
              'sources': {'original_seed': hashlib.sha256(original_seed).hexdigest(),
                          'original_arm': hashlib.sha256(original_arms).hexdigest(),
                          'new_seed': hashlib.sha256(new_seed).hexdigest(),
                          'new_arm': hashlib.sha256(new_arms).hexdigest()},
              'new_games': 0, 'interpreter_transitions': 0,
              'wall_seconds_including_instrumentation': time.perf_counter()-start}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('funding', 'sources')}, indent=2))
    return not report['complete']


if __name__ == '__main__':
    raise SystemExit(main())
