# SPDX-License-Identifier: Apache-2.0
"""Independent full-native completion controls for two existing V4 repairs.

This runs four isolated scratch packages; it never changes a production package.
All native collaborators, configuration, interpreter and loader are byte-pinned.
Fault injection is explicit: exact-line cancellation using the active timer's
own sentinel, plus timed initialization stalls. No game-strength gate is implied.
"""
from __future__ import annotations

import argparse
import ast
import concurrent.futures
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time

SOURCE_SHA256 = 'e87d70dd3bcf5aea1e929f1a5dbdc86f3cc33d8a0b3492986f2970fc8e774be2'
RUNTIME_BEFORE = 'b952c9c228ecbde592bf3d2df01638677abb0d24'
RUNTIME_AFTER = 'c42344489a3f50d91e2abe8d85d4ee15f34732a1'
ADAPTER_BEFORE = '664aa4f8a21368c388dfa6714406519b6535ef7f'
ADAPTER_AFTER = '8f36fbe5d05fb71731ef4b799a664189a6dae153'
RECOVERY_SOURCE = '060e8c2896bb18e3372a4bd3e90087c33520b1c1'
TERMINAL_SOURCE = '0ee0294016224d952adc813bb6b035fe7e4d5be0'
ADAPTER = 'reference/titan-current/deadline_adapter.py'
ARMS = ('base', 'terminal', 'recovery', 'both')


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def load_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, 'module spec unavailable')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def verify_package(root, arm):
    source = (root / 'SOURCE.json').read_bytes()
    require(sha(source) == SOURCE_SHA256, 'unrecognized complete package manifest')
    manifest = json.loads(source)['runtime']
    require(len(manifest) == 109, 'manifest cardinality changed')
    changes = {}
    for relative, item in manifest.items():
        path = root / relative
        require(path.is_file() and not path.is_symlink(), 'nonregular/missing member: ' + relative)
        raw = path.read_bytes()
        if relative == 'titan_runtime.py' and arm in ('recovery', 'both'):
            require(blob(raw) == RUNTIME_AFTER, 'unexpected runtime postimage')
            changes[relative] = blob(raw)
        elif relative == ADAPTER and arm in ('terminal', 'both'):
            require(blob(raw) == ADAPTER_AFTER, 'unexpected adapter postimage')
            changes[relative] = blob(raw)
        else:
            require(len(raw) == item['bytes'] and sha(raw) == item['sha256'],
                    'native dependency drift: ' + relative)
    return {'manifest_sha256': SOURCE_SHA256, 'native_members': len(manifest),
            'changed_members': changes, 'manifest_records_sha256': sha(canonical(manifest))}


