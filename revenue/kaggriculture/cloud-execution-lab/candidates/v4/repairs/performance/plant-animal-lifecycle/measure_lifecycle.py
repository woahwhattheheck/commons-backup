# SPDX-License-Identifier: Apache-2.0
"""Run isolated semantic negative controls and alternating component timings."""
from __future__ import annotations
import argparse
import copy
import json
import os
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path
from evidence_support import NAMES, digest, load_inputs, signature, world
from test_lifecycle import MUTANTS


def mutations(runtime, output, optimized):
    output.mkdir(parents=True, exist_ok=False)
    records = []
    for name in MUTANTS:
        command = [sys.executable, *(['-O'] if optimized else []), '-m', 'unittest', '-v', 'test_lifecycle.MutationWitnessTests']
        run = subprocess.run(command, cwd=Path(__file__).parent, capture_output=True, text=True, timeout=60,
                             env={**os.environ, 'PHENOLOGY_RUNTIME': str(runtime), 'PHENOLOGY_MUTANT': name})
        text = run.stdout+run.stderr
        (output/(name+'.log')).write_text(text)
        match = re.search(r'FAILED \(failures=(\d+)\)', text)
        if run.returncode != 1 or not match or 'Ran 7 tests' not in text:
            raise RuntimeError('negative control did not fail behavioral assertions cleanly: '+name)
        records.append({'name': name, 'behavioral_failures': int(match.group(1)), 'tests': 7,
                        'errors': 0, 'returncode': run.returncode, 'log_sha256': digest(text.encode())})
    (output/'MUTATIONS.json').write_text(json.dumps(records, indent=2)+'\n')
    print(json.dumps(records), flush=True)


def benchmark(runtime, output, repeats=9, batch=192):
    _, baseline, candidate, _, _ = load_inputs(runtime)
    result = {'method': 'alternating arms; independently prepared fresh farm copies excluded from timing; component only',
              'repeats': repeats, 'batch': batch, 'python': sys.version, 'workloads': []}
    for density in (0.0, 0.5, 1.0):
        original = world(baseline, 101, density=density)
        for row in original['tiles']:
            for tile in row:
                if isinstance(tile, dict) and tile.get('kind') == 'PLANT':
                    tile.update(watered_today=True, yield_units=4, max_lifespan_step=12)
                elif isinstance(tile, dict) and 'animal' in tile:
                    tile.update(fed_today=True, cared_today=True)
        for name, args in ((NAMES[0], (20,)), (NAMES[1], (11, 24)), (NAMES[2], (11,))):
            times = {'baseline': [], 'candidate': []}
            for rep in range(repeats):
                outputs = {}
                order = ('baseline', 'candidate') if rep%2 == 0 else ('candidate', 'baseline')
                for arm in order:
                    farms = [copy.deepcopy(original) for _ in range(batch)]
                    fn = getattr(baseline if arm == 'baseline' else candidate, name)
                    start = time.perf_counter_ns()
                    for farm in farms: fn(farm, *args)
                    times[arm].append(time.perf_counter_ns()-start)
                    outputs[arm] = signature(farms)
                if outputs['baseline'] != outputs['candidate']:
                    raise RuntimeError('benchmark behavior mismatch')
            b, c = (statistics.median(times[arm]) for arm in ('baseline', 'candidate'))
            result['workloads'].append({'density': density, 'function': name, 'nanoseconds': times,
                                        'baseline_median_ns': b, 'candidate_median_ns': c,
                                        'median_ratio': b/c})
    output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps([{k: v for k, v in row.items() if k != 'nanoseconds'} for row in result['workloads']]), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=lambda p: Path(p).resolve(), required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mutations', action='store_true')
    parser.add_argument('--optimized', action='store_true', help='negative-control child process mode')
    args = parser.parse_args()
    if args.mutations: mutations(args.runtime, args.output, args.optimized)
    else: benchmark(args.runtime, args.output)
