# SPDX-License-Identifier: Apache-2.0
"""One authenticated full native game, isolated in a fresh Python process.

No clock/budget/config override or agent substitution. Counter/profile modes are
explicit diagnostics and must not be pooled with uninstrumented timing runs.
"""
from __future__ import annotations

import argparse
import collections
import copy
import cProfile
import hashlib
import importlib.util
import json
from pathlib import Path
import pstats
import sys
import tempfile
import time

import compose

SOURCE_SHA256 = 'e87d70dd3bcf5aea1e929f1a5dbdc86f3cc33d8a0b3492986f2970fc8e774be2'
UNITFLOW_BLOB = 'e1127c4aad842278a9e617903b0718d21c00f348'
HERE = Path(__file__).resolve().parent


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def authenticate(package):
    data = (package / 'SOURCE.json').read_bytes()
    if hashlib.sha256(data).hexdigest() != SOURCE_SHA256:
        raise ValueError('Unrecognized SOURCE.json: do not certify a different native package')
    manifest = json.loads(data)['runtime']
    if len(manifest) != 109:
        raise ValueError('Expected 109 native runtime members')
    for name, expected in manifest.items():
        path = Path(name)
        if path.is_absolute() or '..' in path.parts:
            raise ValueError('Unsafe manifest path')
        content = (package / path).read_bytes()
        if len(content) != expected['bytes'] or hashlib.sha256(content).hexdigest() != expected['sha256']:
            raise ValueError(f'Native dependency changed: {name}')
    return manifest


