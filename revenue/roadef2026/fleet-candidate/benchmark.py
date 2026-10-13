"""Matched-budget candidate experiments, using the pinned official checker."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import time

ROOT = Path(__file__).resolve().parent

def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def execute(cmd, folder, label, env=None, timeout=660):
    start = time.monotonic()
    def save(stdout, stderr, status, returncode):
        # Keep byte streams unmodified; a timeout's capture is only a prefix.
        stdout, stderr = stdout or b'', stderr or b''
        record = {'schema': 'roadef.benchmark.process.v1', 'label': label,
                  'status': status, 'returncode': returncode,
                  'timeout_seconds': timeout, 'wall_seconds': time.monotonic() - start,
                  'capture_complete': status != 'timeout',
                  'stdout_bytes': len(stdout), 'stderr_bytes': len(stderr),
                  'stdout_sha256': hashlib.sha256(stdout).hexdigest(),
                  'stderr_sha256': hashlib.sha256(stderr).hexdigest()}
        (folder / (label + '.stdout')).write_bytes(stdout)
        (folder / (label + '.stderr')).write_bytes(stderr)
        (folder / (label + '.process.json')).write_text(json.dumps(record, indent=2) + '\n',
                                                       encoding='utf-8')
    try:
        result = subprocess.run(list(map(str, cmd)), capture_output=True, env=env, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        try:
            save(error.stdout, error.stderr, 'timeout', None)
        except OSError as write_error:
            # Evidence I/O must not turn the original timeout into another error.
            error.add_note('Could not persist all timeout evidence: ' + type(write_error).__name__)
            raise error from write_error
        raise
    save(result.stdout, result.stderr, 'completed' if result.returncode == 0 else 'nonzero_exit',
         result.returncode)
    if result.returncode:
        raise RuntimeError(f'{label} exited {result.returncode}: {result.stderr[-2000:]!r}')
    return result, time.monotonic() - start

def finite_loads(rows, label):
    """Check every saturation before sorting or reducing a difference vector."""
    for row in rows:
        if not math.isfinite(row['sat']):
            raise RuntimeError(f'{label}: non-finite saturation')

def load_coordinates(rows, label):
    """Index every recorded coordinate without silently discarding duplicates."""
    if not isinstance(rows, list) or not rows:
        raise RuntimeError(f'Load rows must be a nonempty list: {label}')
    values = {}
    indexed = []
    for index, row in enumerate(rows):
        try:
            key = (row['t'], str(row['from']), str(row['to']))
            value = row['sat']
            duplicate = key in values
        except (KeyError, TypeError) as error:
            raise RuntimeError(f'Invalid load row: {label}[{index}]') from error
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise RuntimeError(f'Invalid saturation: {label}[{index}]')
        if duplicate:
            raise RuntimeError(f'Duplicate load coordinate: {label}[{index}]')
        values[key] = value
        indexed.append((index, value))
    # Retain the landed finite-number contract and its diagnostics.
    finite_loads(rows, label)
    for index, value in indexed:
        if value < 0:
            raise RuntimeError(f'Invalid saturation: {label}[{index}]')
    return values

def validated_loads(checks, diagnostic, expected_keys=None, label='benchmark'):
    """Require matching load universes before ranking or reconciliation.

    Values, sorting, the existing 2e-9 tolerance, and cost handling are unchanged.
    Agreement among reports is not an independent topology-completeness proof.
    """
    score_values = load_coordinates(checks[6]['saturations'], f'{label}: checker-6')
    actual = load_coordinates(checks[12]['saturations'], f'{label}: checker-12')
    predicted = load_coordinates(diagnostic['loads'], f'{label}: diagnostic')
    if score_values.keys() != actual.keys() or actual.keys() != predicted.keys():
        raise RuntimeError('Load key mismatch across checker precision and diagnostics')
    keys = frozenset(actual)
    if expected_keys is not None and keys != expected_keys:
        raise RuntimeError('Load key mismatch across solvers')
    error = max(abs(actual[key] - value) for key, value in predicted.items())
    if error >= 2e-9:
        raise RuntimeError(f'Load disagreement: {error}')
    return sorted(score_values.values(), reverse=True), error, keys

def reserve_outputs(output, instances, solvers, metadata):
    """Give this invocation exclusive ownership of its evidence destinations.

    Existing unrelated files (including explicit resume inputs) are allowed.
    Never overwrite an earlier experiment or consume an earlier trial's files.
    The exclusive experiment file also arbitrates concurrent CLI invocations.
    """
    labels = [label for label, _ in solvers]
    if len(set(labels)) != len(labels) or len(set(instances)) != len(instances):
        raise ValueError('duplicate solver labels or instances share an output cell')
    reserved = [output / name for name in ('experiment.json', 'summary.json')]
    folders = {}
    for name in instances:
        for label in labels:
            folder = (output / name / label).resolve()
            if output not in folder.parents:
                raise ValueError('trial output must be below --output: ' + str(folder))
            for previous in [*reserved, *folders.values()]:
                if folder == previous or folder in previous.parents or previous in folder.parents:
                    raise ValueError('overlapping benchmark output paths: ' + str(folder))
            folders[name, label] = folder
    for path in [*reserved, *folders.values()]:
        if path.exists() or path.is_symlink():
            raise FileExistsError('preserve existing benchmark evidence; choose a fresh --output: ' + str(path))
    output.mkdir(parents=True, exist_ok=True)
    # Check above is diagnostic; x mode, not the check, owns the concurrent race.
    with reserved[0].open('x', encoding='utf-8') as stream:
        json.dump(metadata, stream, indent=2)
    for folder in folders.values():
        folder.mkdir(parents=True, exist_ok=False)
    return folders

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--solver', action='append', required=True, help='label=path')
    ap.add_argument('--seconds', type=float, default=30)
    ap.add_argument('--rounds', type=int)
    ap.add_argument('--workers', type=int, default=2)
    ap.add_argument('--instances', nargs='+', default=[f'setB-{i:02}' for i in range(1,13)])
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--checker', type=Path, default=ROOT/'bin'/('checker.exe' if os.name == 'nt' else 'checker'))
    ap.add_argument('--data', type=Path, help='Extracted pinned official challenge root')
    ap.add_argument('--resume-dir', type=Path)
    args = ap.parse_args()
    # Reject unusable budgets before reading inputs, reserving evidence, or starting work.
    # Zero seconds/rounds are valid no-search baseline requests.
    if not math.isfinite(args.seconds) or args.seconds < 0:
        ap.error('--seconds must be finite and >= 0')
    if args.rounds is not None and args.rounds < 0:
        ap.error('--rounds must be >= 0')
    if args.workers < 1:
        ap.error('--workers must be >= 1')
    if args.data:
        data = args.data.resolve()
    else:
        paths = json.loads((ROOT/'paths.json').read_text(encoding='utf-8-sig'))
        data = Path(paths['challenge'])
    solvers = [(label, Path(path).resolve()) for label, path in (s.split('=', 1) for s in args.solver)]
    args.output = args.output.resolve()
    args.checker = args.checker.resolve()
    metadata = {'started_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
        'platform':platform.platform(), 'benchmark_sha256':digest(__file__), 'seconds_per_solver':args.seconds,
        'rounds':args.rounds,'workers':args.workers,'checker_sha256':digest(args.checker),
        'challenge_commit':'d84d319a7fdb8de3b1866830d2eaa2937871e5ae',
        'networktools_commit':'aebafc9ee91891e5d721bb86725e8cf1533877d1',
        'solvers':{label:{'path':str(path),'sha256':digest(path)} for label,path in solvers}}
    folders = reserve_outputs(args.output, args.instances, solvers, metadata)
    def trial(name):
        prefix = data / name[:4] / name
        inputs = [Path(str(prefix)+suffix) for suffix in ('-net.json','-tm.json','-scenario.json')]
        rows = []
        scores = []
        expected_keys = None
        for label, solver in solvers:
            folder = folders[name, label]
            solution, stats = folder/'solution.json', folder/'stats.json'
            env = dict(os.environ,SEDGE_SECONDS=str(args.seconds), SEDGE_STATS=str(stats))
            env.pop('CLOUD_INITIAL_SOLUTION', None)
            env.pop('SEDGE_MAX_ROUNDS', None)
            if args.rounds is not None: env['SEDGE_MAX_ROUNDS'] = str(args.rounds)
            if args.resume_dir: env['CLOUD_INITIAL_SOLUTION'] = str((args.resume_dir/name/'solution.json').resolve())
            _, wall = execute([solver,*inputs,solution],folder,'solver',env,timeout=max(90,args.seconds+90))
            check_times = {}
            checks = {}
            for decimals in (6,12):
                command = [args.checker,'--net',inputs[0],'--tm',inputs[1],'--scenario',inputs[2],
                           '--srpaths',solution,'--max-decimal-places',decimals]
                result, duration = execute(command,folder,f'checker-{decimals}',timeout=180)
                check = json.loads(result.stdout)
                if check.get('valid') is not True: raise RuntimeError(f'{name}/{label}: checker rejected')
                checks[decimals],check_times[decimals] = check,duration
            diagnostic = json.loads(stats.read_text())
            score, error, expected_keys = validated_loads(
                checks, diagnostic, expected_keys, f'{name}/{label}')
            if sum(diagnostic['budget_used']) != checks[12]['total_cost']: raise RuntimeError('Cost disagreement')
            row = {'instance':name,'solver':label,'valid':True,'mlu_6':score[0],
                   'total_cost':checks[6]['total_cost'],'wall_seconds':wall,'checker_seconds':check_times,
                   'accepted_moves':diagnostic['accepted'],'attempted_moves':diagnostic['attempted'],
                   'max_load_error':error,'load_count':len(score),'solution_sha256':digest(solution),
                   'input_sha256':{p.name:digest(p) for p in inputs}}
            if scores:
                baseline = scores[0]
                row['vs_first'] = 'win' if score < baseline else 'loss' if score > baseline else 'tie'
                row['first_difference_rank'] = next((i+1 for i,(a,b) in enumerate(zip(baseline,score)) if a!=b),None)
            scores.append(score)
            rows.append(row)
            (folder/'result.json').write_text(json.dumps(row,indent=2))
            print(json.dumps(row),flush=True)
        return rows
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(trial,args.instances))
    metadata['results'] = results
    (args.output/'summary.json').write_text(json.dumps(metadata,indent=2))

if __name__ == '__main__': main()
