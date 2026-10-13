# SPDX-License-Identifier: Apache-2.0
"""Run source-pinned, config-only current-native TITAN ablations.

Research only: uses the existing process-isolated official-engine evaluator.
Each job captures the complete authenticated package once, materializes those
bytes into a private frozen tree, and executes only that tree. The unchanged
literal package entrypoint is always the rival. No external network, hosted
runs, production changes, or learned policy.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import gzip
import hashlib
import importlib.util
import json
import math
from pathlib import Path, PurePosixPath
import statistics
import subprocess
import sys
import tempfile
from typing import Any

SOURCE_SHA256 = 'e87d70dd3bcf5aea1e929f1a5dbdc86f3cc33d8a0b3492986f2970fc8e774be2'
ARCHIVE_SHA256 = 'b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9'
FEATURES = ('seed', 'funding', 'committed', 'redundant_hire', 'market_pressure',
            'operating_stock', 'idle_fertilizer', 'crop_release', 'early_capital')


def encoded(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_bytes(encoded(value) + b'\n')


def _safe_runtime_member(relative: Any) -> str:
    if not isinstance(relative, str) or not relative or '\\' in relative:
        raise ValueError(f'Unsafe package member: {relative!r}')
    path = PurePosixPath(relative)
    if path.is_absolute() or path.as_posix() != relative or any(
            part in ('', '.', '..') for part in path.parts):
        raise ValueError(f'Unsafe package member: {relative!r}')
    return relative


def capture_package(root: Path) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Authenticate and capture SOURCE plus every declared runtime byte once."""
    root = root.resolve(strict=True)
    raw = (root / 'SOURCE.json').read_bytes()
    if digest(raw) != SOURCE_SHA256:
        raise ValueError('Wrong current-native source manifest; do not label a partial artifact current')
    manifest = json.loads(raw)
    runtime = manifest.get('runtime')
    if type(runtime) is not dict or len(runtime) != 109:
        raise ValueError('Incomplete declared runtime closure')
    declared = {_safe_runtime_member(relative) for relative in runtime}
    allowed = declared | {'SOURCE.json'}
    extras = [str(p.relative_to(root)) for p in root.rglob('*')
              if p.is_file() and '__pycache__' not in p.parts
              and str(p.relative_to(root)) not in allowed]
    if extras:
        raise ValueError(f'Undeclared package files: {extras[:5]}')

    captured: dict[str, bytes] = {'SOURCE.json': raw}
    for relative, pin in runtime.items():
        relative = _safe_runtime_member(relative)
        if type(pin) is not dict or set(pin) < {'bytes', 'sha256'}:
            raise ValueError(f'Incomplete package pin: {relative}')
        path = root / relative
        if path.is_symlink() or not path.resolve(strict=True).is_relative_to(root):
            raise ValueError(f'Unsafe package member: {relative}')
        data = path.read_bytes()
        if len(data) != pin['bytes'] or digest(data) != pin['sha256']:
            raise ValueError(f'Package mismatch: {relative}')
        captured[relative] = data

    config_raw = captured.get('TITAN-CONFIG.json')
    if config_raw is None:
        raise ValueError('Authenticated runtime is missing TITAN-CONFIG.json')
    config = json.loads(config_raw)
    if any(config.get(feature) is not True for feature in FEATURES):
        raise ValueError('Requested ablation is not enabled in the authenticated baseline')
    pins = {'source_manifest_sha256': SOURCE_SHA256,
            'archive_sha256': ARCHIVE_SHA256, 'runtime_files': 109,
            'default_config': config,
            'capture_sha256': digest(encoded({name: digest(data)
                                               for name, data in sorted(captured.items())}))}
    return pins, captured


def verify_package(root: Path) -> dict[str, Any]:
    """Compatibility verifier; execution callers should retain capture_package bytes."""
    return capture_package(root)[0]


