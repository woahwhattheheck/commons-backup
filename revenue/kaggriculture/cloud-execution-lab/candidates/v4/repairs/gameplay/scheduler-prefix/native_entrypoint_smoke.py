#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Bounded actual main.py::agent smoke on an authenticated native package.

Run each variant/seat in a fresh process. This is not a strength gate. A composed
package may differ from the exact base archive in ONLY the two generated files.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tarfile
import time

import compose_native_scheduler_prefix as composition
import test_native_scheduler_prefix as fixture

BASE_ARCHIVE_SHA256 = 'b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9'


def authenticate(package: Path, archive: Path, engine: Path, composed: bool) -> dict:
    if hashlib.sha256(archive.read_bytes()).hexdigest() != BASE_ARCHIVE_SHA256:
        raise ValueError('base archive identity mismatch')
    root = package.resolve()
    expected = {}
    with tarfile.open(archive) as handle:
        for member in handle.getmembers():
            if not member.isfile():
                raise ValueError('base archive must contain only regular files')
            path = Path(member.name)
            if path.is_absolute() or '..' in path.parts:
                raise ValueError('unsafe archive member')
            expected[member.name] = handle.extractfile(member).read()
    if len(expected) != 110:
        raise ValueError('expected 110 authenticated archive members')
    changed = {}
    if composed:
        changed, _ = composition.compose(expected['scheduler.py'], expected['frozen_selected.py'],
                                          engine.read_bytes())
        expected.update(changed)
    actual_names = {str(p.relative_to(root)) for p in root.rglob('*')
                    if p.is_file() and '__pycache__' not in p.parts}
    if actual_names != set(expected):
        raise ValueError('package member inventory mismatch')
    for name, data in expected.items():
        path = root / name
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError('package member alias: ' + name)
        if path.read_bytes() != data:
            raise ValueError('package member bytes differ: ' + name)
    return {'base_archive_sha256': BASE_ARCHIVE_SHA256,
            'members_verified': len(expected), 'composed': composed,
            'changed_blobs': {name: composition.git_blob(data) for name, data in changed.items()}}


def run(package: Path, archive: Path, engine_dir: Path, *, seat: int = 0,
        seed: int = 94127, steps: int = 32, composed: bool = False) -> dict:
    if seat not in (0, 1) or not 1 <= steps <= 719:
        raise ValueError('seat must be 0/1 and steps must be in [1,719]')
    identity = authenticate(package, archive, engine_dir / 'kaggriculture.py', composed)
    fixture.ENGINE_DIR = engine_dir
    engine = fixture.official_engine()
    S = fixture.Struct
    cfg = S({k: v.get('default') if isinstance(v, dict) else v
             for k, v in engine.specification['configuration'].items()})
    cfg.seed = seed
    state = [S(observation=S(), action={}, status='ACTIVE', reward=0) for _ in range(2)]
    env = S(configuration=cfg, done=False, info={})
    engine.interpreter(state, env)
    root = package.resolve()
    sys.path.insert(0, str(root))
    spec = importlib.util.spec_from_file_location('_ridge_native_entrypoint', root / 'main.py')
    entry = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(entry)
    rows = []
    for step in range(steps):
        for player, current in enumerate(state):
            current.observation.step = step
            if player != seat:
                current.action = engine.starter_agent(copy.deepcopy(current.observation))
                continue
            started = time.perf_counter()
            current.action = entry.agent(copy.deepcopy(current.observation), cfg)
            elapsed = time.perf_counter() - started
            instance = entry._INSTANCE
            consumer = getattr(instance, 'consumer', None)
            diagnostics = dict(getattr(instance, 'diagnostics', {}) or {})
            rows.append({'step': step, 'action': current.action,
                         'status': diagnostics.get('status', 'no_instance'),
                         'parent_calls': diagnostics.get('parent_calls'),
                         'consumer': None if consumer is None else
                                     type(consumer).__module__ + '.' + type(consumer).__name__,
                         'pending': copy.deepcopy(getattr(consumer, 'pending', None)),
                         'elapsed_seconds': elapsed})
        engine.interpreter(state, env)
        if any(s.status == 'DONE' for s in state):
            break
    behavioral = [{k: v for k, v in row.items() if k != 'elapsed_seconds'} for row in rows]
    return {'identity': identity, 'seed': seed, 'seat': seat, 'steps_requested': steps,
            'steps_executed': len(rows), 'rows': rows,
            'behavior_sha256': hashlib.sha256(json.dumps(behavioral, sort_keys=True).encode()).hexdigest(),
            'deadline_or_incomplete_calls': sum(row['status'] != 'completed' for row in rows),
            'max_call_seconds': max(row['elapsed_seconds'] for row in rows),
            'money': [f['money'] for f in state[0].observation.farms],
            'episode_completed': all(s.status == 'DONE' for s in state),
            'strength_claim': False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--base-archive', type=Path, required=True)
    parser.add_argument('--engine-dir', type=Path, required=True)
    parser.add_argument('--composed', action='store_true')
    parser.add_argument('--seat', type=int, choices=(0, 1), default=0)
    parser.add_argument('--seed', type=int, default=94127)
    parser.add_argument('--steps', type=int, default=32)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(args.package.resolve()):
        parser.error('receipt must be outside the authenticated package')
    if args.output.exists() or args.output.is_symlink():
        parser.error('receipt output must be fresh')
    report = run(args.package, args.base_archive, args.engine_dir, seat=args.seat,
                 seed=args.seed, steps=args.steps, composed=args.composed)
    with args.output.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'rows'}, sort_keys=True))


if __name__ == '__main__':
    main()
