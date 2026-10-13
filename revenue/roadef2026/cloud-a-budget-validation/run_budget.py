"""Execute the three assigned cold qualification-budget cases once.

Consumes an existing frozen context, pinned official inputs/reference and a
source-bound retained-log eligibility record. No build, tuning or submission.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time


CASES = ('04', '14', '16')
SOURCE_SHA256 = {
    'sources/candidate/main.cpp': '758977095f8f34263bbcd9ed043ac4ab7943f04f65fae530c78ee64787c34f8f',
    'supervisor.py': '182371658e82f9037716e90ea8cd115622d089d02512916c7a7bf3b39fca1c63',
    'compare_checker.py': 'a402a0166b1e52c95dd181e15b8a124504ac78ddea7e815944c754569b323cb8',
}
BINARY_SHA256 = {
    'candidate': '2dcbbe9bf36581fc102d861e742027c41d755fa198edcef8738c546b196df6cd',
    'checker': '7227194df604d627720938b163b3d63baaba5a090ed90bff574e7e26af69149a',
    'flora': '449fe1d4919bed04056924d70b6c9e786219940986225eb5dc0c67d250213790',
    'sedge': 'c9cb373dbe454dbaa87a581f09e4ff7608bc3ed31b05baeda5113df8cb629ec8',
}
OBSERVER_SHA256 = '9dc966fa257114768b221d73ad8429f186daff2c222c07f89a86020e0b146ccd'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.write_text(json.dumps(value, indent=2, default=str) + '\n')


def read_diagnostic(path, six):
    """Validate twelve-decimal diagnostics without changing six-decimal ranking."""
    report = json.loads(path.read_bytes(), parse_float=Decimal)
    if report.get('valid') is not True:
        raise ValueError('Official twelve-decimal checker rejected the solution')
    rows = report['saturations']
    keys = [(row['t'], str(row['from']), str(row['to'])) for row in rows]
    vector = [Decimal(row['sat']) for row in rows]
    if (len(keys) != len(set(keys)) or set(keys) != six['keys']
            or any(not value.is_finite() or value < 0 for value in vector)):
        raise ValueError('Twelve-decimal diagnostic coordinates/values differ from complete six-decimal output')
    return {'valid': True, 'vector': vector, 'sha256': digest(path)}


def execute_case(number, args, comparator, reference, eligibility):
    label = 'setA-' + number
    output = args.output / label
    output.mkdir()  # A retained case is never overwritten or silently rerun.
    if eligibility['all_lanes_naturally_exhausted']:
        result = {'instance': label, 'status': 'skipped_natural_exhaustion',
                  'eligibility': eligibility}
        write(output / 'RESULT.json', result)
        return result
    inputs = [args.inputs / f'{label}-{kind}.json' for kind in ('net', 'tm', 'scenario')]
    solution = output / 'solution.json'
    (output / 'artifacts').mkdir()
    env = os.environ.copy()
    for name in ('SEDGE_SECONDS', 'SEDGE_MAX_ROUNDS', 'SEDGE_STATS',
                 'CLOUD_INITIAL_SOLUTION', 'PORTFOLIO_CHECK_INTERVAL',
                 'PORTFOLIO_CHECK_TIMEOUT'):
        env.pop(name, None)
    env.update(PORTFOLIO_SECONDS='585', FLEET_DIRECTED='1', FLEET_JOINT='1',
               FLEET_WAYPOINT_LIMIT='0', PORTFOLIO_ARTIFACTS=str(output / 'artifacts'))
    command = [sys.executable, str(args.observer), '--output', str(output / 'resources.json'),
               '--', 'timeout', '--signal=TERM', '--kill-after=10s', '590s',
               str(args.context / 'run.sh'), *map(str, inputs), str(solution)]
    with (output / 'observer.stdout').open('wb') as log, (output / 'observer.stderr').open('wb') as err:
        run = subprocess.run(command, env=env, cwd=args.output, stdout=log, stderr=err, check=False)
    result = {'instance': label, 'eligibility': eligibility, 'command': command,
              'returncode': run.returncode, 'input_sha256': {p.name: digest(p) for p in inputs}}
    if run.returncode != 0:
        result['status'] = 'execution_failed'
        write(output / 'RESULT.json', result)
        return result
    receipt = read(output / 'solution.json.portfolio.json')
    if not (receipt['validated'] and receipt['search_allowance_seconds'] == 565
            and receipt['deadline_seconds'] == 585 and digest(solution) == receipt['solution_sha256']):
        raise ValueError(f'{label}: invalid final receipt')
    checks = []
    for decimals in (6, 12):
        target = output / f'checker-{decimals}.json'
        command = [str(args.context / 'bin/checker'), '--net', str(inputs[0]),
                   '--tm', str(inputs[1]), '--scenario', str(inputs[2]),
                   '--srpaths', str(solution), '--max-decimal-places', str(decimals)]
        start = time.monotonic()
        with target.open('wb') as out, target.with_suffix('.stderr').open('wb') as err:
            checked = subprocess.run(command, stdout=out, stderr=err, timeout=60, check=False)
        parsed = (comparator.load_result(target) if decimals == 6 else
                  read_diagnostic(target, comparator.load_result(output / 'checker-6.json')))
        checks.append({'decimals': decimals, 'command': command, 'returncode': checked.returncode,
                       'wall_seconds': time.monotonic() - start, 'valid': parsed['valid'],
                       'load_count': len(parsed['vector']), 'sha256': digest(target)})
        if checked.returncode != 0 or not parsed['valid']:
            raise ValueError(f'{label}: independent checker rejected final solution')
    if checks[0]['sha256'] != receipt['selected_checker_sha256']:
        raise ValueError(f'{label}: selected checkpoint differs from independent recheck')
    six = comparator.load_result(output / 'checker-6.json')
    comparison = comparator.compare_sprint(six, reference, label)
    result.update(status='complete', solution_sha256=digest(solution),
                  comparison=comparison, independent_checks=checks,
                  resources=read(output / 'resources.json'), portfolio_receipt=receipt)
    write(output / 'RESULT.json', result)
    print(json.dumps({'case': label, 'status': 'complete', 'comparison': comparison}), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('context', 'inputs', 'reference', 'observer', 'eligibility', 'output'):
        parser.add_argument('--' + name, type=lambda p: Path(p).resolve(), required=True)
    args = parser.parse_args()
    for name, expected in SOURCE_SHA256.items():
        if digest(args.context / name) != expected:
            raise ValueError('Frozen source mismatch: ' + name)
    for name, expected in BINARY_SHA256.items():
        if digest(args.context / 'bin' / name) != expected:
            raise ValueError('Frozen binary mismatch: ' + name)
    if digest(args.observer) != OBSERVER_SHA256:
        raise ValueError('Observer mismatch')
    eligibility = read(args.eligibility)
    for number in CASES:
        row = eligibility['cases']['setA-' + number]
        if type(row.get('all_lanes_naturally_exhausted')) is not bool or not row.get('source'):
            raise ValueError('Source-bound retained-log eligibility missing: ' + number)
        for kind in ('net', 'tm', 'scenario'):
            path = args.inputs / f'setA-{number}-{kind}.json'
            if digest(path) != eligibility['input_sha256'][path.name]:
                raise ValueError('Official input mismatch: ' + path.name)
    spec = importlib.util.spec_from_file_location('frozen_compare', args.context / 'compare_checker.py')
    comparator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(comparator)
    reference = comparator.load_sprint_reference(args.reference)
    args.output.mkdir()  # No implicit resume/repetition after interrupted execution.
    write(args.output / 'SETUP.json', {'source_sha256': SOURCE_SHA256, 'binaries': BINARY_SHA256,
          'observer_sha256': OBSERVER_SHA256, 'runner_sha256': digest(Path(__file__)),
          'eligibility': eligibility, 'maximum_concurrent_cases': 2,
          'execution_order': list(CASES), 'source_manifest_commit': '6feb9c0566b8f203c5d1a2ffdfbf1cb6d11be055'})
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(execute_case, number, args, comparator, reference,
                               eligibility['cases']['setA-' + number]) for number in CASES]
        results = [future.result() for future in futures]
    write(args.output / 'RESULT.json', {'cases': results,
          'all_complete_or_deliberately_skipped': all(row['status'] in ('complete', 'skipped_natural_exhaustion') for row in results),
          'historical_reference_resource_budgets_matched': False,
          'qualification_rank': 'unknown'})
    return 0 if all(row['status'] in ('complete', 'skipped_natural_exhaustion') for row in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