def materialize_capture(destination: Path, captured: dict[str, bytes]) -> None:
    """Write only previously authenticated buffers into a new private tree."""
    destination.mkdir(parents=True, exist_ok=False)
    for relative, data in captured.items():
        relative = 'SOURCE.json' if relative == 'SOURCE.json' else _safe_runtime_member(relative)
        target = destination / PurePosixPath(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def wrapper_text(root: Path, feature: str | None) -> str:
    if feature is not None and feature not in FEATURES:
        raise ValueError(f'Unsupported one-feature intervention: {feature!r}')
    overrides = {} if feature is None else {feature: False}
    return f'''# Generated diagnostic wrapper; not a production entrypoint.
from pathlib import Path
import importlib.util
import sys
ROOT = Path({str(root.resolve())!r})
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('_ablation_exact_parent', ROOT / 'main.py')
parent = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = parent
spec.loader.exec_module(parent)
original_constructor = parent._new_instance
OVERRIDES = {overrides!r}
def constructor(root, feature_data):
    return original_constructor(root, dict(feature_data, **OVERRIDES))
parent._new_instance = constructor
agent = parent.agent
'''


def make_plan(seeds: list[int], features: list[str]) -> list[dict[str, Any]]:
    if not seeds or any(type(seed) is not int for seed in seeds) or len(set(seeds)) != len(seeds):
        raise ValueError('Use distinct integer environment seeds')
    if not features or len(set(features)) != len(features) or any(f not in FEATURES for f in features):
        raise ValueError('Use distinct supported feature names')
    rows = []
    for variant in ['base', 'sham', *features]:
        for seed in seeds:
            for seat in (0, 1):
                rows.append({'id': f'{variant}-{seed}-{seat}', 'variant': variant,
                             'seed': seed, 'candidate_seat': seat})
    return rows


class TraceEngine:
    """Pass-through observer: never normalizes/truncates actions or observations."""
    def __init__(self, engine: Any):
        self.engine = engine
        self.actions: list[list[dict[str, Any]]] = []

    def __getattr__(self, name: str) -> Any:
        return getattr(self.engine, name)

    def interpreter(self, state: Any, env: Any) -> Any:
        if state and state[0].observation.get('farms'):
            self.actions.append(json.loads(encoded([row.action for row in state])))
        return self.engine.interpreter(state, env)


def run_job(job: dict[str, Any]) -> dict[str, Any]:
    source_root = Path(job['root']).resolve(strict=True)
    pins, captured = capture_package(source_root)
    with tempfile.TemporaryDirectory(prefix='titan-native-ablation-') as td:
        private = Path(td)
        root = private / 'package'
        materialize_capture(root, captured)
        evaluator = root / 'checks/reference/evaluator/evaluate.py'
        loader = root / 'checks/reference/evaluator/loader.py'
        cache = root / 'checks/reference/engine'
        spec = importlib.util.spec_from_file_location('_ablation_evaluator', evaluator)
        if spec is None or spec.loader is None:
            raise ValueError('Evaluator cannot be imported')
        ev = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = ev
        spec.loader.exec_module(ev)
        engine, hashes = ev.get_engine(cache, loader)
        proxy = TraceEngine(engine)

        variant = job['variant']
        if variant == 'base':
            candidate = root / 'main.py'
            candidate_bytes = captured['main.py']
        else:
            feature = None if variant == 'sham' else variant
            candidate = private / f'{variant}.py'
            candidate_bytes = wrapper_text(root, feature).encode()
            candidate.write_bytes(candidate_bytes)
        rival = str(root / 'main.py')
        seat = job['candidate_seat']
        specs = [str(candidate), rival] if seat == 0 else [rival, str(candidate)]
        result = ev.play(proxy, specs, cache, loader, job['seed'], seat,
                         rng_seed=20260907, action_timeout=1.0,
                         startup_timeout=10.0, game_timeout=120.0)
        result.update(id=job['id'], variant=variant,
                      seed=job['seed'], candidate_seat=seat,
                      opponent='literal-current-native',
                      evaluator_sha256=digest(captured['checks/reference/evaluator/evaluate.py']),
                      engine_sha256=hashes,
                      source_manifest_sha256=SOURCE_SHA256,
                      package_capture_sha256=pins['capture_sha256'],
                      candidate_entry_sha256=digest(candidate_bytes))
        result['action_sha256'] = digest(encoded(proxy.actions))
        result['recorded_action_callbacks'] = len(proxy.actions)
        result['unit_verbs'] = []
        result['market_verbs'] = []
        for player in (0, 1):
            units, market = Counter(), Counter()
            for pair in proxy.actions:
                action = pair[player]
                for row in [action.get('farmer', []), *action.get('hands', [])]:
                    if isinstance(row, list) and row:
                        units[str(row[0])] += 1
                for row in action.get('market', []):
                    if isinstance(row, list) and row:
                        market[str(row[0])] += 1
            result['unit_verbs'].append(dict(units))
            result['market_verbs'].append(dict(market))
        tape = Path(job['tape'])
        tape.write_bytes(gzip.compress(encoded(proxy.actions), mtime=0))
        result['tape_sha256'] = digest(tape.read_bytes())
        result['tape_file'] = tape.name
        return result


def run_child(job: dict[str, Any], directory: Path) -> dict[str, Any]:
    job_path = directory / f"{job['id']}.job.json"
    result_path = directory / f"{job['id']}.json"
    write_json(job_path, job)
    proc = subprocess.run([sys.executable, '-B', str(Path(__file__).resolve()),
                           '--job', str(job_path), '--result', str(result_path)],
                          capture_output=True, text=True, timeout=150, check=False)
    if proc.returncode or not result_path.exists():
        result = {k: job[k] for k in ('id', 'variant', 'seed', 'candidate_seat')}
        result.update(status='failed', failure={'kind': 'driver_failure',
                      'returncode': proc.returncode, 'stderr': proc.stderr[-3000:]})
        write_json(result_path, result)
        return result
    return json.loads(result_path.read_bytes())


def _bind_results_to_plan(plan: list[dict[str, Any]], results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    expected = {row['id']: row for row in plan}
    by_id = {row.get('id'): row for row in results}
    if len(expected) != len(plan):
        raise ValueError('Duplicate planned game ids')
    if len(by_id) != len(results) or set(by_id) != set(expected):
        raise ValueError('Missing, duplicate or unplanned game results')
    for result_id, result in by_id.items():
        planned = expected[result_id]
        for field in ('variant', 'seed', 'candidate_seat'):
            actual = result.get(field)
            wanted = planned[field]
            if type(actual) is not type(wanted) or actual != wanted:
                raise ValueError(
                    f'Result coordinates disagree with PLAN for {result_id}: {field}'
                )
    return by_id


def paired_report(plan: list[dict[str, Any]], results: list[dict[str, Any]], tapes: Path) -> dict[str, Any]:
    _bind_results_to_plan(plan, results)
    baseline = {(r['seed'], r['candidate_seat']): r for r in results if r['variant'] == 'base'}
    sham, pairs, failures = [], [], []
    for row in results:
        if row['variant'] == 'base':
            if row['status'] != 'complete':
                failures.append(row['id'])
            continue
        base = baseline[row['seed'], row['candidate_seat']]
        if row['status'] != 'complete' or base['status'] != 'complete':
            failures.append(row['id'])
            continue
        seat = row['candidate_seat']
        if row.get('recorded_action_callbacks') != 719 or base.get('recorded_action_callbacks') != 719:
            raise ValueError('Incomplete full-game action trace')
        same = row['trace_sha256'] == base['trace_sha256'] and row['scores'] == base['scores']
        if row['variant'] == 'sham':
            sham.append({'id': row['id'], 'same_trace_and_scores': same,
                         'same_actions': row['action_sha256'] == base['action_sha256']})
            continue
        own = row['scores'][seat] - base['scores'][seat]
        rival = row['scores'][1-seat] - base['scores'][1-seat]
        a = json.loads(gzip.decompress((tapes / base['tape_file']).read_bytes()))
        b = json.loads(gzip.decompress((tapes / row['tape_file']).read_bytes()))
        changed = [i for i, (left, right) in enumerate(zip(a, b)) if left[seat] != right[seat]]
        first = changed[0] if changed else None
        pairs.append({'id': row['id'], 'feature_disabled': row['variant'], 'seed': row['seed'],
                      'seat': seat, 'delta_own': own, 'delta_rival': rival,
                      'delta_margin': own-rival, 'changed_candidate_callbacks': len(changed),
                      'first_changed_callback': first,
                      'first_base_action': a[first][seat] if first is not None else None,
                      'first_off_action': b[first][seat] if first is not None else None,
                      'same_full_trace': same})
    summary = {}
    for name in sorted({r['variant'] for r in results} - {'base', 'sham'}):
        rows = [p for p in pairs if p['feature_disabled'] == name]
        changes = [r['delta_margin'] for r in rows]
        summary[name] = {'complete_pairs': len(rows),
            'scheduled_pairs': sum(r['variant'] == name for r in plan),
            'mean_delta_own': statistics.mean(r['delta_own'] for r in rows) if rows else None,
            'mean_delta_rival': statistics.mean(r['delta_rival'] for r in rows) if rows else None,
            'mean_delta_margin': statistics.mean(changes) if rows else None,
            'min_delta_margin': min(changes, default=None),
            'max_delta_margin': max(changes, default=None),
            'positive_zero_negative': [sum(v > 0 for v in changes), sum(v == 0 for v in changes), sum(v < 0 for v in changes)],
            'changed_candidate_callbacks': sum(r['changed_candidate_callbacks'] for r in rows)}
    return {'schema': 'titan-native-ablation-v1', 'source_manifest_sha256': SOURCE_SHA256,
            'archive_sha256': ARCHIVE_SHA256,
            'interpretation': 'OFF minus full baseline: positive delta means removing the feature helped this self-play cell.',
            'scope': 'Current native production package self-play, not composed V4 field strength or a default-change recommendation.',
            'seed_dependency': 'Disabling seed also bypasses the dependent funding application; funding=False isolates only funding.',
            'scheduled_games': len(plan), 'completed_games': sum(r['status'] == 'complete' for r in results),
            'failed_or_unpaired_ids': failures, 'sham_controls': sham,
            'sham_control_gate': len(sham) == sum(r['variant'] == 'sham' for r in plan)
                and bool(sham) and all(x['same_trace_and_scores'] and x['same_actions'] for x in sham),
            'summary': summary, 'pairs': pairs}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--seeds', default='9923101,9923102,9923103,9923104')
    parser.add_argument('--features', default=','.join(FEATURES))
    parser.add_argument('--workers', type=int, default=2)
    parser.add_argument('--job', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--result', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.job:
        if args.result is None:
            parser.error('--result is required with --job')
        write_json(args.result, run_job(json.loads(args.job.read_bytes())))
        return 0
    if args.root is None or args.output is None:
        parser.error('--root and --output are required')
    if not 1 <= args.workers <= 4:
        parser.error('--workers must be between 1 and 4')
    pins = verify_package(args.root)
    plan = make_plan([int(x.strip()) for x in args.seeds.split(',')], args.features.split(','))
    if args.output.resolve().is_relative_to(args.root.resolve()):
        parser.error('--output must not be inside the authenticated package')
    args.output.mkdir(parents=True, exist_ok=False)
    directory = args.output.resolve()
    root = args.root.resolve()
    write_json(directory / 'PLAN.json', {'plan': plan, 'pins': pins, 'rng_seed': 20260907,
        'limits': {'rpc_seconds': 1.0, 'game_seconds': 120.0},
        'runner_sha256': digest(Path(__file__).read_bytes()), 'python': sys.version})
    jobs = [dict(row, root=str(root), tape=str(directory / (row['id'] + '.actions.json.gz')))
            for row in plan]
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_child, job, directory): job for job in jobs}
        for future in as_completed(futures):
            job = futures[future]
            try:
                result = future.result()
            except Exception as error:
                result = dict(job, status='failed', failure={'kind': 'supervisor', 'error': repr(error)})
                write_json(directory / (job['id'] + '.json'), result)
            results.append(result)
            print(json.dumps({k: result.get(k) for k in ('id','status','scores','failure')}, allow_nan=False), flush=True)
    order = {row['id']: index for index, row in enumerate(plan)}
    results.sort(key=lambda r: order[r['id']])
    report = paired_report(plan, results, directory)
    write_json(directory / 'RESULTS.json', results)
    write_json(directory / 'REPORT.json', report)
    verify_package(root)
    print(json.dumps({'summary': report['summary'], 'sham_control_gate': report['sham_control_gate']}, indent=2), flush=True)
    return int(bool(report['failed_or_unpaired_ids']) or not report['sham_control_gate'])


if __name__ == '__main__':
    raise SystemExit(main())
