# SPDX-License-Identifier: Apache-2.0
"""Paired artifact-native full-game gate; offline, no production installation.

Use the exact b567 artifact-native directory and its CURRENT-SOURCE.json. Only
mechanics.py differs in disposable candidate copies. Each arm/game gets a fresh
process; the official interpreter, raw hand/market vectors and deadlines remain
intact. This is not a Kaggle-hosted or whole-assembled-V4 performance claim.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import importlib.util
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from evidence_support import NAMES, PINS, checked, digest, initial
from repair_lifecycle import repair_source

MANIFEST_SHA = 'e87d70dd3bcf5aea1e929f1a5dbdc86f3cc33d8a0b3492986f2970fc8e774be2'


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


def play(runtime, seed, seat, count=False):
    for name, expected in PINS.items():
        checked(runtime/name, expected)
    loader = load(runtime/'checks/reference/evaluator/loader.py', 'native_gate_loader')
    engine, _ = loader.get_engine(runtime/'checks/reference/engine')
    entry = load(runtime/'main.py', 'native_entry')
    state, env = initial(loader, engine, seed)
    frames = hashlib.sha256()
    durations, cpu_durations, trace, extra_hands = [], [], [], 0
    calls = {name: 0 for name in NAMES}
    wrapped = set()
    wrapped_modules = []
    def instrument():
        # Count from step 1 onward without moving native imports outside the
        # actual main.agent first-call deadline. This probe is timed separately.
        for obj in list(sys.modules.values()):
            source = getattr(obj, '__file__', None)
            if not source or Path(source).resolve() != runtime/'mechanics.py' or id(obj) in wrapped:
                continue
            wrapped.add(id(obj))
            wrapped_modules.append(obj)
            for name in NAMES:
                original = getattr(obj, name)
                def wrapper(*args, _fn=original, _name=name, **kwargs):
                    calls[_name] += 1
                    return _fn(*args, **kwargs)
                setattr(obj, name, wrapper)
    for step in range(env.configuration.episodeSteps):
        for player, record in enumerate(state):
            record.observation.step = step
            observation = copy.deepcopy(record.observation)
            if player == seat:
                started = time.perf_counter()
                cpu = time.process_time()
                action = entry.agent(observation, env.configuration)
                cpu_durations.append(time.process_time()-cpu)
                durations.append(time.perf_counter()-started)
                instance = entry._INSTANCE
                diagnostics = getattr(instance, 'diagnostics', {})
                trace.append([diagnostics.get('status'), diagnostics.get('parent_calls'),
                              diagnostics.get('fallback_stage')])
                if diagnostics.get('status') != 'completed':
                    raise RuntimeError(f'native incomplete seed={seed} seat={seat} step={step}: {diagnostics}')
                extra_hands += max(0, len(action.get('hands', []))-len(observation['farms'][seat]['hands']))
            else:
                action = engine.starter_agent(observation)
            if not isinstance(action, dict):
                raise TypeError('native action is not a dict')
            record.action = action  # Preserve ALL raw rows, including surplus hands.
        engine.interpreter(state, env)
        frames.update(json.dumps({'state': state, 'trace': trace[-1]}, sort_keys=True,
                                 separators=(',', ':'), allow_nan=False).encode())
        frames.update(b'\n')
        if count and step == 0: instrument()
        if any(record.status == 'DONE' for record in state):
            break
    if [record.status for record in state] != ['DONE', 'DONE']:
        raise RuntimeError('game failed to finish')
    if count:
        if not wrapped_modules:
            raise RuntimeError('no root mechanics module instrumented')
        for obj in wrapped_modules:
            before = dict(calls)
            obj._decay_plants({'tiles': []}, 0)
            obj._daily_refresh_plants({'tiles': []}, 0, 24)
            obj._daily_refresh_animals({'tiles': []}, 0)
            if any(calls[name] != before[name]+1 for name in NAMES):
                raise RuntimeError('positive instrumentation control failed')
            calls.update(before)
    return {'seed': seed, 'seat': seat, 'steps': step+1, 'status': [s.status for s in state],
            'rewards': [s.reward for s in state], 'frame_sha256': frames.hexdigest(),
            'trace_sha256': digest(json.dumps(trace, separators=(',', ':')).encode()),
            'extra_hand_rows_preserved': extra_hands, 'incomplete_calls': 0,
            'cpu_seconds': sum(cpu_durations), 'wall_seconds': sum(durations),
            'max_call_seconds': max(durations), 'cold_call_seconds': durations[0],
            'instrumented_from_step1': count, 'lifecycle_calls': calls,
            'instrumented_modules': [obj.__name__ for obj in wrapped_modules],
            'instrumentation_positive_control': bool(count)}


def authenticate(runtime, manifest):
    data = json.loads(checked(manifest, MANIFEST_SHA))
    files = data['runtime']
    if len(files) != 109:
        raise ValueError('wrong runtime member count')
    for path, identity in files.items():
        checked(runtime/path, identity['sha256'])
    return files


def run_pair(runtime, manifest, output, seed, seat, optimized=False, count=False):
    """One bounded pair per invocation; collect several independent pair receipts."""
    files = authenticate(runtime, manifest)
    if output.exists():
        raise FileExistsError(output)
    report = {'scope': 'artifact-native b567; not whole-current assembled V4',
              'driver_sha256': digest(Path(__file__).read_bytes()),
              'manifest_sha256': MANIFEST_SHA, 'authenticated_files': len(files),
              'mode': 'optimized' if optimized else 'normal', 'instrumented': count,
              'seed': seed, 'seat': seat}
    with tempfile.TemporaryDirectory(prefix='phenology-pair-') as temporary:
        candidate = Path(temporary)/'candidate'
        shutil.copytree(runtime, candidate, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        text = repair_source((runtime/'mechanics.py').read_text())
        (candidate/'mechanics.py').write_text(text)
        changed = [path for path in files if (runtime/path).read_bytes() != (candidate/path).read_bytes()]
        if changed != ['mechanics.py']:
            raise RuntimeError(f'unexpected changed paths: {changed}')
        report['changed_files'] = changed
        report['candidate_mechanics_sha256'] = digest(text.encode())
        order = ('baseline', 'candidate') if seat == 0 else ('candidate', 'baseline')
        for arm in order:
            dest = Path(temporary)/(arm+'.json')
            root = runtime if arm == 'baseline' else candidate
            command = [sys.executable, *(['-O'] if optimized else []), str(Path(__file__).resolve()),
                       '--child', '--runtime', str(root), '--seed', str(seed), '--seat', str(seat),
                       '--output', str(dest), *(['--count'] if count else [])]
            subprocess.run(command, check=True, timeout=180,
                           env={**os.environ, 'PYTHONHASHSEED': '0'})
            report[arm] = json.loads(dest.read_text())
        keys = ('frame_sha256', 'trace_sha256', 'rewards', 'steps', 'status',
                'extra_hand_rows_preserved', 'lifecycle_calls')
        for key in keys:
            if report['baseline'][key] != report['candidate'][key]:
                raise RuntimeError('native pair mismatch: '+key)
        authenticate(runtime, manifest)
        for path, identity in files.items():
            expected = report['candidate_mechanics_sha256'] if path == 'mechanics.py' else identity['sha256']
            checked(candidate/path, expected)
        report['disposition'] = ('COLD_ON_PROBE' if count and not any(report['baseline']['lifecycle_calls'].values())
                                 else 'REACHED_ON_PROBE' if count else 'ACTION_STATE_IDENTICAL')
    output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({'seed': seed, 'seat': seat, 'mode': report['mode'],
                      'disposition': report['disposition'], 'output': str(output)}), flush=True)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', required=True, type=lambda p: Path(p).resolve())
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--seed', type=int, default=9600913)
    parser.add_argument('--seat', type=int, choices=(0, 1), default=0)
    parser.add_argument('--optimized', action='store_true')
    parser.add_argument('--child', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--count', action='store_true')
    args = parser.parse_args()
    if args.child:
        args.output.write_text(json.dumps(play(args.runtime, args.seed, args.seat, args.count), indent=2)+'\n')
    else:
        if args.manifest is None: parser.error('--manifest is required')
        run_pair(args.runtime, args.manifest, args.output, args.seed, args.seat, args.optimized, args.count)
