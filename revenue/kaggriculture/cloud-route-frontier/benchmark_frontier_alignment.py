# SPDX-License-Identifier: Apache-2.0
"""Compare frontier alignment cost and run the unchanged T06/native-engine join.

No network, policy actor, game initialization or new game seed. Performance
workloads are explicitly synthetic alternatives. Native cases are fixed states.
"""
from __future__ import annotations
import argparse
import ast
from copy import deepcopy
from dataclasses import asdict
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import statistics
import subprocess
import sys
from time import perf_counter
from types import ModuleType
from typing import Any, Callable
import route_frontier as current

BASELINE_REF = '09ee5b81cab4bb5b1237a6c2a20ac66672a68617'
BASELINE_PATH = 'revenue/kaggriculture/cloud-route-frontier/route_frontier.py'
BASELINE_BLOB = '5a08c7a016d0576a38454ac70af98621b26398ca'
KERNEL_BLOB = 'd05b35057509ed706679c0c841a81ffba05a9936'
ENGINE_REF = '28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c'
ENGINE_HASHES = {
    'kaggriculture.py': 'bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e',
    'kaggriculture.json': 'a82c89c1a2315b93f39775d8e025471a01b738647c9772658368ee6b1b6f4867',
    'utils.py': '537b627b11784d424147ef57ebb0369b039bf83c9f891e81f10486b1f552334b',
}


def blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def module_from_bytes(name, data, filename):
    mod = ModuleType(name); mod.__file__ = str(filename)
    sys.modules[name] = mod
    exec(compile(data, str(filename), 'exec'), mod.__dict__)
    return mod


def signature(result):
    return {'kept': [x.name for x in result.kept], 'dominated': list(result.dominated),
            'budget_dropped': list(result.budget_dropped),
            'dominance_comparisons': result.dominance_comparisons,
            'approximate': result.approximate}


def bank(size, scenarios, mode):
    shared = tuple(current.rollout('macro', {'step': 0, 'cash': 0}, [{'delta': 0}],
                   lambda s, a: {'step': 1, 'cash': 0}, context=f's{i:02}')
                   for i in range(scenarios))
    items = []
    for i in range(size):
        traces = shared
        if mode == 'incomparable':
            traces = tuple(current.rollout('macro', {'step': 0, 'cash': 0, 'g': i}, [{}],
                           lambda s, a: dict(s, step=1), context=f's{j:02}')
                           for j in range(scenarios))
        values = ((i, size-i),) * scenarios if mode == 'tradeoff' else ((i, i),) * scenarios
        if i % 2:
            traces, values = traces[::-1], values[::-1]
        items.append(current.Alternative(str(i), traces, ('cash', 'deadline'), values))
    return items


def timings(before, samples):
    rows = []
    for size, scenarios, mode in ((16, 1, 'tradeoff'), (64, 16, 'tradeoff'),
                                  (128, 32, 'tradeoff'), (128, 16, 'dominated'),
                                  (128, 16, 'incomparable')):
        items = bank(size, scenarios, mode)
        expected = signature(before.pareto_frontier(items))
        old, new = [], []
        for _ in range(2):
            before.pareto_frontier(items); current.pareto_frontier(items)
        for index in range(samples):
            funcs = ((before.pareto_frontier, old), (current.pareto_frontier, new))
            if index % 2:
                funcs = funcs[::-1]
            for function, target in funcs:
                start = perf_counter(); result = function(items); elapsed = perf_counter() - start
                target.append(elapsed)
                assert signature(result) == expected
                assert all(any(kept is a for a in items) for kept in result.kept)
        rows.append({'size': size, 'scenarios': scenarios, 'mode': mode,
                     'result': expected, 'baseline_seconds': old, 'candidate_seconds': new,
                     'baseline_median_seconds': statistics.median(old),
                     'candidate_median_seconds': statistics.median(new),
                     'median_reduction_fraction': 1 - statistics.median(new)/statistics.median(old),
                     'timed_exact_matches': samples * 2})
    return rows


class Struct(dict):
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key) from None
    def __setattr__(self, key, value):
        self[key] = value


