#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Fixed-work consumer for supplied ROADEF binaries; no search algorithm edits.

Creates new deterministic bidirected, distinct-OD development instances. Every
arm receives the same cold input or immutable baseline incumbent. Compares exact
solution bytes and every non-time statistic. Optional official checker calls
validate baseline and full composition at 6/12 decimals, retaining raw reports.
"""
from __future__ import annotations
import argparse
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import resource
import statistics
import subprocess
import time

VARIANTS = ('baseline', 'distance', 'objective', 'topology',
            'distance_objective', 'distance_topology', 'objective_topology', 'combined')


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path: Path, value: object) -> None:
    # Every caller uses a new run directory. Progress is a single atomic file.
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def inputs(seed: int, n: int, h: int, demands: int, unique: bool,
           segments: int = 4, tight: bool = False, ties: bool = False):
    rng = random.Random(seed)
    ids = [101 + 13*i for i in range(n)]
    pairs = {(min(i, (i+1) % n), max(i, (i+1) % n)) for i in range(n)}
    ring = set(pairs)
    others = [(u, v) for u in range(n) for v in range(u+1, n) if (u, v) not in pairs]
    rng.shuffle(others)
    pairs.update(others[:max(h, n//2)])
    links, chords = [], []
    for u, v in sorted(pairs):
        arc_pair = []
        for a, b in ((u, v), (v, u)):
            arc_pair.append(len(links))
            links.append({'id': len(links), 'from': ids[a], 'to': ids[b],
                          'metric': 1 if ties else rng.randint(1, 6),
                          'capacity': rng.randint(4, 30)})
        if (u, v) not in ring:
            chords.append(arc_pair)
    od = rng.sample([(s, t) for s in ids for t in ids if s != t], demands)
    traffic = [{'s': s, 't': t,
                'v': [0 if (seed+timestep+i) % 19 == 0 else rng.randint(1, 75)
                      for timestep in range(h)]} for i, (s, t) in enumerate(od)]
    masks = [[]]
    for t in range(1, h):
        masks.append(chords[(t-1) % len(chords)] if unique else
                     ([] if t % 3 == 0 else chords[(t % 3)-1]))
    scenario = {'max_segments': segments,
                'budget': [{'t': t, 'value': (0 if tight else (3, 6, 12, 24)[t % 4])}
                           for t in range(1, h)],
                'interventions': [{'t': t, 'links': mask} for t, mask in enumerate(masks)
                                  if t and mask]}
    network = {'directed': True, 'multigraph': False,
               'nodes': [{'id': i} for i in ids], 'links': links}
    return network, {'num_time_slots': h, 'demands': traffic}, scenario, len({tuple(m) for m in masks})


def invoke(binary: Path, paths: list[Path], destination: Path, rounds: int,
           incumbent: Path | None, joint: bool) -> dict:
    destination.mkdir(parents=True, exist_ok=False)
    solution, stats = destination/'solution.json', destination/'stats.json'
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('SEDGE_', 'FLEET_', 'CLOUD_INITIAL_'))}
    env.update(SEDGE_SECONDS='120', SEDGE_MAX_ROUNDS=str(rounds),
               SEDGE_STATS=str(stats), FLEET_JOINT=str(int(joint)), FLEET_DIRECTED='1')
    if incumbent is not None:
        env['CLOUD_INITIAL_SOLUTION'] = str(incumbent)
    command = [str(binary), *map(str, paths), str(solution)]
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    started = time.perf_counter()
    try:
        result = subprocess.run(command, env=env, capture_output=True, timeout=125)
    except subprocess.TimeoutExpired as error:
        (destination/'stdout').write_bytes(error.stdout or b'')
        (destination/'stderr').write_bytes(error.stderr or b'')
        dump(destination/'process.json', {'status': 'timeout', 'command': command})
        raise
    wall = time.perf_counter()-started
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    (destination/'stdout').write_bytes(result.stdout)
    (destination/'stderr').write_bytes(result.stderr)
    row = {'returncode': result.returncode, 'command': command, 'wall_s': wall,
           'child_cpu_s': after.ru_utime + after.ru_stime - before.ru_utime - before.ru_stime,
           'binary_sha256': sha(binary), 'round_limit': rounds, 'joint': joint,
           'incumbent_sha256': sha(incumbent) if incumbent else None}
    dump(destination/'process.json', row)
    if result.returncode or not solution.exists() or not stats.exists():
        raise RuntimeError(f'Failed solver: {destination}')
    values = json.loads(stats.read_text())
    if values['seconds'] >= 60:
        raise RuntimeError('Run approached the time-dependent search threshold; not fixed-work evidence')
    row.update(solution_sha256=sha(solution), stats_sha256=sha(stats), solver_s=values['seconds'],
               comparable={k: v for k, v in values.items() if k != 'seconds'})
    return row


def check(checker: Path, paths: list[Path], directory: Path) -> dict:
    records = {}
    values = json.loads((directory/'stats.json').read_text())
    for places in (6, 12):
        command = [str(checker), '--net', str(paths[0]), '--tm', str(paths[1]),
                   '--scenario', str(paths[2]), '--srpaths', str(directory/'solution.json'),
                   '--max-decimal-places', str(places)]
        result = subprocess.run(command, capture_output=True, timeout=30)
        prefix = directory/f'checker-{places}'
        prefix.with_suffix('.stdout').write_bytes(result.stdout)
        prefix.with_suffix('.stderr').write_bytes(result.stderr)
        parsed = json.loads(result.stdout, parse_float=Decimal)
        if result.returncode or parsed.get('valid') is not True:
            raise RuntimeError(f'Official checker rejected {directory}: {result.returncode}')
        vector = sorted((r['sat'] for r in parsed['saturations']), reverse=True)
        records[str(places)] = {'valid': True, 'raw_sha256': hashlib.sha256(result.stdout).hexdigest(),
                                'count': len(vector), 'cost': parsed['total_cost'],
                                'vector_sha256': hashlib.sha256(json.dumps(list(map(str, vector))).encode()).hexdigest()}
        if places == 12:
            observed = {(r['t'], str(r['from']), str(r['to'])): float(r['sat']) for r in parsed['saturations']}
            predicted = {(r['t'], str(r['from']), str(r['to'])): r['sat'] for r in values['loads']}
            if observed.keys() != predicted.keys():
                raise AssertionError('Different saturation coordinates')
            maximum_error = max(abs(observed[k]-v) for k, v in predicted.items())
            if maximum_error >= 2e-9 or sum(values['budget_used']) != parsed['total_cost']:
                raise AssertionError('Native/checker load or budget disagreement')
            records[str(places)]['maximum_native_load_error'] = maximum_error
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bin-dir', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--checker', type=Path)
    parser.add_argument('--cases', type=int, default=8)
    parser.add_argument('--repeat', type=int, default=1)
    parser.add_argument('--rounds', type=int, default=24)
    parser.add_argument('--large', action='store_true')
    parser.add_argument('--variants', nargs='+', default=list(VARIANTS))
    args = parser.parse_args()
    if (not 1 <= args.cases <= 32 or not 1 <= args.repeat <= 15 or not 1 <= args.rounds <= 100
        or len(args.variants) != len(set(args.variants)) or 'baseline' not in args.variants):
        parser.error('Use distinct arms including baseline and bounded cases/repeats/rounds')
    args.out = args.out.resolve(); args.bin_dir = args.bin_dir.resolve()
    if args.checker:
        args.checker = args.checker.resolve()
    args.out.mkdir(parents=True, exist_ok=False)
    report = {'status': 'running', 'scope': 'generated fixed-work native development; not public-B or qualification',
              'platform': platform.platform(), 'python': platform.python_version(),
              'script_sha256': sha(Path(__file__)), 'cases': [], 'rounds': args.rounds,
              'variants': args.variants, 'checker_sha256': sha(args.checker) if args.checker else None}
    dump(args.out/'REPORT.json', report)
    try:
        for index in range(args.cases):
            folder = args.out/f'case-{index:02d}'; folder.mkdir()
            unique = bool(index % 2)
            n, h, d = (36, 18, 54) if args.large else (10 + index % 4, 4 + index % 5, 10 + 2*index)
            net, traffic, scenario, topology_count = inputs(202609088100 + index, n, h, d, unique,
                segments=4 if args.large else (1, 2, 4, 8)[index % 4],
                tight=not args.large and index in (0, 5), ties=index % 3 == 0)
            paths = [folder/name for name in ('net.json', 'tm.json', 'scenario.json')]
            for path, obj in zip(paths, (net, traffic, scenario)):
                dump(path, obj)
            cell = {'index': index, 'nodes': n, 'slots': h, 'demand_pairs': d,
                    'topology_count': topology_count, 'mask_regime': 'unique' if unique else 'repeated',
                    'inputs': {p.name: sha(p) for p in paths}, 'runs': [], 'checks': {}}
            report['cases'].append(cell)
            baseline_incumbent = None
            for mode in ('cold', 'resume'):
                expected = None
                for repeat in range(args.repeat):
                    # Rotate and reverse order; each process is sequential and fresh.
                    names = args.variants[repeat % len(args.variants):] + args.variants[:repeat % len(args.variants)]
                    if repeat % 2: names = list(reversed(names))
                    for name in names:
                        dest = folder/f'{mode}-{repeat:02d}'/name
                        row = invoke(args.bin_dir/name, paths, dest, args.rounds,
                                     baseline_incumbent if mode == 'resume' else None, bool(index % 2))
                        compared = (row['solution_sha256'], row['comparable'])
                        if expected is None: expected = compared
                        if compared != expected:
                            dump(dest/'MISMATCH.json', {'expected': expected, 'actual': compared})
                            raise AssertionError(f'Fixed-work mismatch {index} {mode} {name}')
                        row.update(variant=name, mode=mode, repetition=repeat)
                        cell['runs'].append(row)
                        if repeat == 0 and name in ('baseline', 'combined') and args.checker:
                            cell['checks'][f'{mode}/{name}'] = check(args.checker, paths, dest)
                        if mode == 'cold' and name == 'baseline' and repeat == 0:
                            baseline_incumbent = dest/'solution.json'
                        dump(args.out/'REPORT.json', report)
                for field in ('wall_s', 'child_cpu_s', 'solver_s'):
                    cell.setdefault('medians', {}).setdefault(mode, {})[field] = {
                        name: statistics.median(r[field] for r in cell['runs']
                                                if r['mode'] == mode and r['variant'] == name)
                        for name in args.variants}
            print(json.dumps({'case': index, 'regime': cell['mask_regime'],
                              'native_runs': len(cell['runs']), 'checks': len(cell['checks']) * 2,
                              'exact_match': True}), flush=True)
        report.update(status='complete', exact_solution_load_budget_counters=True,
                      native_runs=sum(len(c['runs']) for c in report['cases']),
                      official_checker_calls=sum(len(c['checks']) * 2 for c in report['cases']))
    except BaseException as error:
        report.update(status='failed', error_type=type(error).__name__, error=str(error))
        raise
    finally:
        dump(args.out/'REPORT.json', report)


if __name__ == '__main__':
    main()
