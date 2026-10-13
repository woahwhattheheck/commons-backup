# SPDX-License-Identifier: Apache-2.0
"""Offline independent-opponent benchmark; one fresh subprocess per complete game.

Uses the existing pinned evaluator solely as the official-engine loader. Native
comparison calls the unchanged archive's main.agent and records its diagnostics.
No network, hosted submission, native overlay, or silent runtime fallback.
"""
from __future__ import annotations
import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
SOURCE_MANIFEST_SHA256 = 'e87d70dd3bcf5aea1e929f1a5dbdc86f3cc33d8a0b3492986f2970fc8e774be2'
LOADER_SHA256 = 'cd113a94ae99b03492502e425bdcf09c3db17a2aa2a8fd866f0d78caec9e311e'
EVALUATOR_SHA256 = 'e30b3108e0027477ab7ddbc057892a241c41a1f2b38f72caf267477877c4333c'
ENGINE_BLOBS = {
    'kaggriculture.py': '3c202c7ee921da239356789e266b694635103fc4',
    'kaggriculture.json': 'b354d06b742fe48402513792253f1a5c29366b20',
    'utils.py': '91c8822ee6201ba4a5a8416c7dbe34f95dd61c87',
}

def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()

def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()

def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f'Cannot load {path}')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

def setup(runtime):
    runtime = Path(runtime).resolve()
    reference = runtime / 'checks/reference'
    evaluator = reference / 'evaluator/evaluate.py'
    if hashlib.sha256(evaluator.read_bytes()).hexdigest() != EVALUATOR_SHA256:
        raise ValueError('Pinned evaluator changed')
    if hashlib.sha256((reference / 'evaluator/loader.py').read_bytes()).hexdigest() != LOADER_SHA256:
        raise ValueError('Pinned loader changed')
    ev = load(evaluator, 'orchard_existing_evaluator')
    engine, hashes = ev.get_engine(reference / 'engine', reference / 'evaluator/loader.py')
    if ev.ENGINE_BLOBS != ENGINE_BLOBS:
        raise ValueError('Official interpreter identity changed')
    cfg = ev.Struct({k: v.get('default') if isinstance(v, dict) else v
                     for k, v in engine.specification['configuration'].items()})
    return ev, engine, hashes, cfg

def verify_native(runtime):
    runtime = Path(runtime).resolve()
    source = (runtime / 'SOURCE.json').read_bytes()
    if hashlib.sha256(source).hexdigest() != SOURCE_MANIFEST_SHA256:
        raise ValueError('Pinned native source manifest changed')
    members = json.loads(source)['runtime']
    for path, record in members.items():
        data = (runtime / path).read_bytes()
        if len(data) != record['bytes'] or hashlib.sha256(data).hexdigest() != record['sha256']:
            raise ValueError(f'Native runtime source changed: {path}')
    return {'manifest_sha256': SOURCE_MANIFEST_SHA256, 'verified_members': len(members)}

def initialized(ev, engine, cfg, seed):
    cfg = deepcopy(cfg)
    cfg.seed = seed
    env = ev.Struct(configuration=cfg, done=False, info={})
    state = [ev.Struct(observation=ev.Struct(), action={}, status='ACTIVE', reward=0)
             for _ in range(2)]
    engine.interpreter(state, env)
    if cfg.get('seed') is not None:
        raise ValueError('Environment seed exposed to agent configuration')
    return state, env

