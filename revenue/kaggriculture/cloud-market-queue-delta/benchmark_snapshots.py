# SPDX-License-Identifier: Apache-2.0
"""Paired warm benchmark of the existing queue executor, without game panels."""
from __future__ import annotations

import argparse
import cProfile
import gc
import hashlib
import json
import math
from pathlib import Path
import platform
import pstats
import statistics
import sys
import time

import queue_delta as candidate
import test_snapshot_reuse as cases


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sample_summary(values):
    ordered = sorted(values)
    return dict(min_ms=ordered[0], median_ms=statistics.median(ordered),
                p95_ms=ordered[math.ceil(0.95 * len(ordered)) - 1],
                max_ms=ordered[-1], samples_ms=values)


def read_optional(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def measure(module, engine, payload):
    start = time.perf_counter_ns()
    result = module.compare_queues(engine, **payload)
    milliseconds = (time.perf_counter_ns() - start) / 1e6
    if result['status'] != 'complete_conditional':
        raise AssertionError(result.get('reason'))
    return milliseconds, result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine-cache', type=Path, required=True)
    parser.add_argument('--baseline-source', type=Path, required=True)
    parser.add_argument('--repeats', type=int, default=21)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.baseline_source = args.baseline_source.resolve()
    if args.repeats < 3:
        parser.error('--repeats must be at least 3')
    if digest(args.baseline_source) != cases.BASELINE_SHA256:
        parser.error('baseline source does not match original PR9976')
    baseline = cases.load_module('snapshot_benchmark_baseline', args.baseline_source)
    engine = cases.load_full_engine(args.engine_cache)
    cases.ENGINE = engine
    report = dict(
        schema='queue-snapshot-benchmark-v1',
        baseline_sha256=digest(args.baseline_source),
        candidate_sha256=digest(Path(candidate.__file__)),
        benchmark_sha256=digest(Path(__file__)),
        fixture_sha256=digest(Path(cases.__file__)),
        engine_sha256=digest(args.engine_cache / 'kaggriculture.py'),
        python=sys.version, platform=platform.platform(),
        cpu_max=read_optional('/sys/fs/cgroup/cpu.max'),
        memory_max=read_optional('/sys/fs/cgroup/memory.max'),
        method='Two excluded warmups per arm; alternating timed order; full reports compared after every pair; GC enabled, collection before each pair.',
        timing_scope='Warm whole compare_queues call; imports, engine loading and JSON serialization excluded; no agent/game timing claim.',
        repeats=args.repeats, game_panels=0, game_seeds=0, workloads=[])
    workloads = [(1, 0), (8, 6), (32, 12)]
    for scenario_count, hands in workloads:
        payload = cases.fixture(scenarios=scenario_count, hands=hands, slots=10)
        for _ in range(2):
            _, old = measure(baseline, engine, payload)
            _, new = measure(candidate, engine, payload)
            if cases.without_time(old) != cases.without_time(new):
                raise AssertionError('warmup reports differ')
        times = {'baseline': [], 'candidate': []}
        for iteration in range(args.repeats):
            gc.collect()
            order = [('baseline', baseline), ('candidate', candidate)]
            if iteration % 2:
                order.reverse()
            outputs = {}
            for label, module in order:
                elapsed, outputs[label] = measure(module, engine, payload)
                times[label].append(elapsed)
            if cases.without_time(outputs['baseline']) != cases.without_time(outputs['candidate']):
                raise AssertionError('paired reports differ')
        b, c = sample_summary(times['baseline']), sample_summary(times['candidate'])
        row = dict(scenarios=scenario_count, initial_hands=hands, slots=10,
                   baseline=b, candidate=c,
                   median_reduction_percent=100 * (1 - c['median_ms'] / b['median_ms']),
                   paired_report_matches=args.repeats)
        report['workloads'].append(row)
        print(json.dumps({k: v for k, v in row.items() if k not in ('baseline', 'candidate')}
                         | {'old_ms': b['median_ms'], 'new_ms': c['median_ms']}))
    # Profile only after timings; overhead-bearing profile is reported separately.
    profiler = cProfile.Profile()
    payload = cases.fixture(scenarios=8, hands=6, slots=10)
    profiler.enable()
    for _ in range(5):
        baseline.compare_queues(engine, **payload)
    profiler.disable()
    stats = pstats.Stats(profiler)
    key = next(key for key in stats.stats if key[0] == str(args.baseline_source) and key[2] == '_view')
    data = stats.stats[key]
    report['instrumented_baseline_profile'] = dict(
        comparisons=5, scenarios_per_comparison=8,
        total_seconds=stats.total_tt, view_calls=data[1], view_cumulative_seconds=data[3],
        view_cumulative_fraction=data[3] / stats.total_tt,
        note='Profiler overhead included; use paired unprofiled samples for latency.')
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
