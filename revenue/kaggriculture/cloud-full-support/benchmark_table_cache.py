# SPDX-License-Identifier: Apache-2.0
"""Alternating-order cache-hit and cache-miss timings against an exact source.

Synthetic receipt tables only. Imports, engines, receipt construction, physical
feasibility, and whole-agent performance are outside these measurements.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import statistics
import time
import full_support as current


def load(path):
    spec = importlib.util.spec_from_file_location('_cache_benchmark_reference', path)
    if spec is None or spec.loader is None:
        raise ValueError('Cannot load the supplied reference')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def identity(path):
    body = Path(path).read_bytes()
    return {'git_blob': hashlib.sha1(b'blob '+str(len(body)).encode()+b'\0'+body).hexdigest(),
            'sha256': hashlib.sha256(body).hexdigest(), 'bytes': len(body)}


def workloads():
    yield 'zero_1x1', [[0]]
    yield 'three_support_4x3', [[0,0,0],[5,-2,-2],[-2,5,-2],[-2,-2,5]]
    yield 'eight_support_9x8', [[0]*8] + [[8 if i == j else -1 for j in range(8)] for i in range(8)]
    yield 'repeated_columns_9x32', [[0]*32] + [[8 if i == j%8 else -1 for j in range(32)] for i in range(8)]
    # The terminal adapter embeds absolute win-point rows as [zero; 1+points].
    # These are algebraic consumer-shaped fixtures, not new engine receipts.
    yield 'terminal_varying_baseline_3x2', [[0,0],[1,2],[2,2]]
    yield 'terminal_mixture_4x3', [[0,0,0],[1,2,'3/2'],[2,1,2],[1,2,2]]


def run(reference_file, *, repeats=16, batch=12):
    reference = load(reference_file)
    records = []
    for name, data in workloads():
        expected = reference.solve_full_table(data)
        for mode in ['hit', 'miss']:
            rows = []
            for repetition in range(repeats):
                current.clear_table_cache()
                current.solve_full_table(data)  # Warm module/input outside timing.
                order = ['original', 'cached'] if repetition % 2 == 0 else ['cached', 'original']
                samples = {}
                for label in order:
                    fn = reference.solve_full_table if label == 'original' else current.solve_full_table
                    timings = []
                    for _ in range(batch):
                        if mode == 'miss' and label == 'cached':
                            current.clear_table_cache()  # Excluded; lookup/miss/copy are included.
                        start = time.perf_counter_ns()
                        result = fn(data)
                        timings.append((time.perf_counter_ns()-start)/1e6)
                        if result != expected:
                            raise AssertionError((name, mode, repetition, label))
                    samples[label] = timings
                rows.append({'repetition': repetition, 'order': order, 'samples_ms': samples})
            original = [v for row in rows for v in row['samples_ms']['original']]
            cached = [v for row in rows for v in row['samples_ms']['cached']]
            def stats(values):
                ordered = sorted(values)
                return {'median_ms': statistics.median(values),
                        'p95_ms': ordered[int(.95*(len(values)-1))], 'maximum_ms': max(values)}
            a, b = stats(original), stats(cached)
            records.append({'name': name, 'mode': mode, 'deltas': data,
                            'result': expected, 'original': a, 'cached': b,
                            'median_speedup': a['median_ms']/b['median_ms'],
                            'median_ms_delta': b['median_ms']-a['median_ms'],
                            'pairs': len(original), 'raw': rows})
    return {'schema': 'titan.full-support-cache.benchmark.v1', 'python': platform.python_version(),
            'platform': platform.platform(), 'repetitions': repeats, 'batch': batch,
            'source': {'current': identity(Path(__file__).with_name('full_support.py')),
                       'original': identity(reference_file), 'benchmark': identity(__file__)},
            'scope': 'In-process solver calls on synthetic tables only; imports and cache clear excluded. '
                     'Miss lookup, detached result copy, normalization and validation included. '
                     'Actual application cache-hit frequency and whole-agent benefit are unmeasured.',
            'records': records, 'full_result_pair_comparisons': sum(r['pairs'] for r in records),
            'games': 0, 'engine_transitions': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference-file', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repeats', type=int, default=16)
    parser.add_argument('--batch', type=int, default=12)
    args = parser.parse_args()
    if not 1 <= args.repeats <= 100 or not 1 <= args.batch <= 100:
        parser.error('repeats and batch must each be in 1..100')
    report = run(args.reference_file, repeats=args.repeats, batch=args.batch)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2); stream.write('\n')
    print(json.dumps([{k: r[k] for k in ['name','mode','median_speedup','median_ms_delta','original','cached']}
                      for r in report['records']], indent=2))


if __name__ == '__main__':
    main()
