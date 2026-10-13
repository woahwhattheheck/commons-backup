#!/usr/bin/env python3
"""Compare cold actor scheduling on one retained input, without running games.

The existing evaluator Actor owns the unchanged 10-second startup and 1-second
action RPC deadlines. Every sample starts a fresh interpreter; the SciPy bank's
first call includes its normal optional imports. Nothing is prewarmed in workers.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import statistics
import sys
import time

from prepare_bank import prepare

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
EVALUATOR = ROOT / 'cloud-eval/evaluate.py'
RNG_SEED = 20260908  # Existing evaluator's default opponent RNG, not a game seed.


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                   allow_nan=False).encode()).hexdigest()


def read_cgroup(name):
    path = Path('/sys/fs/cgroup') / name
    return path.read_text().strip() if path.exists() else None


def load_evaluator():
    spec = importlib.util.spec_from_file_location('cold_start_existing_evaluator', EVALUATOR)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def sample(evaluator, bank, case, index, origin, interval):
    scheduled = origin + index * interval
    remaining = scheduled - time.perf_counter()
    if remaining > 0:
        time.sleep(remaining)
    row = {'index': index, 'scheduled_start_offset_s': index * interval,
           'actual_start_offset_s': time.perf_counter() - origin}
    actor = None
    started = time.perf_counter()
    try:
        # These path arguments are unused by this bank actor. No engine loader
        # is invoked and no game is initialized by constructing or calling it.
        actor = evaluator.Actor(str(bank / 'lonespear-v18-scipy.py'),
                                ROOT / 'cloud-execution-lab/reference/engine',
                                evaluator.LOADER, RNG_SEED, startup_timeout=10.0)
        row['process_to_ready_seconds'] = time.perf_counter() - started
        row['ready'] = deepcopy(actor.ready)
        if actor.ready.get('kind') != 'ready':
            row['response'] = deepcopy(actor.ready)
        else:
            row['action_request_offset_s'] = time.perf_counter() - origin
            row['response'] = actor.act(case['observation'], case['configuration'], 1.0)
        row['response_offset_s'] = time.perf_counter() - origin
    except Exception as exc:
        row['response'] = {'kind': 'harness_error', 'error': f'{type(exc).__name__}: {exc}'}
    finally:
        if actor is not None:
            actor.close()
            row['stats'] = deepcopy(actor.stats)
        row['closed_offset_s'] = time.perf_counter() - origin
    response = row['response']
    if response.get('kind') == 'action':
        row['action_sha256'] = canonical_digest(response['action'])
        row['expected_action_match'] = (None if case.get('expected_action') is None
                                        else response['action'] == case['expected_action'])
    return row


def run_cohort(evaluator, bank, case, workers, interval, repeat):
    origin = time.perf_counter() + 0.05
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(sample, evaluator, bank, case, index, origin, interval)
                   for index in range(workers)]
        rows = [future.result() for future in futures]
    return {'workers': workers, 'start_interval_s': interval, 'repeat': repeat,
            'response_wall_seconds': max(row.get('response_offset_s', row['closed_offset_s'])
                                         for row in rows),
            'wall_seconds_including_close': max(row['closed_offset_s'] for row in rows),
            'samples': rows}


def summarize(cohorts):
    summary = {}
    for cohort in cohorts:
        key = f"workers={cohort['workers']};interval={cohort['start_interval_s']:g}"
        summary.setdefault(key, []).append(cohort)
    result = {}
    for key, groups in summary.items():
        rows = [row for group in groups for row in group['samples']]
        good = [row for row in rows if row['response'].get('kind') == 'action']
        kinds = {}
        for row in rows:
            kind = row['response'].get('kind', 'missing')
            if kind == 'action' and row.get('expected_action_match') is False:
                kind = 'action_mismatch'
            kinds[kind] = kinds.get(kind, 0) + 1
        result[key] = {'samples': len(rows), 'completed_first_actions': len(good), 'kinds': kinds,
                       'cohort_wall_seconds': [g['wall_seconds_including_close'] for g in groups],
                       'total_wall_seconds': sum(g['wall_seconds_including_close'] for g in groups),
                       'all_complete_action_hashes': sorted({r['action_sha256'] for r in good})}
        result[key]['completed_first_actions_per_minute'] = (
            60 * len(good) / result[key]['total_wall_seconds'])
        for name, values in (
            ('process_to_ready', [r['process_to_ready_seconds'] for r in rows
                                  if 'process_to_ready_seconds' in r]),
            ('first_rpc', [r['stats']['rpc_seconds'][0] for r in rows
                           if r.get('stats', {}).get('rpc_seconds')]),
            ('completed_first_call', [r['response']['call_seconds'] for r in good])):
            if values:
                result[key][name + '_median_s'] = statistics.median(values)
                result[key][name + '_max_s'] = max(values)
    return result


def summarize_only(source, output):
    """Relabel retained v1 samples without importing or calling any actor."""
    raw = json.loads(source.read_text())
    snapshot = source.parent / 'evidence/benchmark-measured.py.txt'
    if digest(snapshot) != raw['source']['benchmark']:
        raise ValueError('Measured benchmark snapshot does not match its recorded source')
    if not str(raw['input_provenance'].get('expected_scipy_action', '')).startswith('not retained'):
        raise ValueError('This v1 relabel requires the explicit no-expected-action provenance')
    cohorts = deepcopy(raw['cohorts'])
    for cohort in cohorts:
        for row in cohort['samples']:
            row.pop('matches_expected_action', None)
            if row['response'].get('kind') == 'action':
                row['expected_action_match'] = None
    hashes = sorted({row['action_sha256'] for cohort in cohorts for row in cohort['samples']
                     if row['response'].get('kind') == 'action'})
    result = {'schema': 'titan.widefield.cold-scheduling-summary.v2',
              'derived_from': str(source), 'derived_from_sha256': digest(source),
              'executed_source_snapshot': str(snapshot),
              'executed_benchmark_sha256': raw['source']['benchmark'],
              'postprocessing_source_sha256': digest(__file__),
              'postprocessing_note': 'Labels only; no new actor calls, engine imports or timing measurements',
              'postrun_source_metadata': {
                  'prepare_input_sha256': digest(HERE / 'prepare_input.py'),
                  'loader_argument_sha256': digest(ROOT / '20260907-offline-agent/evaluate.py'),
                  'note': 'These additional file digests were read after timing; no pre-run equivalence claim. '
                          'The bank actor uses its separately verified contract; the evaluator loader argument '
                          'is only used for official_starter and was not loaded by this target.'},
              'summary': summarize(cohorts),
              'cross_scheduling_action_parity': {
                  'completed_action_hashes': hashes, 'all_returned_actions_identical': len(hashes) == 1,
                  'historical_expected_action_available': False, 'engine_legality_checked': False},
              'interpretation': 'Completed means an action response from the existing Actor protocol; '
                                'neither historical correspondence nor engine legality is established',
              'environment': raw['environment'], 'input_provenance': raw['input_provenance'],
              'measurement_sources_unchanged': raw['sources_unchanged'],
              'measurement_bank_unchanged': raw['bank_unchanged'],
              'cohorts': len(cohorts), 'fresh_process_samples': sum(len(c['samples']) for c in cohorts)}
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(output)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps(result['summary'], indent=2, sort_keys=True))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bank', type=Path)
    parser.add_argument('--input', type=Path,
                        help='Retained observation/configuration with provenance, optional expected_action')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--summarize-only', type=Path,
                        help='Derive corrected v1 labels from existing samples; no actor or policy calls')
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--stagger-seconds', type=float, default=0.25)
    args = parser.parse_args()
    if args.summarize_only:
        return summarize_only(args.summarize_only, args.output)
    if args.bank is None or args.input is None:
        parser.error('--bank and --input are required for a measurement')
    if not 1 <= args.repeats <= 10 or not math.isfinite(args.stagger_seconds) or not 0 < args.stagger_seconds <= 2:
        parser.error('repeats must be 1..10; stagger-seconds must be in (0,2]')
    case = json.loads(args.input.read_text())
    if (not isinstance(case.get('configuration'), dict)
            or not isinstance(case.get('provenance'), dict)
            or not case['provenance']
            or case.get('observation', {}).get('step') != 0):
        parser.error('a provenance-bound retained step-zero observation/configuration is required')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        parser.error('output already exists; choose another path to retain previous measurements')
    bank_receipt = prepare(args.bank)
    evaluator = load_evaluator()
    source_before = {'evaluator': digest(EVALUATOR), 'benchmark': digest(__file__),
                     'loader_argument': digest(evaluator.LOADER),
                     'prepare_bank': digest(HERE / 'prepare_bank.py'),
                     'prepare_input': digest(HERE / 'prepare_input.py'), 'input': digest(args.input)}
    environment = {'python': sys.version, 'platform': platform.platform(),
                   'affinity_cpus': sorted(os.sched_getaffinity(0)),
                   'cgroup_cpu_max': read_cgroup('cpu.max'),
                   'cgroup_memory_max': read_cgroup('memory.max'),
                   'numpy': importlib.metadata.version('numpy'),
                   'scipy': importlib.metadata.version('scipy')}
    configurations = [(1, 0.0), (2, 0.0), (4, 0.0), (4, args.stagger_seconds)]
    report = {'schema': 'titan.widefield.cold-scheduling.v1',
              'started_at_utc': datetime.now(timezone.utc).isoformat(),
              'environment': environment, 'source': source_before,
              'bank_receipt': bank_receipt, 'input_provenance': case['provenance'],
              'agent_rng_seed': RNG_SEED, 'game_initializations': 0,
              'engine_transitions': 0, 'startup_deadline_s': 10.0,
              'action_rpc_deadline_s': 1.0,
              'scope': 'Retained first-input runtime workload; not games, held evidence, or hosted timing',
              'cohorts': []}
    for repeat in range(args.repeats):
        # Rotate configuration order across rounds to expose simple order drift.
        order = configurations[repeat % len(configurations):] + configurations[:repeat % len(configurations)]
        for workers, interval in order:
            cohort = run_cohort(evaluator, args.bank.resolve(), case, workers, interval, repeat)
            report['cohorts'].append(cohort)
            report['summary'] = summarize(report['cohorts'])
            args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
            print(json.dumps({'repeat': repeat, 'workers': workers, 'interval': interval,
                              'kinds': [r['response']['kind'] for r in cohort['samples']]}), flush=True)
    source_after = {'evaluator': digest(EVALUATOR), 'benchmark': digest(__file__),
                    'loader_argument': digest(evaluator.LOADER),
                    'prepare_bank': digest(HERE / 'prepare_bank.py'),
                    'prepare_input': digest(HERE / 'prepare_input.py'), 'input': digest(args.input)}
    report['sources_unchanged'] = source_after == source_before
    report['bank_unchanged'] = prepare(args.bank)['files'] == bank_receipt['files']
    action_hashes = sorted({row['action_sha256'] for group in report['cohorts']
                           for row in group['samples'] if 'action_sha256' in row})
    report['cross_scheduling_action_parity'] = {
        'completed_action_hashes': action_hashes, 'all_returned_actions_identical': len(action_hashes) == 1,
        'historical_expected_action_available': case.get('expected_action') is not None,
        'engine_legality_checked': False}
    report['completed_at_utc'] = datetime.now(timezone.utc).isoformat()
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps(report['summary'], indent=2, sort_keys=True))
    return 0 if report['sources_unchanged'] and report['bank_unchanged'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
