#!/usr/bin/env python3
"""Run the assigned historical V2 temporal OFF/ON resumed diagnostic once."""
from decimal import Decimal
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import time

ROOT = Path(__file__).resolve().parent
INPUT = Path('/tmp/quartz-roadef-a-budget-20260908-01')
CONTEXT = Path('/tmp/quartz-roadef-final-20260908-01/context')
BINARY = ROOT / 'temporal-v2'
OBSERVER = ROOT / 'measure_command.py'
CHECKER = CONTEXT / 'bin/checker'
CASES = [('04', (0, 1)), ('14', (1, 0))]
INCUMBENT_SHA = {
    '04': '03075aa4e0703e568451d730f63e312124e5a039b26366802a5e28c12898c9b9',
    '14': '9d01dea739f910ae3c23d4649dbffb248884b0af18a2cc0624bf338b3defb009',
}


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def read_decimal(path):
    return json.loads(path.read_text(), parse_float=Decimal)


def diagnostic(path):
    data = read_decimal(path)
    if data.get('valid') is not True:
        return {'valid': False, 'sha256': sha(path)}
    rows = data['saturations']
    keys = [(row['t'], str(row['from']), str(row['to'])) for row in rows]
    values = [Decimal(row['sat']) for row in rows]
    if len(keys) != len(set(keys)) or any(not v.is_finite() or v < 0 for v in values):
        raise ValueError(f'Invalid checker vector: {path}')
    return {'valid': True, 'sha256': sha(path), 'keys': keys,
            'vector': sorted(values, reverse=True), 'total_cost': data.get('total_cost')}


def compare(left, right):
    if not left['valid'] or not right['valid']:
        return {'winner': 'left' if left['valid'] else 'right' if right['valid'] else 'neither'}
    if set(left['keys']) != set(right['keys']):
        raise ValueError('Checker coordinate sets differ')
    a, b = left['vector'], right['vector']
    if len(a) != len(b):
        raise ValueError('Checker vector lengths differ')
    rank = next((i for i, pair in enumerate(zip(a, b)) if pair[0] != pair[1]), None)
    result = {'load_count': len(a), 'left_mlu': str(a[0]), 'right_mlu': str(b[0]),
              'first_changed_rank': None if rank is None else rank + 1,
              'winner': 'tie' if rank is None else ('left' if a[rank] < b[rank] else 'right')}
    if rank is not None:
        result.update(left_at_first_change=str(a[rank]), right_at_first_change=str(b[rank]))
    return result


def run_checker(case, solution, decimals, output):
    inputs = [INPUT / 'inputs' / f'setA-{case}-{kind}.json' for kind in ('net', 'tm', 'scenario')]
    command = [str(CHECKER), '--net', str(inputs[0]), '--tm', str(inputs[1]),
               '--scenario', str(inputs[2]), '--srpaths', str(solution),
               '--max-decimal-places', str(decimals)]
    start = time.monotonic()
    with output.open('xb') as stdout, output.with_suffix('.stderr').open('xb') as stderr:
        result = subprocess.run(command, stdout=stdout, stderr=stderr, timeout=60, check=False)
    record = {'command': command, 'returncode': result.returncode,
              'wall_seconds': time.monotonic() - start, 'sha256': sha(output),
              **{k: v for k, v in diagnostic(output).items() if k not in ('keys', 'vector')}}
    if result.returncode != 0 or not record['valid']:
        raise ValueError(f'Official checker rejected {solution} at {decimals} decimals')
    return record


