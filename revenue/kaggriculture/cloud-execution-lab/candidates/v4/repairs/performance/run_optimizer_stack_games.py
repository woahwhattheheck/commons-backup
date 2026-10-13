# SPDX-License-Identifier: Apache-2.0
"""One fresh-process native game with all raw actions passed to the pinned engine.

This evaluator deliberately does not impose the historical loader's hand-count
assertion or truncate authored rows: surplus PLANT rows can affect atomic seed
admission. Each invocation authenticates the entire parent manifest and applies
only the named in-memory optimizer overlay. No runtime files are modified.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time
import types
from compose_optimizer_stack import compose, git_blob, SOURCE_GIT


MANIFEST_SHA256 = 'e87d70dd3bcf5aea1e929f1a5dbdc86f3cc33d8a0b3492986f2970fc8e774be2'
FINAL_CORE_GIT = '16dde00627effa5d0ae4d73a8e05a295e9534e1f'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def authenticate(root):
    manifest = root / 'SOURCE.json'
    raw = manifest.read_bytes()
    if sha(raw) != MANIFEST_SHA256:
        raise ValueError('reviewed artifact SOURCE.json identity mismatch')
    data = json.loads(raw)
    checked = {}
    for relative, record in data['runtime'].items():
        path = root / relative
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError('manifest member escapes runtime')
        member = path.read_bytes()
        if len(member) != record['bytes'] or sha(member) != record['sha256']:
            raise ValueError('parent member identity mismatch: ' + relative)
        checked[relative] = sha(member)
    if not checked or 'selected_sell_core.py' not in checked:
        raise ValueError('incomplete parent manifest')
    return {'manifest_sha256': sha(raw), 'members': len(checked),
            'member_map_sha256': sha(json.dumps(checked, sort_keys=True).encode()),
            'entrypoint_git': git_blob((root / 'main.py').read_bytes()),
            'runtime_git': git_blob((root / 'titan_runtime.py').read_bytes())}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def run(root, components, arm, seed, seat, opponent):
    identity = authenticate(root)
    sys.path.insert(0, str(root))
    raw = (root / 'selected_sell_core.py').read_bytes()
    if git_blob(raw) != SOURCE_GIT:
        raise ValueError('unexpected active core')
    overlay = None
    if arm == 'composed':
        raw, overlay = compose(raw, components)
    core = types.ModuleType('selected_sell_core')
    core.__file__ = str(root / 'selected_sell_core.py')
    sys.modules['selected_sell_core'] = core
    exec(compile(raw, core.__file__, 'exec'), core.__dict__)
    optimizer_calls = []
    optimizer_digest = hashlib.sha256(); horizons = {}
    original = core.optimize_lot
    def observed_optimize(**kwargs):
        start = time.perf_counter()
        try:
            result = original(**kwargs)
            optimizer_digest.update(canonical(result) + b'\n')
            horizon = str(kwargs['dates'][-1] - kwargs['now'])
            horizons[horizon] = horizons.get(horizon, 0) + 1
            return result
        finally:
            optimizer_calls.append(time.perf_counter() - start)
    core.optimize_lot = observed_optimize
    entry = load('_weave_entry', root / 'main.py')
    loader = load('_weave_official_loader', root / 'checks/reference/evaluator/loader.py')
    engine, engine_hashes = loader.get_engine(root / 'checks/reference/engine')
    Struct = loader.Struct
    cfg = Struct({key: value.get('default') if isinstance(value, dict) else value
                  for key, value in engine.specification['configuration'].items()})
    cfg.seed = seed
    env = Struct(configuration=cfg, done=False, info={})
    state = [Struct(observation=Struct(), action={}, status='ACTIVE', reward=0) for _ in range(2)]
    engine.interpreter(state, env)
    action_digest = hashlib.sha256(); state_digest = hashlib.sha256()
    timings = []; diagnoses = {}; surplus = 0; tape = []
    start_game = time.perf_counter()
    for step in range(cfg.episodeSteps):
        for player, current in enumerate(state):
            current.observation.step = step
            obs = copy.deepcopy(current.observation)
            if player == seat:
                before = time.perf_counter()
                action = entry.agent(obs, cfg)
                timings.append(time.perf_counter() - before)
                instance = getattr(entry, '_INSTANCE', None)
                status = 'no_instance' if instance is None else instance.diagnostics.get('status', 'missing')
                diagnoses[status] = diagnoses.get(status, 0) + 1
                if not isinstance(action, dict):
                    raise TypeError('native caller returned non-dict action')
                surplus += int(len(action.get('hands', [])) > len(obs['farms'][seat]['hands']))
                action_digest.update(canonical([step, action]) + b'\n')
            elif opponent == 'starter':
                action = engine.starter_agent(obs)
            else:
                action = {'farmer': ['PASS'], 'hands': [], 'market': []}
            current.action = action
        engine.interpreter(state, env)
        frame = canonical([step, state])
        state_digest.update(frame + b'\n')
        tape.append({'step': step, 'state_sha256': sha(frame),
                     'action_sha256': sha(canonical(state[seat].action))})
        if any(current.status == 'DONE' for current in state):
            env.done = True
            break
    # The active runtime may load frozen_selected under its own cached alias.
    callers = [name for name, module in list(sys.modules.items())
               if getattr(module, 'optimize_lot', None) is observed_optimize and module is not core]
    if not optimizer_calls or not callers:
        raise RuntimeError('composed active optimizer was not observed through a native caller')
    if state[0].status != 'DONE' or state[1].status != 'DONE':
        raise RuntimeError('episode did not complete')
    ordered = sorted(timings)
    return {'schema': 'titan-v4-optimizer-stack-native-game/v1', 'arm': arm,
            'python_optimized': sys.flags.optimize, 'seed': seed, 'seat': seat,
            'opponent': opponent, 'parent': identity, 'engine_sha256': engine_hashes,
            'core_git': git_blob(raw), 'composition': overlay,
            'steps': step + 1, 'bank': [current.reward for current in state],
            'action_sha256': action_digest.hexdigest(),
            'full_state_sha256': state_digest.hexdigest(), 'frame_hashes': tape,
            'diagnostic_statuses': diagnoses, 'surplus_hand_callbacks': surplus,
            'native_optimizer_callers': sorted(callers), 'optimizer_calls': len(optimizer_calls),
            'optimizer_seconds': sum(optimizer_calls),
            'optimizer_result_sha256': optimizer_digest.hexdigest(),
            'optimizer_horizons': horizons,
            'callback_seconds': {'mean': statistics.mean(timings), 'max': max(timings),
                                 'p95': ordered[min(len(ordered)-1, int(.95*len(ordered)))]},
            'wall_seconds': time.perf_counter()-start_game}


def run_panel(root, components, destination, seeds):
    """Both-seat/two-opponent pairs for named seeds, each arm in a fresh process."""
    destination.mkdir(parents=True, exist_ok=False)
    rows = []
    for seed in seeds:
        for seat in (0, 1):
            for opponent in ('starter', 'pass'):
                pair = []
                for arm in ('baseline', 'composed'):
                    output = destination / f'{seed}-{seat}-{opponent}-{arm}.json'
                    command = [sys.executable, *(['-O'] if sys.flags.optimize else []),
                               str(Path(__file__).resolve()), '--runtime-root', str(root),
                               '--components-root', str(components), '--arm', arm,
                               '--seed', str(seed), '--seat', str(seat), '--opponent', opponent,
                               '--output', str(output)]
                    completed = subprocess.run(command, capture_output=True, text=True, timeout=60)
                    (destination / (output.stem + '.log')).write_text(
                        completed.stdout + completed.stderr, encoding='utf-8')
                    if completed.returncode:
                        raise RuntimeError(f'game process failed: {output.name}: {completed.stderr}')
                    pair.append(json.loads(output.read_text()))
                old, new = pair
                if old['core_git'] != SOURCE_GIT or new['core_git'] != FINAL_CORE_GIT:
                    raise ValueError('panel source identity mismatch')
                keys = ('parent','engine_sha256','steps','bank','action_sha256',
                        'full_state_sha256','frame_hashes','diagnostic_statuses',
                        'surplus_hand_callbacks','native_optimizer_callers',
                        'optimizer_calls','optimizer_result_sha256','optimizer_horizons')
                for key in keys:
                    if old[key] != new[key]:
                        raise ValueError(f'{seed}/{seat}/{opponent}: unequal {key}')
                if old['steps'] != 719 or old['diagnostic_statuses'] != {'completed': 719}:
                    raise ValueError('incomplete/fallback game does not certify native equivalence')
                rows.append({key: old[key] for key in ('seed','seat','opponent','steps','bank',
                            'action_sha256','full_state_sha256','optimizer_calls',
                            'optimizer_result_sha256','optimizer_horizons','surplus_hand_callbacks')})
                rows[-1]['timing'] = {arm: {key: row[key] for key in
                        ('optimizer_seconds','callback_seconds','wall_seconds')}
                        for arm,row in zip(('baseline','composed'),pair)}
                print(json.dumps({'completed_pair': [seed,seat,opponent],
                                  'optimizer_calls': old['optimizer_calls']}), flush=True)
    result = {'schema': 'titan-v4-optimizer-stack-panel/v1',
              'optimized': sys.flags.optimize, 'parent': old['parent'],
              'engine_sha256': old['engine_sha256'], 'pairs': rows,
              'full_games': 2*len(rows), 'compared_callbacks': sum(row['steps'] for row in rows),
              'native_optimizer_calls_per_arm': sum(row['optimizer_calls'] for row in rows),
              'scope': 'checked artifact default native entrypoint; two simple opponents; no field EV'}
    (destination / 'PANEL.json').write_text(json.dumps(result, indent=2, sort_keys=True)+'\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-root', type=Path, required=True)
    parser.add_argument('--components-root', type=Path, default=Path(__file__).parent)
    parser.add_argument('--panel-dir', type=Path)
    parser.add_argument('--panel-seeds', type=int, nargs='+', default=[9922999,9600912])
    parser.add_argument('--arm', choices=['baseline', 'composed'])
    parser.add_argument('--seed', type=int)
    parser.add_argument('--seat', type=int, choices=[0, 1])
    parser.add_argument('--opponent', choices=['starter', 'pass'], default='starter')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.panel_dir is not None:
        if any(value is not None for value in (args.arm,args.seed,args.seat,args.output)):
            parser.error('panel mode cannot be combined with individual-game arguments')
        result = run_panel(args.runtime_root.resolve(), args.components_root.resolve(),args.panel_dir,args.panel_seeds)
        print(json.dumps({key: result[key] for key in ['full_games','compared_callbacks',
                                                       'native_optimizer_calls_per_arm']}, sort_keys=True))
        return
    if any(value is None for value in (args.arm,args.seed,args.seat,args.output)):
        parser.error('individual game requires --arm, --seed, --seat and --output')
    # Refuse overwrite before running an entire episode.
    with args.output.open('x', encoding='utf-8') as output:
        result = run(args.runtime_root.resolve(), args.components_root.resolve(),
                     args.arm, args.seed, args.seat, args.opponent)
        json.dump(result, output, indent=2, sort_keys=True)
        output.write('\n')
    print(json.dumps({k: result[k] for k in ['arm','seed','seat','opponent','steps','bank',
                     'action_sha256','full_state_sha256','optimizer_calls','diagnostic_statuses',
                     'optimizer_seconds','callback_seconds','wall_seconds']}, sort_keys=True))

if __name__ == '__main__':
    main()
