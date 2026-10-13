# SPDX-License-Identifier: Apache-2.0
"""Alternating local unit-loop benchmark; NOT whole-agent or game-speed evidence."""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path
import statistics
import time
from check_kinetic import authenticate, graph, module, simple_world
from compose_kinetic import compose


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--native-root', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--iterations', type=int, default=150000)
    p.add_argument('--rounds', type=int, default=7)
    args = p.parse_args()
    if args.iterations < 1 or args.rounds < 2:
        p.error('Positive iterations and at least two alternating rounds required')
    authenticate(args.native_root)
    text = (args.native_root/'mechanics.py').read_text()
    mods = {'baseline': module(text, 'kinetic_benchmark_baseline'),
            'candidate': module(compose(text), 'kinetic_benchmark_candidate')}
    fixtures = {'pass': [['PASS']], 'movement': [['EAST'], ['WEST']],
                'mixed': [['PASS'], ['EAST'], ['WEST'], ['WATER'], ['COLLECT_FERTILIZER'], ['CARE']]}
    rows, summary = [], {}
    for name, ops in fixtures.items():
        by_arm = {'baseline': [], 'candidate': []}
        for rep in range(args.rounds):
            snapshots = {}
            order = ['baseline', 'candidate'] if rep%2 == 0 else ['candidate', 'baseline']
            for arm in order:
                farm, private = simple_world()
                fn = mods[arm]._apply_unit_action
                before = time.perf_counter()
                for i in range(args.iterations):
                    fn(farm, private, i%3, ops[i%len(ops)], 10, 8, 24)
                elapsed = time.perf_counter()-before
                snapshots[arm] = graph((farm, private))
                by_arm[arm].append(elapsed)
                rows.append({'fixture': name, 'round': rep, 'arm': arm, 'seconds': elapsed})
            if snapshots['baseline'] != snapshots['candidate']:
                raise AssertionError(f'Benchmark state mismatch: {name}/{rep}')
        b = statistics.median(by_arm['baseline'])
        c = statistics.median(by_arm['candidate'])
        summary[name] = {'baseline_median_seconds': b, 'candidate_median_seconds': c,
                         'candidate_to_baseline_ratio': c/b}
    report = {'scope': 'Repeated constructed Python unit-loop batches; not native RPC, deadline, or EV evidence',
              'iterations_per_batch': args.iterations, 'rounds': args.rounds, 'samples': rows,
              'summary': summary}
    args.output.write_text(json.dumps(report, sort_keys=True, indent=2)+'\n')
    print(json.dumps(summary, sort_keys=True))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
