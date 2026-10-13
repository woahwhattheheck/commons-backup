# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import argparse
import json
from pathlib import Path
import resource
import statistics
import time

from constraint_repair import RepairConfig, find_shortest_splice


def transition(state, action):
    # Deterministic small branch tree. Exact target is a 3-step lexically early path.
    out = {'path': state['path'] + [action], 'material': dict(state['material'])}
    if out['path'] == ['A', 'A', 'A']:
        out['material'] = {'position': [4, 2], 'cash': 100, 'wheat': 8}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', required=True)
    ap.add_argument('--runs', type=int, default=64)
    args = ap.parse_args()

    cfg = RepairConfig(max_nodes=128, max_depth=8, budget_ns=10_000_000, max_candidates=8)
    elapsed = []
    reasons = {}
    nodes = []
    outputs = set()
    for _ in range(args.runs):
        start = {'path': [], 'material': {'position': [1, 2], 'cash': 100, 'wheat': 8}}
        target = {'position': [4, 2], 'cash': 100, 'wheat': 8}
        t0 = time.perf_counter_ns()
        result = find_shortest_splice(
            start, target,
            lambda st, depth: ('D', 'C', 'B', 'A'),
            transition,
            projector=lambda st: st['material'],
            config=cfg,
        )
        wall_ms = (time.perf_counter_ns() - t0) / 1_000_000
        elapsed.append(wall_ms)
        reasons[result.reason] = reasons.get(result.reason, 0) + 1
        nodes.append(result.nodes_seen)
        if result.nodes_seen > 128:
            raise SystemExit('node cap exceeded')
        # Hard admission boundary: wall elapsed must stay under the 10 ms budget
        # for this finite cooperative harness. Search-loop + raw-pull bounds are
        # the enforceable contract; a single blocking callback remains cooperative.
        if wall_ms > 10.0:
            raise SystemExit(f'wall budget exceeded: {wall_ms:.3f} ms > 10 ms')
        if result.found:
            outputs.add(json.dumps(result.actions, separators=(',', ':')))
            if result.actions != ('A', 'A', 'A'):
                raise SystemExit('non-shortest or non-deterministic result')
        elif result.actions:
            raise SystemExit('failed repair returned actions')

    if len(outputs) > 1:
        raise SystemExit('successful output is non-deterministic')
    ordered = sorted(elapsed)
    p95_idx = max(0, min(len(ordered) - 1, int(len(ordered) * .95) - 1))
    rss_kib = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    report = {
        'schema': 'titan.s19.contract.v1',
        'runs': args.runs,
        'config': {
            'max_nodes': 128,
            'max_depth': 8,
            'budget_ms': 10,
            'max_candidates': 8,
            'max_raw_pulls': cfg.max_raw_pulls,
        },
        'reasons': reasons,
        'deterministic_success_outputs': len(outputs),
        'max_nodes_seen': max(nodes),
        'timing_ms': {
            'min': min(elapsed),
            'median': statistics.median(elapsed),
            'p95': ordered[p95_idx],
            'max': max(elapsed),
        },
        'max_rss_kib': rss_kib,
        'fail_closed': True,
        'wall_budget_enforced': True,
        'gameplay_claim': False,
    }
    Path(args.output).write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps(report, sort_keys=True))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
