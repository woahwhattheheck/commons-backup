#!/usr/bin/env python3
"""Paired equal-budget continuations with the official checker and exact inputs.

Incumbents are supplied by the existing SEDGE/FLORA lane, never reconstructed
from a reported score. Raw official data and execution outputs stay outside Git.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def compare(before, after):
    rank = next((i for i, (a, b) in enumerate(zip(before, after)) if a != b), None)
    return {'order': -1 if after < before else 1 if after > before else 0,
            'first_changed_rank': rank, 'before': None if rank is None else before[rank],
            'after': None if rank is None else after[rank]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--checker', type=Path, required=True)
    parser.add_argument('--incumbents', type=Path, required=True)
    parser.add_argument('--parent', type=Path, required=True, help='Built unchanged FLORA solver')
    parser.add_argument('--candidate', type=Path, default=Path(__file__).with_name('solver'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seconds', type=float, default=3)
    parser.add_argument('--instances', nargs='+', required=True)
    args = parser.parse_args()
    if args.seconds <= 0 or args.seconds > 600:
        parser.error('seconds must be in (0,600] for this bounded benchmark')
    for key in ['data', 'checker', 'incumbents', 'parent', 'candidate', 'output']:
        setattr(args, key, getattr(args, key).resolve())
    args.output.mkdir(parents=True, exist_ok=True)
    checker_hash = digest(args.checker)
    rows = []
    for name in args.instances:
        if not name.startswith(('setA-', 'setB-')) or not name[5:].isdigit():
            parser.error('use an exact public setA/setB instance name')
        folder = args.output / name
        folder.mkdir(exist_ok=True)
        inputs = [args.data/name[:4]/(name+'-'+suffix+'.json') for suffix in ['net', 'tm', 'scenario']]
        input_hashes = {p.name: digest(p) for p in inputs}
        incumbent = args.incumbents/name/'solution.json'
        initial_hash = digest(incumbent)
        scores_dir = folder/'scores'; scores_dir.mkdir(exist_ok=True)

        def evaluate(solution, decimals):
            key = hashlib.sha256(json.dumps([checker_hash, input_hashes, digest(solution), decimals], sort_keys=True).encode()).hexdigest()
            cache = scores_dir/(key+'.json')
            if cache.exists():
                result = json.loads(cache.read_text())
            else:
                command = [str(args.checker), '--net', str(inputs[0]), '--tm', str(inputs[1]),
                           '--scenario', str(inputs[2]), '--srpaths', str(solution),
                           '--max-decimal-places', str(decimals)]
                proc = subprocess.run(command, text=True, capture_output=True, timeout=90)
                result = json.loads(proc.stdout)
                if proc.returncode != 0 or result.get('valid') is not True:
                    raise RuntimeError(f'Official checker rejected {solution}: {proc.stderr}')
                # Keep official raw output, including its unrelated Infinity
                # metrics on zero-load synthetic/unused links, without rewriting.
                cache.write_text(proc.stdout)
            if result.get('valid') is not True:
                raise RuntimeError(f'Invalid cached checker result: {cache}')
            return result

        initial = evaluate(incumbent, 6)
        initial_scores = sorted((r['sat'] for r in initial['saturations']), reverse=True)
        results = {}
        labels = ['parent', 'candidate'] if int(name[5:]) % 2 else ['candidate', 'parent']
        for label in labels:
            exe = getattr(args, label)
            target = folder/label; target.mkdir(exist_ok=True)
            solution, stats_path = target/'solution.json', target/'stats.json'
            identity = {'input_hashes': input_hashes, 'incumbent_sha256': initial_hash,
                        'executable_sha256': digest(exe), 'seconds': args.seconds,
                        'window_boundaries': 4, 'label': label}
            record = target/'execution.json'
            if record.exists():
                run = json.loads(record.read_text())
                if run['identity'] != identity or run['solution_sha256'] != digest(solution) or run['stats_sha256'] != digest(stats_path):
                    raise RuntimeError('Existing execution does not match exact benchmark inputs')
            else:
                env = dict(os.environ, SEDGE_SECONDS=str(args.seconds), SEDGE_STATS=str(stats_path),
                           CLOUD_INITIAL_SOLUTION=str(incumbent), CLOUD_WINDOW_BOUNDARIES='4')
                env.pop('SEDGE_MAX_ROUNDS', None)
                start = time.monotonic()
                proc = subprocess.run([str(exe), *map(str, inputs), str(solution)],
                                      env=env, text=True, capture_output=True, timeout=args.seconds+30)
                wall = time.monotonic()-start
                (target/'solver.log').write_text(proc.stderr)
                if proc.returncode != 0:
                    raise RuntimeError(f'Solver failed: {proc.stderr}')
                run = {'identity': identity, 'wall_seconds': wall, 'solution_sha256': digest(solution),
                       'stats_sha256': digest(stats_path)}
                write(record, run)
            official = evaluate(solution, 6)
            score = sorted((r['sat'] for r in official['saturations']), reverse=True)
            if len(score) != len(initial_scores) or score > initial_scores:
                raise AssertionError((name, label, 'official objective regression'))
            stats = json.loads(stats_path.read_text())
            if stats.get('resumed') is not True:
                raise AssertionError((name, label, 'incumbent was not resumed'))
            agreement = None
            if label == 'candidate':
                precise = evaluate(solution, 12)
                actual = {(r['t'], int(r['from']), int(r['to'])): r['sat'] for r in precise['saturations']}
                predicted = {(r['t'], r['from'], r['to']): r['sat'] for r in stats['loads']}
                if actual.keys() != predicted.keys():
                    raise AssertionError('load domains differ')
                error = max(abs(v-actual[k]) for k,v in predicted.items())
                if error >= 2e-9 or sum(stats['budget_used']) != precise['total_cost']:
                    raise AssertionError((name, 'load/cost mismatch', error))
                agreement = {'loads_checked': len(actual), 'max_load_error': error, 'exact_transition_cost': precise['total_cost']}
            results[label] = {'scores': score, 'wall_seconds': run['wall_seconds'],
                              'solution_sha256': digest(solution), 'incumbent_comparison': compare(initial_scores, score),
                              'stats': {k:v for k,v in stats.items() if k != 'loads'}, 'agreement': agreement}
        paired = compare(results['parent']['scores'], results['candidate']['scores'])
        for result in results.values(): result.pop('scores')
        row = {'instance': name, 'valid': True, 'input_hashes': input_hashes, 'incumbent_sha256': initial_hash,
               'checker_sha256': checker_hash, 'seconds_per_continuation': args.seconds,
               'paired_order': labels, 'comparison': paired, 'results': results}
        write(folder/'summary.json', row)
        rows.append(row)
        print(json.dumps({'instance': name, 'comparison': paired,
                          'window_accepted': results['candidate']['stats']['window_accepted'],
                          'agreement': results['candidate']['agreement']}), flush=True)
    write(args.output/'last-batch.json', rows)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
