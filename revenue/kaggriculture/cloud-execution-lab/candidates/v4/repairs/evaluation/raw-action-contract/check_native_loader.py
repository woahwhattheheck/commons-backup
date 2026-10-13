# SPDX-License-Identifier: Apache-2.0
"""Run one authenticated archive game to compare loader/direct action+state traces.

Each invocation uses a fresh process. Does not activate or rewrite the native
agent, runtime, archive or engine. --arm legacy is expected to fail without -O
when its raw-vector assertions encounter surplus hand rows.
"""
from __future__ import annotations
import argparse
from collections import Counter
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import sys
import time
import traceback

from repair_loader import blob_hash, repair_source, SOURCE_BLOB
from test_loader_contract import ENGINE_PINS, direct_play, load_bytes
import test_loader_contract as reference

ARCHIVE_SHA = 'b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9'
MANIFEST_SHA = 'e87d70dd3bcf5aea1e929f1a5dbdc86f3cc33d8a0b3492986f2970fc8e774be2'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def authenticate(root: Path, archive: Path, manifest_path: Path):
    if hashlib.sha256(archive.read_bytes()).hexdigest() != ARCHIVE_SHA:
        raise ValueError('Checked archive identity mismatch')
    manifest_bytes = manifest_path.read_bytes()
    if hashlib.sha256(manifest_bytes).hexdigest() != MANIFEST_SHA:
        raise ValueError('Checked source manifest identity mismatch')
    manifest = json.loads(manifest_bytes)
    files = manifest['runtime']
    for name, expected in files.items():
        path = (root/name).resolve()
        if not path.is_relative_to(root.resolve()):
            raise ValueError('Runtime manifest path escapes root')
        data = path.read_bytes()
        if len(data) != expected['bytes'] or hashlib.sha256(data).hexdigest() != expected['sha256']:
            raise ValueError(f'Runtime member mismatch: {name}')
    actual = {str(p.relative_to(root)) for p in root.rglob('*')
              if p.is_file() and '__pycache__' not in p.parts}
    if actual != set(files) | {'SOURCE.json'}:
        raise ValueError('Runtime member set is not the checked package')
    if (root/'SOURCE.json').read_bytes() != manifest_bytes:
        raise ValueError('Embedded source manifest differs')
    return len(files)


class TraceEngine:
    def __init__(self, engine):
        self.engine = engine
        self.specification = engine.specification
        self.state_hash = hashlib.sha256()
        self.action_hash = hashlib.sha256()
        self.frames = 0
        self.transitions = 0
        self.status = None
        self.bank = None

    def interpreter(self, state, env):
        initial = not state[0].observation.get('farms')
        if not initial:
            self.action_hash.update(bytes.fromhex(digest([s.action for s in state])))
            self.transitions += 1
        result = self.engine.interpreter(state, env)
        self.state_hash.update(bytes.fromhex(digest({'state': state, 'info': env.info,
                                                    'configuration': env.configuration})))
        self.frames += 1
        self.status = [s.status for s in state]
        self.bank = [s.reward for s in state]
        return result


