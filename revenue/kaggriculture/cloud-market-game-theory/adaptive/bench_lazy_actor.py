# SPDX-License-Identifier: Apache-2.0
"""Compare offer materialization using the existing saved-observation profiler.

No engine, game, source export, production patch or provider call. Two isolated
copies differ by one eager list() expression. Timing stays in profile_saved.py;
this module coordinates it and separately records state/work correspondence.
"""
from __future__ import annotations

import argparse
import ast
import copy
from dataclasses import asdict, is_dataclass
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile

LAZY = 'offers = (self._offers(cfg, base)'
EAGER = 'offers = (list(self._offers(cfg, base))'
RUNTIME = Path('cloud-market-game-theory/adaptive/runtime.py')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def eager_source(source):
    """Only materialize the same existing generator, at the same call site."""
    if source.count(LAZY) != 1 or EAGER in source:
        raise ValueError('expected exactly one unmodified lazy offer call site')
    result = source.replace(LAZY, EAGER)
    ast.parse(result)
    return result


def read_module(path, name):
    """Compile the recorded source bytes; do not consume timestamp .pyc files."""
    path = Path(path).resolve()
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
    return module


def plain(value):
    if is_dataclass(value):
        return plain(asdict(value))
    if isinstance(value, dict):
        # Some history maps use tuple keys. Preserve typed keys as pairs.
        if all(isinstance(key, str) for key in value):
            return {key: plain(item) for key, item in value.items()}
        rows = [[plain(key), plain(item)] for key, item in value.items()]
        return sorted(rows, key=lambda row: canonical(row[0]))
    if isinstance(value, set):
        return sorted((plain(item) for item in value), key=canonical)
    if isinstance(value, (list, tuple)) or type(value).__name__ == 'deque':
        return [plain(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError('unsupported snapshot type: ' + type(value).__name__)


def decision_snapshot(actor):
    """Economic/continuation state, excluding evaluation-count diagnostics.

    Empty history keys inserted by an unused read are not economic observations.
    Actual nonempty observations and all selected plans/trees remain compared.
    Eager _offered_index names its LAST generated offer, not its accepted one;
    therefore work diagnostics are deliberately outside this decision snapshot.
    """
    trans = actor.transformer
    hist = actor.history
    return plain({
        'active': trans.selector.active, 'completed': trans.selector.completed,
        'draws': trans.selector.draws, 'tree': trans.tree,
        'branch_done': trans.branch_done, 'last': actor.last,
        'transform_counts': trans.counts,
        'continuation': {k: v for k, v in vars(trans.continuation).items() if k != 'selector'},
        'history': {'bins': {k: v for k, v in hist.bins.items() if v},
                    'records': {k: v for k, v in hist.records.items() if v},
                    'last': hist.last, 'identified': hist.identified,
                    'censored': hist.censored},
        'last_fill': actor.last_fill, 'last_flow': actor.last_flow,
        'previous_sales': actor.previous_sales,
        'parent_diagnostics': actor.parent.diagnostics,
    })


def trace(args):
    """Separate untimed instrumentation; one real parent through each Agent.act."""
    profiler = read_module(args.profiler, 'cove_existing_profiler')
    receipt, _ = profiler.load_execution_receipt(args.receipt)
    cfg, rows, input_info = profiler.load_workload(args.input, args.seat, 719, args.receipt)
    wanted_seed = str(receipt['candidate_pythonhashseed'] % (2**32))
    if os.environ.get('PYTHONHASHSEED') != wanted_seed:
        raise ValueError('trace process must start with receipt PYTHONHASHSEED')
    random.seed(receipt['candidate_actor_rng_seed'])
    before = profiler.source_rows(args.source_root)
    path = args.source_root / RUNTIME
    sys.path.insert(0, str(path.parent))
    module = read_module(path, 'cove_adaptive_target')
    actor = module.Agent('adaptive')
    records = []
    status, failure = 'error', None
    try:
        for row in rows:
            obs = copy.deepcopy(row['observation'])
            configuration = copy.deepcopy(row.get('configuration', cfg))
            configuration.pop('seed', None)
            pristine = canonical([obs, configuration])
            action = actor.act(obs, configuration)
            snapshot = decision_snapshot(actor)
            records.append({'step': obs['step'], 'action': action,
                            'state': snapshot, 'work': copy.deepcopy(actor.offer_work),
                            'inputs_unchanged': canonical([obs, configuration]) == pristine})
        status = 'complete'
    except Exception as exc:
        failure = {'type': type(exc).__name__, 'message': str(exc)[:500]}
    result = {'status': status, 'failure': failure, 'input': input_info,
              'source_hashes': before,
              'sources_unchanged': before == profiler.source_rows(args.source_root),
              'records': records,
              'work_index_semantics': 'eager admitted_index is last generated; compare selected active key instead'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('xb') as out:
        out.write(gzip.compress(canonical(result) + b'\n', mtime=0))
    return 0 if status == 'complete' else 2


def compare_traces(lazy, eager):
    issues = []
    for name, item in [('lazy', lazy), ('eager', eager)]:
        if item.get('status') != 'complete' or item.get('sources_unchanged') is not True:
            issues.append(name + ' incomplete or changed source')
    if lazy.get('input') != eager.get('input'):
        issues.append('input identities differ')
    left, right = lazy.get('records', []), eager.get('records', [])
    if len(left) != len(right) or not left:
        issues.append('record counts differ or are empty')
    actions, states, mutations = [], [], []
    for a, b in zip(left, right):
        step = a['step']
        if step != b['step'] or a['action'] != b['action']:
            actions.append(step)
        if a['state'] != b['state']:
            states.append(step)
        if not a['inputs_unchanged'] or not b['inputs_unchanged']:
            mutations.append(step)
    totals = {}
    for label, records in [('lazy', left), ('eager', right)]:
        totals[label] = {field: sum(row['work'][field] for row in records)
                        for field in ('captured_windows', 'inspected_windows', 'compiled_windows')}
        totals[label]['calls_with_captures'] = sum(row['work']['captured_windows'] > 0 for row in records)
        totals[label]['max_captured_windows'] = max((row['work']['captured_windows'] for row in records), default=0)
    savings = [{'step': a['step'], 'lazy_compiled': a['work']['compiled_windows'],
                'eager_compiled': b['work']['compiled_windows']}
               for a, b in zip(left, right)
               if a['work']['compiled_windows'] != b['work']['compiled_windows']]
    return {'complete_correspondence': not (issues or actions or states or mutations),
            'issues': issues, 'calls': len(left), 'action_differences': actions,
            'state_differences': states, 'input_mutations': mutations,
            'work_totals': totals, 'different_compilation_calls': savings}


def summarize_passes(passes):
    import statistics
    out = {}
    for mode, rows in passes.items():
        if not rows or any(r.get('status') != 'complete' or not r.get('calls')
                           or r.get('sources_unchanged') is not True for r in rows):
            raise ValueError('incomplete timing passes')
        out[mode] = {'passes': len(rows),
            'action_hashes': sorted({r['action_sequence_sha256'] for r in rows}),
            'total_action_s': [sum(c['wall_s'] for c in r['calls']) for r in rows],
            'p99_s': [r['p99_call_s'] for r in rows],
            'max_s': [max(c['wall_s'] for c in r['calls']) for r in rows],
            'load_through_first_s': [r['target_load_through_first_attempt_wall_s'] for r in rows],
            'expected_action_mismatches': [r['expected_actions']['mismatches'] for r in rows]}
        for key in ('total_action_s', 'p99_s', 'max_s', 'load_through_first_s'):
            out[mode]['median_' + key] = statistics.median(out[mode][key])
    hashes = {h for row in out.values() for h in row['action_hashes']}
    out['all_action_hashes_equal'] = len(hashes) == 1
    out['median_action_time_reduction_pct'] = 100 * (1 - out['lazy']['median_total_action_s'] / out['eager']['median_total_action_s'])
    return out


def _retain_child_failure(output, log, phase, error, *, stdout=b'', stderr=b'',
                          returncode=None):
    """Retain observed bytes, not a successful measurement or inferred result.

    A timeout can carry bytes even when no child JSON was returned. Preserve the
    original exception if storage itself fails; report only error classes in
    notes. Streams retain the existing stdout-then-stderr concatenation order.
    """
    data = (stdout or b'') + (stderr or b'')
    problems = []
    try:
        log.write_bytes(data)
    except OSError as failure:
        problems.append('log:' + type(failure).__name__)
    record = {
        'schema': 'titan.lazy-actor-child-failure.v1', 'complete': False,
        'phase': phase, 'error_type': type(error).__name__,
        'kind': ('timeout' if isinstance(error, subprocess.TimeoutExpired)
                 else 'exit' if returncode is not None else 'launch'),
        'returncode': returncode,
        'timeout_seconds': getattr(error, 'timeout', None),
        'expected_output': output.name, 'child_output_present': output.is_file(),
        'child_output_validated': False, 'log': log.name,
        'captured_log_bytes': len(data), 'captured_log_sha256': sha(data),
        'retention_errors': list(problems),
    }
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent, prefix='.child-failure-',
                                         suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(canonical(record) + b'\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output.parent / 'FAILURE.json')
    except OSError as failure:
        problems.append('record:' + type(failure).__name__)
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError as failure:
                problems.append('temporary:' + type(failure).__name__)
    for problem in problems:
        error.add_note('Child evidence retention failed: ' + problem)


def _run_child(command, *, environment, output, log, phase):
    """Use the same subprocess deadline; retain failed attempts before raising."""
    try:
        run = subprocess.run(command, env=environment, capture_output=True, timeout=180)
    except subprocess.TimeoutExpired as error:
        _retain_child_failure(output, log, phase, error,
                              stdout=error.stdout, stderr=error.stderr)
        raise
    except OSError as error:
        _retain_child_failure(output, log, phase, error)
        raise
    if run.returncode:
        error = RuntimeError(f'{phase} failed; retained {output}')
        _retain_child_failure(output, log, phase, error, stdout=run.stdout,
                              stderr=run.stderr, returncode=run.returncode)
        raise error
    log.write_bytes(run.stdout + run.stderr)
    return run


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--profiler', type=Path, required=True)
    p.add_argument('--source-root', type=Path, required=True, help='compact complete kaggriculture source closure')
    p.add_argument('--timing-source', type=Path, required=True)
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--receipt', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True, help='new directory; trace-worker mode takes new .json.gz')
    p.add_argument('--rounds', type=int, default=3)
    p.add_argument('--seat', type=int, default=0, choices=(0, 1))
    p.add_argument('--trace-worker', action='store_true')
    args = p.parse_args()
    for name in ('profiler', 'source_root', 'timing_source', 'input', 'receipt', 'output'):
        setattr(args, name, getattr(args, name).resolve())
    if args.trace_worker:
        return trace(args)
    if args.rounds < 1 or args.rounds > 10:
        p.error('rounds must be 1..10')
    if args.output.is_relative_to(args.source_root) or args.output.exists():
        p.error('use a new output directory outside the source tree')
    text = (args.source_root / RUNTIME).read_text()
    eager = eager_source(text)
    args.output.mkdir(parents=True)
    profiler = read_module(args.profiler, 'cove_profiler_contract')
    execution, _ = profiler.load_execution_receipt(args.receipt)
    environment = dict(os.environ, PYTHONHASHSEED=str(execution['candidate_pythonhashseed'] % (2**32)))
    roots = {}
    for mode in ('lazy', 'eager'):
        root = args.output / (mode + '-source')
        shutil.copytree(args.source_root, root, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        if mode == 'eager':
            (root / RUNTIME).write_text(eager)
        roots[mode] = root
    common = ['--factory', 'Agent', '--factory-kwargs', '{"mode":"adaptive"}',
              '--timing-source', str(args.timing_source), '--replay', str(args.input),
              '--input-receipt', str(args.receipt), '--seat', str(args.seat),
              '--max-decisions', '719', '--classification', 'retained-development-off-policy']
    passes = {'lazy': [], 'eager': []}
    for index in range(args.rounds):
        order = ('lazy', 'eager') if index % 2 == 0 else ('eager', 'lazy')
        for mode in order:
            output = args.output / f'{index}-{mode}.json'
            command = [sys.executable, '-B', str(args.profiler), '--worker-mode', 'ordinary',
                       '--entrypoint', str(roots[mode] / RUNTIME), '--source-root', str(roots[mode]),
                       *common, '--output', str(output)]
            _run_child(command, environment=environment, output=output,
                       log=args.output / f'{index}-{mode}.log', phase=f'{mode} pass')
            passes[mode].append(json.loads(output.read_text()))
            print(f'complete {index} {mode}', flush=True)
    traced = {}
    for mode in ('lazy', 'eager'):
        output = args.output / f'{mode}-trace.json.gz'
        command = [sys.executable, '-B', str(Path(__file__).resolve()), '--trace-worker',
                   '--profiler', str(args.profiler), '--source-root', str(roots[mode]),
                   '--timing-source', str(args.timing_source), '--input', str(args.input),
                   '--receipt', str(args.receipt), '--seat', str(args.seat), '--output', str(output)]
        _run_child(command, environment=environment, output=output,
                   log=args.output / f'{mode}-trace.log', phase=f'{mode} trace')
        traced[mode] = json.loads(gzip.decompress(output.read_bytes()))
    result = {'schema': 'titan.lazy-actor-comparison.v1',
              'benchmark_sha256': sha(Path(__file__).read_bytes()),
              'profiler_sha256': sha(args.profiler.read_bytes()),
              'timing_source_sha256': sha(args.timing_source.read_bytes()),
              'runtime_sha256': sha(text.encode()), 'eager_runtime_sha256': sha(eager.encode()),
              'source_only_difference': str(RUNTIME),
              'input': traced['lazy']['input'], 'environment': passes['lazy'][0]['environment'],
              'comparison': compare_traces(traced['lazy'], traced['eager']),
              'timing': summarize_passes(passes),
              'limits': ['Off-policy retained observations, not a new game or strength result.',
                         'Repeated timings are one workload, not independent economic evidence.',
                         'Traced state instrumentation is separate from ordinary timing.',
                         'Eager unused-window errors can change fallback; no general error parity is promised.',
                         'Source closure is explicitly pinned; later main changes are not inherited.']}
    (args.output / 'RESULTS.json').write_bytes(json.dumps(result, indent=2, allow_nan=False).encode() + b'\n')
    print(json.dumps({'comparison': result['comparison'], 'timing': result['timing']}, indent=2))
    return 0 if result['comparison']['complete_correspondence'] and result['timing']['all_action_hashes_equal'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
