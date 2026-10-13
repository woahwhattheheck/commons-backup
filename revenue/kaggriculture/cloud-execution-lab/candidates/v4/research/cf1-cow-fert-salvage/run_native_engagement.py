# SPDX-License-Identifier: Apache-2.0
"""Run one read-only native-parent CF1 observation game in a fresh process.

No source fetch, policy activation, game-state intervention, or archive write.
The official starter is a coverage opponent, not leaderboard-strength evidence.
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import gzip
import importlib.util
import json
from pathlib import Path
import platform
import sys
import time

from engagement_probe import EngagementProbe, blob_hash, digest, summarize

ENGINE_PINS = {
    'kaggriculture.py': '3c202c7ee921da239356789e266b694635103fc4',
    'kaggriculture.json': 'b354d06b742fe48402513792253f1a5c29366b20',
    'utils.py': '91c8822ee6201ba4a5a8416c7dbe34f95dd61c87',
}
LOADER_PIN = '23948e10cfc3d32f46c9abb1321b0d8fc8db21d5'


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f'Cannot load {path}')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def validate_manifest(root: Path, manifest: dict) -> dict:
    """Bind the named parent payload; this does not establish GitHub freshness."""
    root = root.resolve()
    if not isinstance(manifest, dict) or not manifest:
        raise ValueError('Nonempty parent Git-blob manifest required')
    result = {}
    for relative, expected in manifest.items():
        if not isinstance(relative, str) or not isinstance(expected, str):
            raise ValueError('Invalid manifest entry')
        path = (root / relative).resolve()
        if Path(relative).is_absolute() or '..' in Path(relative).parts or not path.is_relative_to(root):
            raise ValueError('Manifest path escapes the parent root')
        if not path.is_file() or blob_hash(path.read_bytes()) != expected:
            raise ValueError(f'Parent source mismatch: {relative}')
        result[relative] = expected
    if not {'main.py', 'titan_runtime.py', 'TITAN-CONFIG.json'} <= result.keys():
        raise ValueError('Manifest lacks required parent entrypoint/runtime/config')
    # Include every runtime Python/JSON file, not just a convenient few pins.
    actual = {str(p.relative_to(root)) for p in root.rglob('*')
              if p.is_file() and p.suffix in ('.py', '.json')
              and 'checks' not in p.relative_to(root).parts}
    if actual != set(result):
        raise ValueError('Manifest does not cover the exact runtime Python/JSON payload')
    return dict(sorted(result.items()))


def run(args) -> dict:
    root, engine_path = args.parent_root.resolve(), args.engine.resolve()
    loader_path = args.loader.resolve()
    donor = Path(__file__).with_name('r04_cow_fert_salvage.py')
    manifest = validate_manifest(root, json.loads(args.manifest.read_text()))
    for name, expected in ENGINE_PINS.items():
        path = engine_path / name
        if not path.is_file() or blob_hash(path.read_bytes()) != expected:
            raise ValueError(f'Missing or mismatched official engine source: {name}')
    if blob_hash(loader_path.read_bytes()) != LOADER_PIN:
        raise ValueError('Unreviewed offline engine loader')
    if not 1 <= args.max_steps <= 720:
        raise ValueError('max-steps must be between 1 and 720')
    output = args.output.resolve()
    protected = [root, engine_path, loader_path.parent, donor.parent, args.manifest.resolve().parent]
    if any(output == p or output.is_relative_to(p) for p in protected):
        raise ValueError('Output must be outside all source/input directories')
    output.mkdir(parents=True, exist_ok=False)
    provenance = {
        'parent_manifest': manifest, 'parent_payload_sha256': digest(manifest),
        'engine_blobs': ENGINE_PINS, 'loader_blob': LOADER_PIN,
        'probe_blob': blob_hash(Path(__file__).with_name('engagement_probe.py').read_bytes()),
        'runner_blob': blob_hash(Path(__file__).read_bytes()),
        'python': platform.python_version(), 'optimization': sys.flags.optimize,
        'seed': args.seed, 'seat': args.seat, 'opponent': 'official_starter',
        'scope': 'Offline native-parent trajectory; not hosted or gauntlet-overlay validation',
    }
    (output / 'SOURCES.json').write_text(json.dumps(provenance, indent=2) + '\n')
    loader = load('_cf1_offline_loader', loader_path)
    engine, _ = loader.get_engine(engine_path)  # All sources prevalidated: no fetch path.
    sys.path.insert(0, str(root))
    parent = load('_cf1_native_parent', root / 'main.py')
    probe = EngagementProbe(donor)
    cfg = loader.Struct({key: value.get('default') if isinstance(value, dict) else value
                         for key, value in engine.specification['configuration'].items()})
    cfg.seed = args.seed
    env = loader.Struct(configuration=cfg, done=False, info={})
    state = [loader.Struct(observation=loader.Struct(), action={}, status='ACTIVE', reward=0)
             for _ in range(2)]
    engine.interpreter(state, env)
    rows, diagnostics, times = [], Counter(), []
    started = time.perf_counter()
    rowfile = output / 'callbacks.jsonl'
    eodfile = output / 'eod.jsonl.gz'
    # Persist the exact inputs needed to replay all eligible donor admissions.
    # Counterfactual proposals never become state.action.
    with rowfile.open('x') as log, eodfile.open('xb') as raw:
        with gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as fixtures:
            for step in range(args.max_steps):
                for seat, item in enumerate(state):
                    item.observation.step = step
                    visible = copy.deepcopy(item.observation)
                    before = time.perf_counter()
                    action = (parent.agent(copy.deepcopy(visible), cfg) if seat == args.seat
                              else engine.starter_agent(copy.deepcopy(visible)))
                    elapsed = time.perf_counter() - before
                    if not isinstance(action, dict):
                        raise TypeError('Agent did not return a dictionary')
                    if seat == args.seat:
                        times.append(elapsed)
                        row = probe.inspect(visible, cfg, action)
                        instance = getattr(parent, '_INSTANCE', None)
                        status = getattr(instance, 'diagnostics', {}).get('status', 'absent')
                        diagnostics[status] += 1
                        row['parent_status'] = status
                        rows.append(row)
                        log.write(json.dumps(row, sort_keys=True) + '\n')
                        if 0 <= step <= 695 and step % 24 == 23:
                            fixture = {'observation': visible, 'configuration': dict(cfg),
                                       'action': action, 'probe': row}
                            fixtures.write((json.dumps(fixture, sort_keys=True) + '\n').encode())
                    item.action = action  # Always the original parent's returned object.
                engine.interpreter(state, env)
                if any(item.status == 'DONE' for item in state):
                    env.done = True
                    break
    unchanged = validate_manifest(root, manifest) == manifest
    summary = summarize(rows)
    summary.update(
        seed=args.seed, seat=args.seat, opponent='official_starter',
        parent_payload_sha256=provenance['parent_payload_sha256'],
        parent_status_counts=dict(diagnostics),
        terminal_status=[item.status for item in state],
        terminal_cash=[item.reward for item in state],
        parent_sources_unchanged=unchanged,
        engine_sources_unchanged=all(blob_hash((engine_path / n).read_bytes()) == h for n, h in ENGINE_PINS.items()),
        executed_parent_actions=len(rows), executed_cf1_actions=0,
        actual_cf1_fertilizer_recovered=0,
        max_parent_call_seconds=max(times), elapsed_seconds=time.perf_counter()-started,
        callbacks_blob=blob_hash(rowfile.read_bytes()), eod_fixture_blob=blob_hash(eodfile.read_bytes()),
        donor_return_guards=probe.reasons,
        promotion_authorized=False,
    )
    if (summary['terminal_status'] != ['DONE', 'DONE'] or diagnostics != Counter(completed=len(rows))
            or not summary['engine_sources_unchanged'] or not unchanged):
        summary.update(complete=False, verdict='INCOMPLETE_OR_PARENT_FALLBACK')
    (output / 'RESULT.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps({k: summary[k] for k in ('seed', 'seat', 'callbacks', 'would_activate', 'verdict', 'parent_status_counts', 'elapsed_seconds')}), flush=True)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--parent-root', type=Path, required=True)
    parser.add_argument('--engine', type=Path, required=True)
    parser.add_argument('--loader', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--seed', type=int, required=True)
    parser.add_argument('--seat', type=int, choices=(0, 1), required=True)
    parser.add_argument('--max-steps', type=int, default=720)
    parser.add_argument('--output', type=Path, required=True)
    try:
        result = run(parser.parse_args())
    except Exception as error:
        print(f'CF1 evidence failed: {type(error).__name__}: {error}', file=sys.stderr)
        return 2
    return 0 if result['complete'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