def child(root, arm, output):
    evidence = {'arm': arm, 'pins': verify_package(root, arm),
                'python': sys.version.split()[0], 'optimized': not __debug__}
    sys.path.insert(0, str(root))
    import titan_runtime as T
    import main as entry
    loader = load_file('_completion_official_loader', root / 'checks/reference/evaluator/loader.py')
    engine, engine_hashes = loader.get_engine(root / 'checks/reference/engine')
    S = loader.Struct
    features = json.loads((root / 'TITAN-CONFIG.json').read_bytes())
    init_code = T.TitanAgent._initialize.__code__
    original_signal = signal.getsignal(signal.SIGALRM)
    original_alarm = signal.getitimer(signal.ITIMER_REAL)
    require(original_alarm == (0.0, 0.0), 'preexisting timer: isolated child required')
    baseline_recovered = arm in ('recovery', 'both')
    terminal_fixed = arm in ('terminal', 'both')
    counters = {'native_entrypoint_calls': 0, 'official_interpreter_calls': 0,
                'injected_owned_cancellations': 0, 'actual_timer_stalls': 0}

    def instance(budget=None):
        data = dict(features)
        if budget is not None:
            data.update(budget_seconds=budget, reserve_seconds=0.01)
        return entry._new_instance(root, data)

    def config():
        return S({key: value.get('default') if isinstance(value, dict) else value
                  for key, value in engine.specification['configuration'].items()})

    def fixture(seat, case, step=718):
        cfg = config()
        cfg.weedSpawnChance = 0
        cfg.maxMarketOrdersPerTurn = 0 if case == 'minimum_one' else 10
        farms = [engine._new_farm(10, 0), engine._new_farm(10, 0)]
        market = engine._new_market()
        engine._refresh_prices(market)
        town = engine._new_town()
        state = []
        for player in range(2):
            private = engine._new_private()
            if player == seat:
                if case == 'crowded_prefix':
                    private['shed'] = dict([(a, 1) for a in engine.ANIMALS] +
                        [(p, 50 if p == 'WOOL' else 30 if p == 'FERTILIZER' else 1)
                         for p in engine.PRODUCTS])
                elif case == 'capacity_drop':
                    private['shed'] = {'MELON': 98, 'MILK': 1}
                    farms[player]['farmer'] = [4, 4]
                    farms[player]['hands'] = [[4, 5], [0, 0]]
                    private['inventories'] = [{'WHEAT': 2}, {'WOOL': 2}, {'MILK': 9}]
                else:
                    private['shed'] = {'MILK': 1}
            obs = S(player=player, step=step, day=step // 24, hour=step % 24,
                    farms=farms, market=market, town=town, private=private)
            state.append(S(observation=obs, action=T.deadline.legal_pass(obs), status='ACTIVE', reward=0))
        return state, S(configuration=cfg, done=False, info={'seed': 9417})

    def settle(state, env, seat, action):
        world, context = copy.deepcopy((state, env))
        world[seat].action = copy.deepcopy(action)
        engine.interpreter(world, context)
        counters['official_interpreter_calls'] += 1
        require(all(row.status == 'DONE' for row in world), 'terminal transition not DONE')
        return {'cash': [row.reward for row in world], 'state_sha256': sha(canonical(world))}

    def opening(seed):
        cfg = config()
        cfg.seed = seed
        env = S(configuration=cfg, done=False, info={})
        state = [S(observation=S(), action={}, status='ACTIVE', reward=0) for _ in range(2)]
        engine.interpreter(state, env)
        counters['official_interpreter_calls'] += 1
        return state, env

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        def invoke(a, obs, cfg, worker, code=None, line=None, foreign=None):
            entry._INSTANCE = a
            saved = copy.deepcopy((obs, cfg))
            hits = []
            def trace(frame, event, arg):
                if frame.f_code is code and event == 'line' and frame.f_lineno == line:
                    hits.append(line)
                    timer = T.deadline._ACTIVE_TIMER.get()
                    require(timer is not None, 'injection did not reach an actual active timer')
                    raise foreign if foreign is not None else timer.expired
                return trace
            def run():
                previous = sys.gettrace()
                started = time.perf_counter()
                try:
                    if code is not None:
                        sys.settrace(trace)
                    out = entry.agent(obs, cfg)
                    return {'action': out, 'elapsed': time.perf_counter() - started}
                except (AttributeError, T.deadline.DeadlineExceeded) as error:
                    return {'exception': type(error).__name__, 'message': str(error),
                            'foreign_identity': error is foreign}
                finally:
                    sys.settrace(previous)
                    require(T.deadline._ACTIVE_TIMER.get() is None, 'timer context leaked')
            result = pool.submit(run).result(timeout=5) if worker else run()
            counters['native_entrypoint_calls'] += 1
            require((obs, cfg) == saved, 'entrypoint mutated its input')
            if code is not None:
                require(hits == [line], f'cutpoint not reached exactly once: line={line}, worker={worker}, hits={hits}, result={result}')
                if foreign is None:
                    counters['injected_owned_cancellations'] += 1
            require(signal.getsignal(signal.SIGALRM) is original_signal, 'caller signal handler changed')
            require(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0), 'alarm leaked')
            return result

        # Enumerate actually executed native initialization lines, not a fake
        # initializer or guessed range. The final ready=True line is cut BEFORE
        # execution, so every tested cut represents incomplete initialization.
        lines = set()
        def collect(frame, event, arg):
            if frame.f_code is init_code and event == 'line':
                lines.add(frame.f_lineno)
            return collect
        lines_by_lifecycle = {}
        for stale in (False, True):
            a = instance()
            if stale:
                a._initialize()
                a.ready = False
            lines.clear()
            previous_trace = sys.gettrace()
            try:
                sys.settrace(collect)
                a._initialize()
            finally:
                sys.settrace(previous_trace)
            lines_by_lifecycle[stale] = sorted(lines)
        require(len(lines_by_lifecycle[False]) == 38, 'fresh initializer execution topology changed')
        evidence['initialization_lines'] = {str(k): v for k,v in lines_by_lifecycle.items()}
        matrix = []
        for case in ('minimum_one', 'crowded_prefix', 'capacity_drop'):
            for seat in (0, 1):
                state, env = fixture(seat, case)
                obs = state[seat].observation
                expected = T.deadline.terminal_liquidation_fallback(obs, env.configuration)
                for stale in (False, True):
                    for worker in (False, True):
                        for line in lines_by_lifecycle[stale]:
                            a = instance()
                            if stale:
                                a._initialize()
                                a.ready = False
                            result = invoke(a, obs, env.configuration, worker, init_code, line)
                            row = {'case': case, 'seat': seat, 'stale': stale, 'worker': worker, 'line': line}
                            if 'exception' in result:
                                require(not baseline_recovered, 'repaired native path raised: ' + str(result))
                                require(result['exception'] == 'AttributeError', 'unexpected predecessor failure')
                                row['exception'] = result['exception']
                                row['message'] = result['message']
                            else:
                                if baseline_recovered:
                                    require(result['action'] == expected, 'incomplete initialization changed fallback')
                                    require(a.diagnostics.get('finalizer_skipped') == 'incomplete_initialization',
                                            'missing incomplete-initialization receipt')
                                require(not a.ready, 'interrupted instance remained ready')
                                require(a.diagnostics['parent_calls'] == 0, 'production ran after initialization cut')
                                row['action'] = result['action']
                                row.update(settle(state, env, seat, result['action']))
                            matrix.append(row)
        require(len(matrix) == 3 * 2 * 2 * sum(map(len, lines_by_lifecycle.values())), 'missing native cutpoint cells')
        errors = [row for row in matrix if 'exception' in row]
        if baseline_recovered:
            require(not errors, 'combined native initialization did not close')
        else:
            require(bool(errors), 'predecessor contrast did not reproduce')
        evidence['cutpoints'] = {'cells': len(matrix), 'errors': len(errors),
                                'rows_sha256': sha(canonical(matrix)), 'rows': matrix}

        # Fresh/reconstructed next-callback recovery through real controllers.
        followups = []
        for worker in (False, True):
            for seat in (0, 1):
                for stale in (False, True):
                    active_lines = lines_by_lifecycle[stale]
                    for cut in (active_lines[0], active_lines[len(active_lines)//2], active_lines[-1]):
                        state, env = opening(9417)
                        for row in state:
                            row.observation.step = 0
                        a = instance()
                        if stale:
                            a._initialize()
                            a.ready = False
                        # Step 0 would cause main to replace our instance; step 1
                        # uses the actual instance supplied above on a fresh map.
                        for row in state:
                            row.observation.step = 1
                            row.observation.day = 0
                            row.observation.hour = 1
                        first = invoke(a, state[seat].observation, env.configuration, worker, init_code, cut)
                        if 'exception' not in first:
                            state[seat].action = first['action']
                        else:
                            state[seat].action = T.deadline.legal_pass(state[seat].observation)
                        state[1-seat].action = T.deadline.legal_pass(state[1-seat].observation)
                        engine.interpreter(state, env)
                        counters['official_interpreter_calls'] += 1
                        for row in state:
                            row.observation.step = 2
                        second = invoke(a, state[seat].observation, env.configuration, worker)
                        require('action' in second and a.diagnostics['status'] == 'completed',
                                'native reconstruction did not complete: ' + str(second))
                        followups.append({'worker': worker, 'seat': seat, 'stale': stale, 'cut': cut,
                                          'prior_error': 'exception' in first, 'action': second['action']})
        evidence['followups'] = {'cases': len(followups), 'sha256': sha(canonical(followups))}

        # Actual unmodified seeded opening prefixes; both seats, both execution
        # modes. Keep raw unit rows. Do NOT use loader.play's extra-hand assert.
        prefixes = []
        for worker in (False, True):
            for seat in (0, 1):
                state, env = opening(9417)
                a = None
                trace_rows = []
                for step in range(24):
                    for row in state:
                        row.observation.step = step
                    result = invoke(a, state[seat].observation, env.configuration, worker)
                    require('action' in result, 'normal native callback raised')
                    a = entry._INSTANCE
                    require(a is not None and a.diagnostics['status'] == 'completed',
                            'normal-prefix timeout/noise; not an identity certificate')
                    state[seat].action = result['action']
                    state[1-seat].action = engine.starter_agent(copy.deepcopy(state[1-seat].observation))
                    engine.interpreter(state, env)
                    counters['official_interpreter_calls'] += 1
                    trace_rows.append({'action': result['action'], 'state': copy.deepcopy(state)})
                prefixes.append({'worker': worker, 'seat': seat, 'callbacks': 24,
                                 'action_transition_sha256': sha(canonical(trace_rows))})
        evidence['native_opening_prefixes'] = prefixes

        # Warm selected-action cancellation must retain the native fallback and
        # finalizer path. This intentionally does not change terminal precedence.
        runtime_lines = (root / 'titan_runtime.py').read_text().splitlines()
        selected_line = next(i+1 for i, text in enumerate(runtime_lines)
                             if text.strip() == "stage = 'selected_transform'") + 1
        selected = []
        for worker in (False, True):
            for seat in (0, 1):
                for step in (1, 718):
                    a = instance()
                    a._initialize()
                    state, env = fixture(seat, 'crowded_prefix', step=step)
                    result = invoke(a, state[seat].observation, env.configuration, worker,
                                    T.TitanAgent.act.__code__, selected_line)
                    require('action' in result, 'warm selected cancellation raised')
                    require(a.diagnostics.get('fallback_stage') == 'selected_transform', 'wrong warm stage')
                    require('finalizer_skipped' not in a.diagnostics, 'recovery incorrectly skipped warm finalization')
                    row = {'worker': worker, 'seat': seat, 'step': step, 'action': result['action']}
                    if step == 718:
                        row.update(settle(state, env, seat, result['action']))
                    selected.append(row)
        evidence['warm_selected'] = {'cases': len(selected), 'rows': selected,
                                    'sha256': sha(canonical(selected))}

        # Real wall-clock deadlines, separate from exact-line fault injection.
        # Only a test seam stalls initialization; no native collaborator is
        # replaced with a fabricated controller, SELL policy or finalizer.
        timed = []
        for worker in (False, True):
            for seat in (0, 1):
                a = instance(budget=0.04)
                original_init = a._initialize
                def stalled():
                    until = time.perf_counter() + 0.15
                    while time.perf_counter() < until:
                        pass
                    return original_init()
                a._initialize = stalled
                state, env = fixture(seat, 'minimum_one')
                result = invoke(a, state[seat].observation, env.configuration, worker)
                counters['actual_timer_stalls'] += 1
                if baseline_recovered:
                    require('action' in result, 'actual deadline failed in repaired runtime')
                    require(result['elapsed'] < 1, 'real cancellation did not bound the stall')
                    require(a.diagnostics.get('finalizer_skipped') == 'incomplete_initialization',
                            'actual timer did not exercise recovery')
                    require(result['action'] == T.deadline.terminal_liquidation_fallback(
                        state[seat].observation, env.configuration), 'wrong actual timer fallback')
                else:
                    require(result.get('exception') == 'AttributeError', 'timed baseline defect vanished')
                row = {'worker': worker, 'seat': seat,
                       **{key: val for key, val in result.items() if key != 'elapsed'}}
                if 'action' in result:
                    row.update(settle(state, env, seat, result['action']))
                timed.append(row)
        evidence['actual_deadlines'] = timed

        # Foreign cancellation ownership is a hard no-swallow invariant.
        foreign_cases = 0
        for worker in (False, True):
            for seat in (0, 1):
                a = instance()
                state, env = fixture(seat, 'minimum_one')
                foreign = T.deadline.DeadlineExceeded('independent caller sentinel')
                result = invoke(a, state[seat].observation, env.configuration, worker,
                                init_code, min(lines), foreign)
                require(result.get('foreign_identity') is True, 'foreign cancellation was swallowed/replaced')
                foreign_cases += 1
        evidence['foreign_identity_cases'] = foreign_cases

    evidence['pins_after'] = verify_package(root, arm)
    require(evidence['pins_after'] == evidence['pins'], 'native source changed during checks')
    evidence['engine_sha256'] = engine_hashes
    evidence['counters'] = counters
    evidence['passed'] = True
    output.write_bytes(json.dumps(evidence, sort_keys=True, indent=2).encode() + b'\n')
    print(json.dumps({'arm': arm, 'passed': True, 'counters': counters,
                      'cutpoint_errors': evidence['cutpoints']['errors']}), flush=True)


def run(args):
    base = args.base.resolve()
    verify_package(base, 'base')
    terminal_path = args.terminal_dir.resolve() / 'repair_terminal_fallback.py'
    recovery_path = args.recovery_dir.resolve() / 'repair_deadline_recovery.py'
    require(blob(recovery_path.read_bytes()) == RECOVERY_SOURCE, 'recovery transformer drift')
    require(blob(terminal_path.read_bytes()) == TERMINAL_SOURCE, 'terminal transformer drift')
    terminal = load_file('_completion_terminal_repair', terminal_path)
    recovery = load_file('_completion_recovery_repair', recovery_path)
    args.out.mkdir(parents=True, exist_ok=False)
    receipts = {}
    with tempfile.TemporaryDirectory(prefix='titan-current-completion-') as temporary:
        for arm in ARMS:
            scratch = Path(temporary) / arm
            shutil.copytree(base, scratch, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            if arm in ('terminal', 'both'):
                path = scratch / ADAPTER
                path.write_bytes(terminal.repair(path.read_bytes()))
            if arm in ('recovery', 'both'):
                path = scratch / 'titan_runtime.py'
                path.write_bytes(recovery.repair(path.read_bytes()))
            verify_package(scratch, arm)
            result_path = args.out / (arm + '.json')
            command = [sys.executable, '-I'] + (['-O'] if not __debug__ else []) + [
                str(Path(__file__).resolve()), '--child', str(scratch), '--arm', arm,
                '--child-output', str(result_path.resolve())]
            completed = subprocess.run(command, text=True, capture_output=True, timeout=240,
                                       env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
            (args.out / (arm + '.log')).write_text(completed.stdout + completed.stderr)
            require(completed.returncode == 0, 'child failed ' + arm + ': ' + completed.stderr[-5000:])
            result = json.loads(result_path.read_bytes())
            require(result.get('passed') is True and result['arm'] == arm, 'missing completed child')
            receipts[arm] = result
            print(completed.stdout.strip(), flush=True)
    # No repaired/default feature makes any difference to successful callbacks.
    for arm in ARMS[1:]:
        require(receipts[arm]['native_opening_prefixes'] == receipts['base']['native_opening_prefixes'],
                'native opening action/transition identity failed: ' + arm)
        require(receipts[arm]['warm_selected']['sha256'] == receipts['base']['warm_selected']['sha256'],
                'warm selected/finalizer behavior changed: ' + arm)
    for arm in ('recovery', 'both'):
        require(receipts[arm]['cutpoints']['errors'] == 0, 'repaired lifecycle error')
    witness = {}
    for arm, receipt in receipts.items():
        rows = receipt['cutpoints']['rows']
        for case in ('minimum_one', 'crowded_prefix', 'capacity_drop'):
            sample = next(row for row in rows if row['case'] == case and row['seat'] == 0
                          and row['stale'] and not row['worker'])
            witness.setdefault(case, {})[arm] = sample
    require(witness['minimum_one']['recovery']['cash'][0] == 0, 'old minimum-one witness drift')
    require(witness['minimum_one']['both']['cash'][0] == 160, 'composed minimum-one witness missing')
    require(witness['crowded_prefix']['both']['cash'][0] > witness['crowded_prefix']['recovery']['cash'][0],
            'omitted product recovery missing')
    summary = {'schema': 'titan-v4-current-completion/v1', 'passed': True,
               'python': sys.version.split()[0], 'optimized': not __debug__,
               'source_manifest_sha256': SOURCE_SHA256,
               'repair_blobs': {'terminal': TERMINAL_SOURCE, 'recovery': RECOVERY_SOURCE},
               'arms': {arm: {'runtime_blob': RUNTIME_AFTER if arm in ('recovery', 'both') else RUNTIME_BEFORE,
                              'adapter_blob': ADAPTER_AFTER if arm in ('terminal', 'both') else ADAPTER_BEFORE,
                              'counters': row['counters'], 'cutpoint_errors': row['cutpoints']['errors'],
                              'details_sha256': sha((args.out/(arm+'.json')).read_bytes()),
                              'log_sha256': sha((args.out/(arm+'.log')).read_bytes())}
                        for arm, row in receipts.items()},
               'native_opening_prefixes_equal': True, 'warm_selected_equal': True,
               'witnesses': witness,
               'limits': ['constructed terminal states and explicit fault injection',
                          '24-callback opening prefixes, not full games',
                          'unchanged selected-action terminal precedence; legacy PR11913/11927 separate',
                          'no current V4 gameplay-overlay composition or economic-promotion claim',
                          'no production/default/archive/Kaggle change']}
    (args.out / 'SUMMARY.json').write_bytes(json.dumps(summary, sort_keys=True, indent=2).encode()+b'\n')
    verify_package(base, 'base')
    print('CURRENT_COMPLETION_PASS=' + json.dumps({arm: row['counters'] for arm,row in receipts.items()}, sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path)
    parser.add_argument('--terminal-dir', type=Path)
    parser.add_argument('--recovery-dir', type=Path)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--child', type=Path)
    parser.add_argument('--arm', choices=ARMS)
    parser.add_argument('--child-output', type=Path)
    args = parser.parse_args()
    if args.child:
        require(args.arm is not None and args.child_output is not None, 'child arguments required')
        child(args.child.resolve(), args.arm, args.child_output)
    else:
        require(all((args.base, args.terminal_dir, args.recovery_dir, args.out)), 'parent arguments required')
        run(args)


if __name__ == '__main__':
    main()
