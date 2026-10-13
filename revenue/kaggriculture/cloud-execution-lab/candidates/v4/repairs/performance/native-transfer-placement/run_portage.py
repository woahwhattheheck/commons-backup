# SPDX-License-Identifier: Apache-2.0
"""Run isolated negative controls and alternating local timing comparisons."""
from __future__ import annotations
import argparse
import copy
import gc
import importlib.util
import json
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time

from compose_portage import compose
from check_portage import Portage, load, source_module, with_mechanics


def controls(root, optimized):
    source = compose((root / 'mechanics.py').read_bytes()).decode()
    mutations = {
        'geometry_missing_edge': ('half - 1 <= point[0] <= half', 'half - 1 < point[0] <= half'),
        'geometry_extra_edge': ('half - 1 <= point[1] <= half', 'half - 1 <= point[1] <= half + 1'),
        'spawn_reversed_tie': ('min(occupants, key=occupants.get)', 'min(reversed(occupants), key=occupants.get)'),
        'reverse_actor_priority': ('for inv in private["inventories"]:', 'for inv in reversed(private["inventories"]):'),
        'capacity_extra_one': ('room = max(0, capacity - current)', 'room = max(0, capacity - current + 1)'),
        'shed_subclass_values': ('if type(shed) is dict', 'if isinstance(shed, dict)'),
        'retain_cargo': ('            del inv[item]\n', '            inv[item] = 0\n'),
    }
    results = {}
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        for name, (old, new) in mutations.items():
            if old not in source:
                raise ValueError('unapplied mutation: ' + name)
            raw = source.replace(old, new)
            compile(raw, name, 'exec')
            path, report = td / (name + '.py'), td / (name + '.json')
            path.write_text(raw)
            result = subprocess.run([sys.executable, *(['-O'] if optimized else []),
                str(Path(__file__).with_name('check_portage.py')), '--runtime-root', str(root),
                '--candidate', str(path), '--receipt', str(report)],
                capture_output=True, text=True, timeout=30)
            if not report.exists():
                raise RuntimeError('control infrastructure failure: ' + name + '\n' + result.stderr)
            data = json.loads(report.read_text())
            # Assertion rejection required, not import/setup/infrastructure errors.
            killed = result.returncode == 1 and data['tests'] == 12 and data['failures'] > 0 and data['errors'] == 0
            results[name] = {'killed': killed, 'failures': data['failures'], 'errors': data['errors']}
            if not killed:
                raise RuntimeError('control not behaviorally rejected: ' + name + '\n' + result.stderr)
    return results


def benchmark(root, repeat=7):
    import check_portage as gate
    gate.ROOT = root
    gate.CANDIDATE = None
    Portage.setUpClass()
    case = Portage()
    state, env = case.fixture(0, 20, 100)
    obs, action = state[0].observation, state[0].action
    scheduler = object.__new__(Portage.scheduler.SellScheduler)
    import types
    scheduler.controller = types.SimpleNamespace(R=[[copy.deepcopy(action) for _ in range(24)]], cur=0)
    cargo = {'shed': {p: 5 for p in Portage.base.PRODUCTS},
             'inventories': [{p: 7 for p in Portage.base.PRODUCTS} for _ in range(5)]}
    small_cargo = {'shed': {'MILK': 5}, 'inventories': [{'WOOL': 3}]}
    empty_cargo = {'shed': {}, 'inventories': [{}]}
    positions = [(4, 4), (5, 5), (4, 5), (0, 0), (5, 4), (6, 5)]
    farm = obs['farms'][0]
    def tasks(module):
        def geometry():
            return tuple(module._is_shed_adjacent(p, 10) for p in positions)
        def spawn():
            return module._spawn_hand(farm, 10)
        def transfer(fixture=cargo):
            private = {'shed': dict(fixture['shed']), 'inventories': [dict(x) for x in fixture['inventories']]}
            module._drop_inventories_to_shed(private, 100)
            return private
        def native_post():
            return Portage.scheduler.post_units(obs, action, env.configuration)
        def native_receipt():
            f, p = Portage.scheduler.post_units(obs, action, env.configuration)
            feasible = scheduler.receipt_profile(obs, action, f, p, 23, 'MILK', env.configuration)
            return feasible(((20, 4), (23, 6)))
        return {'geometry': (geometry, 30000), 'spawn': (spawn, 30000),
                'transfer_dense': (transfer, 6000),
                'transfer_one': (lambda: transfer(small_cargo), 30000),
                'transfer_empty': (lambda: transfer(empty_cargo), 30000),
                'native_post_units': (native_post, 2000),
                'native_receipt_profile': (native_receipt, 1000)}
    modules = [Portage.base, Portage.fast]
    work = [tasks(module) for module in modules]
    results = {}
    for name in work[0]:
        samples = [[], []]
        for iteration in range(repeat):
            for idx in ((0, 1) if iteration % 2 == 0 else (1, 0)):
                fn, number = work[idx][name]
                with with_mechanics(Portage.scheduler, modules[idx]):
                    for _ in range(30):
                        fn()
                    gc.collect()
                    start = time.perf_counter_ns()
                    for _ in range(number):
                        fn()
                    samples[idx].append((time.perf_counter_ns() - start) / 1e6)
        old, new = map(statistics.median, samples)
        results[name] = {'iterations_per_sample': work[0][name][1],
                         'baseline_ms': samples[0], 'candidate_ms': samples[1],
                         'median_baseline_ms': old, 'median_candidate_ms': new,
                         'median_reduction_percent': 100 * (1 - new / old)}
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-root', type=Path, required=True)
    parser.add_argument('--mode', choices=['controls', 'benchmark'], required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    root = args.runtime_root.resolve()
    result = controls(root, bool(sys.flags.optimize)) if args.mode == 'controls' else benchmark(root)
    data = {'mode': args.mode, 'python': sys.version, 'optimized': sys.flags.optimize, 'results': result}
    args.receipt.write_text(json.dumps(data, indent=2) + '\n')
    print(json.dumps(data, indent=2))

if __name__ == '__main__':
    main()