def prepare(package, output, arm, unitflow=None):
    manifest = authenticate(package)
    texts = {name: (package / name).read_bytes() for name in manifest}
    if arm.startswith('unitflow'):
        if unitflow is None or compose.blob(unitflow.read_bytes()) != UNITFLOW_BLOB:
            raise ValueError('Exact UNITFLOW source is required for this arm')
        peer = load(unitflow, 'livepath_exact_unitflow')
        sched, frozen = peer.compose_sources(texts['scheduler.py'].decode(),
                                             texts['frozen_selected.py'].decode())
        texts['scheduler.py'], texts['frozen_selected.py'] = sched.encode(), frozen.encode()
    if arm.endswith('clone'):
        helper = (HERE / 'projection_clone.py').read_bytes()
        if hashlib.sha256(helper).hexdigest() != compose.HELPER_SHA256:
            raise ValueError('Clone helper changed')
        frozen, capital = compose.compose_sources(texts['frozen_selected.py'].decode(),
                                                   texts['early_capital.py'].decode())
        texts.update({'frozen_selected.py': frozen.encode(),
                      'early_capital.py': capital.encode(), 'projection_clone.py': helper})
    for name, data in texts.items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    identities = {name: {'blob': compose.blob(data), 'sha256': hashlib.sha256(data).hexdigest()}
                  for name, data in texts.items()}
    return identities


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def run(root, args, identities):
    sys.path[:0] = [str(root), str(root / 'checks')]
    from test_engine_semantics import EngineSemantics
    EngineSemantics.setUpClass()
    engine, ev = EngineSemantics.engine, EngineSemantics.ev
    entry = load(root / 'main.py', 'livepath_native_entry')
    counts = collections.Counter()
    if args.count_clones:
        if not args.arm.endswith('clone'):
            raise ValueError('--count-clones requires a clone arm')
        import projection_clone
        original_clone = projection_clone.clone_projection
        def counted(value, memo=None):
            counts[sys._getframe(1).f_code.co_name] += 1
            return original_clone(value, memo)
        projection_clone.clone_projection = counted
    cfg = ev.Struct({k: v.get('default') if isinstance(v, dict) else v
                     for k, v in engine.specification['configuration'].items()})
    cfg.seed = args.seed
    requested_configuration = copy.deepcopy(dict(cfg))
    env = ev.Struct(configuration=cfg, done=False, info={})
    state = [ev.Struct(observation=ev.Struct(), action={}, status='ACTIVE', reward=0)
             for _ in range(2)]
    engine.interpreter(state, env)
    if env.info.get('seed') != args.seed:
        raise ValueError('Engine did not retain the requested seed')
    profile = cProfile.Profile() if args.profile else None
    action_hash, state_hash, joint_hash = (hashlib.sha256() for _ in range(3))
    statuses, rows = collections.Counter(), []
    wall_start, cpu_start = time.perf_counter(), time.process_time()
    for step in range(int(cfg.episodeSteps)):
        for participant in state:
            participant.observation.step = step
        obs = copy.deepcopy(state[args.seat].observation)
        before = encoded(obs)
        cpu, wall = time.process_time(), time.perf_counter()
        if profile:
            profile.enable()
        action = entry.agent(obs, cfg)
        if profile:
            profile.disable()
        elapsed, elapsed_cpu = time.perf_counter() - wall, time.process_time() - cpu
        if encoded(obs) != before:
            raise AssertionError('Native agent mutated its input observation')
        diag = dict(entry._INSTANCE.diagnostics) if entry._INSTANCE else {}
        status = diag.get('status')
        statuses[status] += 1
        rows.append([step, elapsed, elapsed_cpu, status])
        state[args.seat].action = action
        state[1 - args.seat].action = engine.starter_agent(copy.deepcopy(state[1 - args.seat].observation))
        engine.interpreter(state, env)
        actions = [s.action for s in state]
        states = {'observations': [s.observation for s in state],
                  'rewards': [s.reward for s in state], 'status': [s.status for s in state]}
        action_hash.update(encoded(actions) + b'\n')
        state_hash.update(encoded(states) + b'\n')
        joint_hash.update(encoded({'actions': actions, **states}) + b'\n')
        if any(s.status == 'DONE' for s in state):
            break
    complete = all(s.status == 'DONE' for s in state)
    if not complete or len(rows) != int(cfg.episodeSteps) - 1:
        raise AssertionError('Expected a complete official 719-callback game')
    result = {
        'arm': args.arm, 'requested_seed': args.seed, 'engine_seed': env.info['seed'],
        'configuration': requested_configuration, 'seat': args.seat,
        'opponent': 'official_starter', 'python': sys.version, 'optimized': bool(sys.flags.optimize),
        'profiled': args.profile, 'instrumented_counts': args.count_clones,
        'runtime_members_authenticated': 109, 'source_manifest_sha256': SOURCE_SHA256,
        'materialized_members': identities, 'engine_hashes': EngineSemantics.hashes,
        'callbacks': len(rows), 'interpreter_calls': len(rows) + 1,
        'statuses': dict(statuses), 'final_status': [s.status for s in state],
        'rewards': [s.reward for s in state], 'action_trace_sha256': action_hash.hexdigest(),
        'state_trace_sha256': state_hash.hexdigest(), 'joint_trace_sha256': joint_hash.hexdigest(),
        'clone_calls': dict(counts), 'agent_wall_seconds': sum(row[1] for row in rows),
        'agent_cpu_seconds': sum(row[2] for row in rows),
        'game_wall_seconds': time.perf_counter() - wall_start,
        'game_cpu_seconds': time.process_time() - cpu_start,
        'timing_rows_schema': ['step', 'agent_wall_seconds', 'agent_cpu_seconds', 'status'],
        'timing_rows': rows,
    }
    if profile:
        functions = []
        for (path, line, name), (cc, nc, own, cumulative, callers) in pstats.Stats(profile).stats.items():
            functions.append({'path': path.replace(str(root), 'NATIVE'), 'line': line,
                              'name': name, 'calls': nc, 'primitive_calls': cc,
                              'own_seconds': own, 'cumulative_seconds': cumulative,
                              'callers': [{'path': k[0].replace(str(root), 'NATIVE'),
                                           'line': k[1], 'name': k[2], 'stats': list(v)}
                                          for k, v in callers.items()]})
        result['profile'] = sorted(functions, key=lambda f: f['cumulative_seconds'], reverse=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--arm', choices=('base', 'clone', 'unitflow', 'unitflow-clone'), required=True)
    parser.add_argument('--unitflow', type=Path)
    parser.add_argument('--seed', type=int, default=9922999)
    parser.add_argument('--seat', type=int, choices=(0, 1), default=0)
    parser.add_argument('--profile', action='store_true')
    parser.add_argument('--count-clones', action='store_true')
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit('Refusing to overwrite an earlier game result')
    with tempfile.TemporaryDirectory(prefix='livepath-native-') as temporary:
        root = Path(temporary)
        identities = prepare(args.package.resolve(), root, args.arm, args.unitflow)
        result = run(root, args, identities)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, separators=(',', ':'), sort_keys=True) + '\n')
    print(json.dumps({key: value for key, value in result.items()
                     if key not in ('timing_rows', 'profile', 'materialized_members', 'configuration')}))


if __name__ == '__main__':
    main()