def engine_module(root):
    for name, digest in ENGINE_HASHES.items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest() != digest:
            raise ValueError(f'Engine input differs: {name}')
    # Retain the original helper verbatim; no random initialization is invoked.
    tree = ast.parse((root/'utils.py').read_text())
    helper = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                  and node.name == 'resolve_episode_seed')
    ns = {'Any': Any, 'Callable': Callable, 'random': random}
    exec(compile(ast.Module(body=[helper], type_ignores=[]), str(root/'utils.py'), 'exec'), ns)
    package, utils = ModuleType('kaggle_environments'), ModuleType('kaggle_environments.utils')
    utils.resolve_episode_seed = ns['resolve_episode_seed']
    prior = {m.__name__: sys.modules.get(m.__name__) for m in (package, utils)}
    try:
        sys.modules[package.__name__] = package; sys.modules[utils.__name__] = utils
        return module_from_bytes('frontier_native_engine', (root/'kaggriculture.py').read_bytes(), root/'kaggriculture.py')
    finally:
        for name, value in prior.items():
            if value is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value


def action(unit='PASS', orders=None):
    return {'farmer': [unit], 'hands': [], 'market': orders or []}


def fixture(engine, position):
    cfg = {k: v.get('default') if isinstance(v, dict) else v
           for k, v in engine.specification['configuration'].items()}
    result = {'step': 716, 'position': position, 'farms': [engine._new_farm(10, 0), engine._new_farm(10, 0)],
              'privates': [engine._new_private(), engine._new_private()],
              'market': engine._new_market(), 'town': engine._new_town(), 'config': cfg,
              'info': {'seed': 0}, 'status': ['ACTIVE', 'ACTIVE'], 'rewards': [0, 0], 'done': False}
    result['privates'][position]['inventories'][0] = {'MILK': 2}
    result['town']['unlocked_shops'] = ['PIZZA_SHOP'] * 4
    return result