def run(args):
    root = args.root.resolve()
    members = authenticate(root, args.archive, args.manifest)
    engine_path = root/'checks/reference/engine'
    loader_path = root/'checks/reference/evaluator/loader.py'
    loader_source = loader_path.read_bytes()
    if blob_hash(loader_source) != SOURCE_BLOB:
        raise ValueError('Unexpected evaluator baseline')
    for name, pin in ENGINE_PINS.items():
        if blob_hash((engine_path/name).read_bytes()) != pin:
            raise ValueError(f'Unreviewed official engine {name}')
    baseline = load_bytes('_raw_native_loader_base', loader_source, loader_path)
    repaired = load_bytes('_raw_native_loader_fixed', repair_source(loader_source), loader_path)
    reference.BASE = baseline
    engine, _ = baseline.get_engine(engine_path)
    sys.path.insert(0, str(root))
    spec = importlib.util.spec_from_file_location('_raw_native_parent', root/'main.py')
    native = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = native
    spec.loader.exec_module(native)
    statuses, anomaly = Counter(), Counter()
    calls, max_seconds = 0, 0.0
    first_extra = None
    last_step = None

    def agent(obs, cfg):
        nonlocal calls, max_seconds, first_extra, last_step
        last_step = obs.step
        started = time.perf_counter()
        action = native.agent(obs, cfg)
        elapsed = time.perf_counter() - started
        max_seconds = max(elapsed, max_seconds)
        calls += 1
        instance = getattr(native, '_INSTANCE', None)
        status = getattr(instance, 'diagnostics', {}).get('status', 'absent')
        statuses[status] += 1
        if isinstance(action, dict):
            h = action.get('hands', [])
            excess = max(0, len(h)-len(obs.farms[args.seat]['hands'])) if isinstance(h,list) else 0
            if excess:
                anomaly['extra_hand_callbacks'] += 1
                anomaly['extra_hand_rows'] += excess
                if first_extra is None:
                    first_extra = {'step': obs.step, 'public_hands': len(obs.farms[args.seat]['hands']),
                                   'raw_hands': len(h), 'raw_action': action}
        return action

    agents = [lambda obs,cfg: engine.starter_agent(obs), lambda obs,cfg: engine.starter_agent(obs)]
    agents[args.seat] = agent
    traced = TraceEngine(engine)
    t0 = time.perf_counter()
    result, error, error_trace = None, None, None
    try:
        if args.arm == 'direct':
            result = direct_play(traced, agents, args.seed, {})
        else:
            result = (baseline if args.arm == 'legacy' else repaired).play(traced, agents, args.seed)
    except Exception as caught:
        error = {'type': type(caught).__name__, 'message': str(caught), 'step': last_step}
        error_trace = traceback.format_exc()
    unchanged = authenticate(root, args.archive, args.manifest) == members
    report = {
        'schema': 'titan.v4.offline-evaluator.raw-action.v1',
        'arm': args.arm, 'seed': args.seed, 'seat': args.seat,
        'python': platform.python_version(), 'optimization': sys.flags.optimize,
        'archive_sha256': ARCHIVE_SHA, 'manifest_sha256': MANIFEST_SHA,
        'authenticated_runtime_members': members, 'source_unchanged': unchanged,
        'loader_before_blob': SOURCE_BLOB, 'loader_after_blob': blob_hash(repair_source(loader_source)),
        'engine_pins': ENGINE_PINS, 'native_calls': calls, 'native_status_counts': dict(statuses),
        'observed_anomalies': dict(anomaly), 'first_surplus_hand_witness': first_extra,
        'action_trace_sha256': traced.action_hash.hexdigest(),
        'state_trace_sha256': traced.state_hash.hexdigest(),
        'official_interpreter_calls': traced.frames, 'completed_transitions': traced.transitions,
        'terminal_status': traced.status, 'terminal_bank': traced.bank,
        'error': error, 'error_traceback': error_trace,
        'complete': error is None and traced.status == ['DONE','DONE'] and statuses == Counter(completed=calls),
        'max_native_call_seconds': max_seconds, 'elapsed_seconds': time.perf_counter()-t0,
        'loader_report': result,
        'scope': 'Checked archive b567 vs official starter, evaluator parity only; NOT latest source-head/assembled V4/hosted or competitive EV proof',
        'promotion_authorized': False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
    print(json.dumps({key:report[key] for key in ('arm','seed','seat','optimization','complete','native_calls','observed_anomalies','error','terminal_bank','elapsed_seconds')}), flush=True)
    return 0 if report['complete'] else 2


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--archive', type=Path, required=True)
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--arm', choices=('legacy','fixed','direct'), required=True)
    p.add_argument('--seed', type=int, required=True)
    p.add_argument('--seat', type=int, choices=(0,1), required=True)
    p.add_argument('--output', type=Path, required=True)
    return run(p.parse_args())


if __name__ == '__main__':
    raise SystemExit(main())