def run_game(runtime, profile, rival, seed, seat, trace_path=None):
    ev, engine, engine_hashes, cfg = setup(runtime)
    policy = load(HERE / 'reactive_challengers.py', 'orchard_policy')
    if profile not in policy.PROFILES or seat not in (0, 1):
        raise ValueError('Unknown challenger or invalid seat')
    state, env = initialized(ev, engine, cfg, seed)
    cfg = env.configuration
    native = None
    native_identity = None
    if rival == 'native':
        native_identity = verify_native(runtime)
        sys.path.insert(0, str(Path(runtime).resolve()))
        native = load(Path(runtime) / 'main.py', 'orchard_native_main')
    elif rival not in ('starter', 'pass', *policy.PROFILES):
        raise ValueError('Unknown rival')
    original_project = policy._project
    parity = Counter()
    def checked_project(farm, private, actor, action, day, tpd, cap):
        ef, ep = deepcopy(farm), deepcopy(private)
        engine._apply_unit_action(ef, ep, actor, deepcopy(action), len(farm['tiles']), day, tpd, cap)
        original_project(farm, private, actor, action, day, tpd, cap)
        if (ef, ep) != (farm, private):
            raise AssertionError(f'Unit projection mismatch: {action!r}, day={day}, actor={actor}')
        parity[action[0]] += 1
    policy._project = checked_project
    action_counts, native_status = Counter(), Counter()
    action_hash, state_hash = hashlib.sha256(), hashlib.sha256()
    peak = [0.0, 0.0]
    total = [0.0, 0.0]
    calls = [0, 0]
    days = []
    trace_file = open(trace_path, 'w') if trace_path else None
    started = time.perf_counter()
    try:
        for step in range(int(cfg.episodeSteps)):
            acts = []
            # Snapshot both observations before either caller can act.
            observations = []
            for s in state:
                s.observation.step = step
                s.observation.remainingOverageTime = 0
                observations.append(deepcopy(s.observation))
            for i in (0, 1):
                obs = observations[i]
                before = digest(obs)
                start = time.perf_counter()
                if i == seat:
                    action = policy.act(obs, cfg, profile=profile)
                elif rival == 'native':
                    action = native.agent(obs, cfg)
                    instance = getattr(native, '_INSTANCE', None)
                    status = getattr(instance, 'diagnostics', {}).get('status', 'unknown')
                    native_status[status] += 1
                elif rival == 'starter':
                    action = engine.starter_agent(obs)
                elif rival == 'pass':
                    action = engine.pass_agent(obs)
                else:
                    action = policy.act(obs, cfg, profile=rival)
                elapsed = time.perf_counter() - start
                total[i] += elapsed; peak[i] = max(peak[i], elapsed); calls[i] += 1
                if digest(obs) != before:
                    raise AssertionError(f'Agent mutated input: seat={i}, step={step}')
                if not isinstance(action, dict):
                    raise TypeError('Action must be an object')
                acts.append(action)
            for op in [acts[seat]['farmer'], *acts[seat]['hands']]:
                action_counts['unit:' + op[0]] += 1
            for order in acts[seat]['market']:
                action_counts['market:' + order[0] + (':' + order[1] if len(order) > 1 else '')] += 1
            for i in (0, 1):
                state[i].action = acts[i]
            engine.interpreter(state, env)
            snapshot_hash = digest([s.observation for s in state])
            action_hash.update(encoded(acts)); state_hash.update(snapshot_hash.encode())
            if trace_file:
                trace_file.write(json.dumps({'step': step, 'actions': acts,
                                             'post_observation_sha256': snapshot_hash}, sort_keys=True) + '\n')
            done = all(s.status == 'DONE' for s in state)
            if (step + 1) % cfg.turnsPerDay == 0 or done:
                farm = state[0].observation.farms[seat]
                tiles = [t for row in farm['tiles'] for t in row if isinstance(t, dict)]
                days.append({'step': step, 'cash': [f['money'] for f in state[0].observation.farms],
                             'animals': dict(Counter(t['animal'] for t in tiles if 'animal' in t)),
                             'crops': dict(Counter(t['crop'] for t in tiles if 'crop' in t)),
                             'weeds': sum(t['kind'] == 'WEED' for t in tiles)})
            if done:
                break
        if not done:
            raise RuntimeError('Incomplete game')
        scores = [s.reward for s in state]
        return {'schema': 'titan.independent_challengers.game.v1', 'status': 'complete',
                'profile': profile, 'opponent': rival, 'seed': seed, 'seat': seat,
                'scores': scores, 'margin': scores[seat] - scores[1-seat],
                'steps': step + 1, 'calls': calls, 'native_status': dict(native_status),
                'native_identity': native_identity,
                'unit_projection_checks': dict(parity), 'action_counts': dict(action_counts),
                'actions_sha256': action_hash.hexdigest(), 'observations_sha256': state_hash.hexdigest(),
                'terminal_sha256': digest([s.observation for s in state]),
                'daily': days, 'peak_call_seconds': peak, 'total_call_seconds': total,
                'wall_seconds': time.perf_counter() - started,
                'source_sha256': hashlib.sha256((HERE / 'reactive_challengers.py').read_bytes()).hexdigest(),
                'engine_sha256': engine_hashes, 'native_main_sha256':
                    hashlib.sha256((Path(runtime) / 'main.py').read_bytes()).hexdigest() if native else None,
                'measurement': 'local pinned official interpreter, not hosted; projected-unit checking overhead included'}
    finally:
        if trace_file:
            trace_file.close()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--profiles', default='dairy,poultry,fiber,roots,orchard')
    parser.add_argument('--opponents', default='starter')
    parser.add_argument('--seeds', default='17')
    parser.add_argument('--seats', default='0,1')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--one', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--trace', type=Path)
    args = parser.parse_args()
    if args.one:
        result = run_game(args.runtime, args.profiles, args.opponents, int(args.seeds), int(args.seats), args.trace)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
        return
    rows = []
    for profile in args.profiles.split(','):
        for rival in args.opponents.split(','):
            for seed in args.seeds.split(','):
                for seat in args.seats.split(','):
                    part = args.output.with_suffix(f'.{profile}.{rival}.{seed}.{seat}.json')
                    command = [sys.executable, *(['-O'] if sys.flags.optimize else []), __file__,
                               '--one', '--runtime', str(args.runtime), '--profiles', profile,
                               '--opponents', rival, '--seeds', seed, '--seats', seat, '--output', str(part)]
                    completed = subprocess.run(command, capture_output=True, text=True, timeout=180)
                    if completed.returncode:
                        raise RuntimeError(f'Game failed {profile}/{rival}/{seed}/{seat}: {completed.stderr}')
                    row = json.loads(part.read_text()); rows.append(row)
                    args.output.write_text(json.dumps(rows, indent=2, sort_keys=True) + '\n')
                    print(profile, rival, seed, seat, row['scores'], row['margin'], flush=True)

if __name__ == '__main__':
    main()