def main():
    spec = importlib.util.spec_from_file_location('frozen_compare', ROOT / 'compare_checker.py')
    frozen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(frozen)
    identities = {'binary': sha(BINARY), 'checker': sha(CHECKER), 'observer': sha(OBSERVER),
                  'comparator': sha(ROOT / 'compare_checker.py'),
                  'source_main': sha(ROOT / 'materialized/main.cpp'),
                  'source_temporal_header': sha(ROOT / 'materialized/temporal_dp.hpp')}
    results = []
    for case, order in CASES:
        incumbent = INPUT / 'execution' / f'setA-{case}' / 'solution.json'
        if sha(incumbent) != INCUMBENT_SHA[case]:
            raise ValueError(f'Incumbent mismatch for A{case}')
        incumbent6_path = INPUT / 'execution' / f'setA-{case}' / 'checker-6.json'
        incumbent12_path = INPUT / 'execution' / f'setA-{case}' / 'checker-12.json'
        incumbent6 = diagnostic(incumbent6_path)
        incumbent12 = diagnostic(incumbent12_path)
        arms = []
        for enabled in order:
            name = 'temporal-on' if enabled else 'temporal-off'
            directory = ROOT / f'A{case}' / name
            directory.mkdir(parents=True)
            fallback = directory / 'immutable-fallback.json'
            shutil.copyfile(incumbent, fallback)
            fallback.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
            output = directory / 'raw-output.json'
            stats = directory / 'stats.json'
            inputs = [INPUT / 'inputs' / f'setA-{case}-{kind}.json' for kind in ('net', 'tm', 'scenario')]
            env = os.environ.copy()
            env.update(SEDGE_SECONDS='60', FLEET_TEMPORAL=str(enabled), FLEET_TEMPORAL_ROUTES='12',
                       FLEET_DIRECTED='1', FLEET_JOINT='1', FLEET_WAYPOINT_LIMIT='0',
                       OMP_NUM_THREADS='1', CLOUD_INITIAL_SOLUTION=str(fallback), SEDGE_STATS=str(stats))
            env.pop('SEDGE_MAX_ROUNDS', None)
            measured = [str(os.sys.executable), str(OBSERVER), '--output', str(directory / 'resources.json'),
                        '--', 'timeout', '--signal=TERM', '--kill-after=5s', '65s',
                        str(BINARY), *map(str, inputs), str(output)]
            with (directory / 'observer.stdout').open('xb') as stdout, (directory / 'observer.stderr').open('xb') as stderr:
                process = subprocess.run(measured, cwd=ROOT, env=env, stdout=stdout, stderr=stderr, check=False)
            if process.returncode != 0 or not output.is_file() or not stats.is_file():
                raise ValueError(f'Execution failed: A{case} {name} rc={process.returncode}')
            checks = [run_checker(case, output, decimals, directory / f'checker-{decimals}.json')
                      for decimals in (6, 12)]
            raw6 = diagnostic(directory / 'checker-6.json')
            raw12 = diagnostic(directory / 'checker-12.json')
            versus6 = compare(raw6, incumbent6)
            versus12 = compare(raw12, incumbent12)
            use_output = raw6['valid'] and versus6['winner'] == 'left'
            retained = directory / 'retained-solution.json'
            shutil.copyfile(output if use_output else fallback, retained)
            retained_checks = [run_checker(case, retained, decimals, directory / f'retained-checker-{decimals}.json')
                               for decimals in (6, 12)]
            record = {'case': 'A' + case, 'arm': name, 'temporal_enabled': bool(enabled),
                      'fallback_sha256': sha(fallback), 'raw_solution_sha256': sha(output),
                      'retained_solution_source': 'raw-output' if use_output else 'immutable-fallback',
                      'retained_solution_sha256': sha(retained), 'resources': json.loads((directory / 'resources.json').read_text()),
                      'stats': json.loads(stats.read_text()), 'raw_checks': checks,
                      'retained_checks': retained_checks, 'versus_incumbent_6dp': versus6,
                      'versus_incumbent_12dp_diagnostic': versus12}
            (directory / 'RESULT.json').write_text(json.dumps(record, indent=2) + '\n')
            arms.append(record)
            print(json.dumps({'case': case, 'arm': name, 'versus_incumbent': versus6,
                              'retained': record['retained_solution_source']}), flush=True)
        by_name = {arm['arm']: arm for arm in arms}
        off6 = diagnostic(ROOT / f'A{case}/temporal-off/checker-6.json')
        on6 = diagnostic(ROOT / f'A{case}/temporal-on/checker-6.json')
        off12 = diagnostic(ROOT / f'A{case}/temporal-off/checker-12.json')
        on12 = diagnostic(ROOT / f'A{case}/temporal-on/checker-12.json')
        results.append({'case': 'A' + case, 'execution_order': [a['arm'] for a in arms],
                        'temporal_on_vs_off_6dp': compare(on6, off6),
                        'temporal_on_vs_off_12dp_diagnostic': compare(on12, off12), 'arms': arms})
    summary = {'operation': 'roadef-dock-v2-exhausted-A04-A14-20260908-01',
               'claim': '1788859227.354099', 'strictly_sequential': True,
               'identities': identities, 'cases': results}
    (ROOT / 'RESULT.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps({'complete': True, 'cases': [{k: v for k, v in row.items() if k != 'arms'} for row in results]}))


if __name__ == '__main__':
    main()