def native_join(before, engine, kernel):
    transitions = 0
    traces_record, results = [], []
    def advance(snapshot, own):
        nonlocal transitions
        s = deepcopy(snapshot)
        if s['done']:
            raise ValueError('No action after DONE')
        position, step, cfg = s['position'], s['step'], s['config']
        commands = [action(), action()]; commands[position] = own
        states = [Struct(observation=Struct(step=step, player=i, private=s['privates'][i],
                  farms=s['farms'], market=s['market'], town=s['town'],
                  day=step//cfg['turnsPerDay'], hour=step%cfg['turnsPerDay']),
                  action=commands[i], status=s['status'][i], reward=s['rewards'][i]) for i in (0, 1)]
        engine.interpreter(states, Struct(configuration=Struct(cfg), done=False, info=s['info']))
        transitions += 1
        s['step'] += 1
        s['status'] = [x.status for x in states]; s['rewards'] = [x.reward for x in states]
        s['done'] = any(x.status == 'DONE' for x in states)
        return s
    for position in (0, 1):
        initial = fixture(engine, position); original = deepcopy(initial)
        context = current.exact_key({'engine': ENGINE_REF, 'position': position, 'rival': 'PASS'})
        sell = action('DROP', [['SELL', 'MILK', 2]])
        schedules = [('early', [sell, action(), action()]),
                     ('late', [action(), action(), sell]), ('idle', [action(), action(), action()])]
        traces = [current.rollout(name, initial, commands, advance, context=context) for name, commands in schedules]
        items = [current.Alternative(t.name, (t,), ('terminal_cash', 'cash_after_716'),
                 ((t.state()['farms'][position]['money'], t.state(1)['farms'][position]['money']),),
                 ('DONE',), 'terminal-no-continuation') for t in traces]
        old, new = before.pareto_frontier(items), current.pareto_frontier(items)
        assert signature(old) == signature(new)
        assert [a.name for a in new.kept] == ['early', 'late']
        consumer_results = []
        for bounded in (False, True):
            outcomes = []
            for label, mod, frontier in [('baseline', before, old), ('candidate', current, new)]:
                selected = [a for a in frontier.kept if not bounded or a.values[0][1] >= 100]
                selected_traces = [t for a in selected for t in a.traces]
                model = mod.kernel_model(kernel, selected_traces, lambda s, _: s['farms'][position]['money'])
                r = kernel.search(model, [initial], [context], selected[0].name,
                                  limits=kernel.Limits(seconds=2, max_depth=1))
                record = asdict(r); record.pop('elapsed_seconds')
                outcomes.append(record)
            assert outcomes[0] == outcomes[1]
            assert outcomes[1]['action'] == ('early' if bounded else 'late')
            consumer_results.append({'cash_deadline': 100 if bounded else None, 'result': outcomes[1]})
        assert initial == original
        results.append({'position': position, 'values': {a.name: a.values for a in items},
                        'frontier': signature(new), 't06_comparisons': consumer_results,
                        'input_unchanged': True})
        for t in traces:
            traces_record.append({'name': t.name, 'context': t.context, 'states': [t.state(i) for i in range(len(t.snapshots))],
                                  'actions': [t.action(i) for i in range(len(t.actions))]})
    return {'method': 'Fixed synthetic terminal states; original interpreter; no game initialization or policy calls.',
            'official_transitions': transitions, 'actual_t06_calls': 8, 'results': results}, traces_record


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--baseline', type=Path)
    ap.add_argument('--engine-dir', type=Path, default=Path('engine'))
    ap.add_argument('--kernel-file', type=Path, default=Path('../cloud-search-kernel/search_kernel.py'))
    ap.add_argument('--samples', type=int, default=9)
    ap.add_argument('--output', type=Path, default=Path('frontier-alignment-results.json'))
    args = ap.parse_args()
    if not 3 <= args.samples <= 51:
        raise ValueError('samples must be between 3 and 51')
    data = (args.baseline.read_bytes() if args.baseline is not None else
            subprocess.run(['git', 'show', f'{BASELINE_REF}:{BASELINE_PATH}'], check=True, capture_output=True).stdout)
    if blob(data) != BASELINE_BLOB:
        raise ValueError('Baseline must match the retained original source')
    before = module_from_bytes('frontier_alignment_baseline', data, args.baseline or BASELINE_PATH)
    kernel_data = args.kernel_file.read_bytes()
    if blob(kernel_data) != KERNEL_BLOB:
        raise ValueError('T06 source differs from the recorded consumer')
    kernel = module_from_bytes('frontier_alignment_kernel', kernel_data, args.kernel_file)
    before_ast, after_ast = ast.parse(data), ast.parse(Path(current.__file__).read_bytes())
    def remainder(tree):
        return [ast.dump(node, include_attributes=False) for node in tree.body
                if not (isinstance(node, ast.FunctionDef) and node.name == 'pareto_frontier')]
    assert remainder(before_ast) == remainder(after_ast)
    native, traces = native_join(before, engine_module(args.engine_dir), kernel)
    rows = timings(before, args.samples)
    raw = json.dumps(traces, separators=(',', ':')).encode()
    args.output.with_name('frontier-alignment-native-traces.json').write_bytes(raw)
    output = {'baseline_ref': BASELINE_REF, 'baseline_blob': BASELINE_BLOB,
              'runtime_sha256': hashlib.sha256(Path(current.__file__).read_bytes()).hexdigest(),
              't06_blob': KERNEL_BLOB, 'engine_ref': ENGINE_REF, 'engine_hashes': ENGINE_HASHES,
              'only_pareto_function_changed': True, 'timing_workloads': rows, 'native': native,
              'native_trace_sha256': hashlib.sha256(raw).hexdigest(), 'native_trace_bytes': len(raw),
              'full_games': 0, 'new_game_seeds': [],
              'scope': 'Frontier-call timings only; no whole-agent speed, deadline or game-strength claim.'}
    args.output.write_text(json.dumps(output, indent=2)+'\n')
    print(json.dumps({'native_transitions': native['official_transitions'], 't06_calls': 8,
                      'timed_matches': sum(x['timed_exact_matches'] for x in rows),
                      'timings': [{k: row[k] for k in ('size','scenarios','mode','baseline_median_seconds',
                               'candidate_median_seconds','median_reduction_fraction')} for row in rows]}, indent=2))


if __name__ == '__main__':
    main()
