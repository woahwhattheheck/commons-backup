# SPDX-License-Identifier: Apache-2.0
"""Serial whole-native-game identity/disabled wiring controls, not sellby15 EV.

Consumes HARVESTCLOCK's SAME full-engine observer. No alternative transition or
fill implementation. Complete returned-action traces and journals are retained.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import sys
import tarfile
import time

from native_sale_window import NativeSaleWindow, digest

ARCHIVE_SHA256 = 'b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9'
ORACLE_GIT_BLOB = '20e623722fbb3f8a9cdb71add009a9f68756819d'


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def identity_control(obs, cfg, action):
    """Intentionally identical: this callback makes no gameplay proposal."""
    return action


def authenticate(root, archive):
    actual = hashlib.sha256(archive.read_bytes()).hexdigest()
    if actual != ARCHIVE_SHA256:
        raise ValueError('Unexpected native reference archive')
    manifest = {}
    with tarfile.open(archive) as source:
        for member in source:
            if not member.isfile():
                continue
            target = (root / member.name).resolve()
            if root not in target.parents:
                raise ValueError('Archive member outside runtime root')
            expected = source.extractfile(member).read()
            if target.read_bytes() != expected:
                raise ValueError('Native runtime byte mismatch: ' + member.name)
            manifest[member.name] = hashlib.sha256(expected).hexdigest()
    return {'archive_sha256': actual, 'authenticated_files': len(manifest),
            'member_manifest_sha256': digest(manifest)}


def run(args):
    root, reference = args.native.resolve(), args.reference.resolve()
    binding = authenticate(root, args.archive.resolve())
    oracle_path = Path(__file__).with_name('sale_window.py')
    data = oracle_path.read_bytes()
    if hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() != ORACLE_GIT_BLOB:
        raise ValueError('HARVESTCLOCK oracle identity changed; revalidate before use')
    oracle = load(oracle_path, '_native_wiring_shared_oracle')
    sys.path.insert(0, str(root))
    engine, S = oracle.load_engine(reference)
    native = load(root / 'main.py', '_native_wiring_main')
    trial = None
    if args.mode == 'baseline':
        agent = native.agent
    else:
        trial = NativeSaleWindow(native, identity_control, enabled=args.mode == 'identity',
                                 label='IDENTITY wiring control; not historical sellby15')
        agent = trial.agent
    random.seed(20260907)
    state, env = oracle.initialize(engine, S, seed=args.seed)
    cfg = env.configuration
    if cfg.seed is not None:
        raise ValueError('Environment seed must not be exposed to the agent')
    trace, realized, elapsed = [], [], []
    statuses = {}
    started = time.perf_counter()
    result = {'schema': 'titan.sale_window.native_wiring.v1', 'mode': args.mode,
              'seed': args.seed, 'seat': args.seat, 'native': binding,
              'oracle_git_blob': ORACLE_GIT_BLOB, 'status': 'incomplete',
              'policy_custody': 'historical sellby15 unavailable; identity callback only',
              'trace': trace, 'realized': realized, 'errors': [], 'optimized_python': not __debug__}
    try:
        for step in range(cfg.episodeSteps):
            actions = []
            for seat in (0, 1):
                obs = deepcopy(state[seat].observation)
                obs.step = step
                obs.remainingOverageTime = 0
                if seat == args.seat:
                    begin = time.perf_counter()
                    action = agent(obs, deepcopy(cfg))
                    elapsed.append(time.perf_counter() - begin)
                    diagnostics = getattr(native._INSTANCE, 'diagnostics', {}) or {}
                    key = diagnostics.get('status', 'instance_absent')
                    statuses[key] = statuses.get(key, 0) + 1
                else:
                    action = engine.starter_agent(obs)
                if not isinstance(action, dict):
                    raise TypeError('Agent did not return an action dict')
                actions.append(action)
            report = oracle.observed_step(engine, state, env, actions, step)
            realized.append(report)
            trace.append({'step': step, 'actions': deepcopy(actions),
                          'state_sha256': digest([s.observation for s in state]),
                          'bank': [state[0].observation.farms[i]['money'] for i in (0, 1)]})
            if all(s.status == 'DONE' for s in state):
                result.update(status='complete', scores=[s.reward for s in state])
                break
    except Exception as error:
        result['status'] = 'error'
        result['errors'].append(type(error).__name__ + ': ' + str(error))
    finally:
        result.update(steps=len(trace), trace_sha256=digest(trace), native_status_counts=statuses,
                      max_native_seconds=max(elapsed, default=0),
                      wall_seconds=time.perf_counter() - started)
        if trial is not None:
            result['native_seam_binding'] = trial.native_binding
            result['callback_binding'] = trial.policy_binding
            result['journal'] = trial.rows
        args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k not in
                      ('trace', 'journal', 'realized')}, sort_keys=True), flush=True)
    return 0 if result['status'] == 'complete' else 2


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--native', type=Path, required=True)
    p.add_argument('--reference', type=Path, required=True)
    p.add_argument('--archive', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--seed', type=int, default=17)
    p.add_argument('--seat', type=int, choices=(0, 1), default=0)
    p.add_argument('--mode', choices=('baseline', 'disabled', 'identity'), required=True)
    raise SystemExit(run(p.parse_args()))
