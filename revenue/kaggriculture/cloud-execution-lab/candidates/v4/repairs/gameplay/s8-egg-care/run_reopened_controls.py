# SPDX-License-Identifier: Apache-2.0
"""Run normal/-O candidate gates, semantic mutants and offline custody failures.

Uses the same exact composer as independent field/engine owners. This never
patches production, changes a default, starts a workflow, or contacts Kaggle.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import compose_reopened_s8 as composer

MUTATIONS = {
    'ignore_live_sell': ('lower_bound -= row[2]', 'lower_bound -= 0'),
    'full_shed_off_by_one': ('return lower_bound >= capacity', 'return lower_bound >= capacity - 1'),
    'invent_buy_fill': ('lower_bound -= row[2]\n', 'lower_bound -= row[2]\n        elif row[0] == "BUY_PRODUCT":\n            lower_bound += row[2]\n'),
    'ignore_shed_removing_units': (
        'if rows is None or any(len(row) != 1 or not isinstance(row[0], str)\n                           or row[0] not in _SHED_NEUTRAL_UNITS for row in rows):',
        'if rows is None:'),
    'compact_before_raw_cap': ('for row in market[:limit]:', 'for row in [r for r in market if r][:limit]:'),
    'relax_held_cap': ('units + current_add + 2 > GOOSE_MAX_HELD', 'units + current_add + 2 > GOOSE_MAX_HELD + 1'),
    'unpayable_final_day': ('LAST_CARE_DAY = 27', 'LAST_CARE_DAY = 28'),
    'ignore_pending_bonus': ('pending_bonus != 0:', 'pending_bonus < 0:'),
    'burn_low_buffer': ('MIN_FERTILIZER_BUFFER = 4', 'MIN_FERTILIZER_BUFFER = 0'),
    'retain_inert_price_guard': ('strong if mode == "donor" else egg > fertilizer', 'strong if mode == "donor" else strong'),
    'override_harvest_rescue': ('if command != ["COLLECT_FERTILIZER"]:', 'if command not in (["COLLECT_FERTILIZER"], ["HARVEST"]):'),
    'skip_real_care': ('result_rows[actor] = ["CARE"]', 'result_rows[actor] = ["PASS"]'),
}
DEPENDENCIES = ('checks/reference/engine/kaggriculture.py',
                'checks/reference/engine/kaggriculture.json',
                'checks/reference/engine/utils.py',
                'checks/reference/evaluator/loader.py')


def identity(data):
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
            'blob': hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()}


def run(mode, native, module=None):
    env = dict(os.environ, S8_NATIVE_ROOT=str(native))
    env.pop('S8_MODULE', None)
    if module is not None:
        env['S8_MODULE'] = str(module)
    cmd = [sys.executable] + (['-O'] if mode == 'optimized' else []) + [str(HERE / 'test_reopened_s8.py')]
    result = subprocess.run(cmd, env=env, text=True, capture_output=True, timeout=30)
    output = result.stdout + result.stderr
    tests = re.search(r'Ran (\d+) tests?', output)
    failures = re.search(r'failures=(\d+)', output)
    errors = re.search(r'errors=(\d+)', output)
    skipped = re.search(r'skipped=(\d+)', output)
    counts = re.search(r'FULL_INTERPRETER_CALLS=(\d+) INITIALIZATIONS=(\d+) ACTION_TRANSITIONS=(\d+)', output)
    return {'returncode': result.returncode,
            'tests': int(tests[1]) if tests else 0,
            'failures': int(failures[1]) if failures else 0,
            'errors': int(errors[1]) if errors else 0,
            'skipped': int(skipped[1]) if skipped else 0,
            'interpreter_calls': int(counts[1]) if counts else 0,
            'initializations': int(counts[2]) if counts else 0,
            'action_transitions': int(counts[3]) if counts else 0,
            'assertion_failed_tests': re.findall(r'^FAIL: ([^\n]+)', output, re.MULTILINE),
            'log': output}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--native-root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    native = args.native_root.resolve()
    source = composer.compose((HERE/'s8_egg_care.py').read_bytes()).decode()
    report = {'schema': 'titan-v4-s8-reopen-gate-v1', 'python': platform.python_version(),
              'scope': 'constructed helper/full-interpreter acceptance; not native activation or field EV',
              'generated_helper': identity(source.encode()),
              'inputs': {n: identity((native/n).read_bytes()) for n in DEPENDENCIES},
              'authored_sources': {n: identity((HERE/n).read_bytes()) for n in (
                  'compose_reopened_s8.py', 'test_reopened_s8.py', 'run_reopened_controls.py')},
              'modes': {}}
    begin = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix='s8-reopen-controls-') as tmp:
        tmp = Path(tmp)
        for mode in ('normal', 'optimized'):
            baseline = run(mode, native)
            if baseline['returncode'] or baseline['tests'] != 30 or baseline['failures'] or baseline['errors'] or baseline['skipped']:
                raise RuntimeError('baseline failed: ' + baseline['log'])
            mutants = {}
            for name, (before, after) in MUTATIONS.items():
                if source.count(before) != 1:
                    raise ValueError('mutant anchor mismatch: ' + name)
                path = tmp/(name+'.py'); path.write_text(source.replace(before, after, 1))
                result = run(mode, native, path)
                if result['returncode'] != 1 or not result['failures'] or result['errors'] or result['skipped']:
                    raise RuntimeError('mutant not assertion-rejected: ' + name + '\n' + result['log'])
                mutants[name] = result
            custody = {}
            for rel in DEPENDENCIES:
                for fault in ('missing', 'changed'):
                    root = tmp/(Path(rel).name + '_' + fault)
                    for member in DEPENDENCIES:
                        dest = root/member; dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(native/member, dest)
                    target = root/rel
                    if fault == 'missing':
                        target.unlink()
                    else:
                        target.write_bytes(target.read_bytes() + b'\n# custody fault\n')
                    result = run(mode, root)
                    expected = 'FileNotFoundError' if fault == 'missing' else 'input mismatch:'
                    if result['returncode'] != 1 or result['tests'] != 0 or expected not in result['log']:
                        raise RuntimeError('custody did not fail before import: ' + rel + '\n' + result['log'])
                    custody[rel+':'+fault] = result
            report['modes'][mode] = {'baseline': baseline, 'semantic_mutants': mutants, 'custody_faults': custody}
    report['seconds'] = time.perf_counter()-begin
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True)+'\n')
    print(json.dumps({'baseline_tests_per_mode':30, 'semantic_mutants_rejected_per_mode':len(MUTATIONS),
                      'custody_faults_rejected_per_mode':8, 'report':str(args.output),
                      'seconds':report['seconds']}))


if __name__ == '__main__':
    main()
