# SPDX-License-Identifier: Apache-2.0
"""Execute exact-source MarketPath equivalence and official-market checks.

Requires a complete existing TITAN runtime directory, including the pinned
engine fixture. No dependency or game function is replaced. A fail-on-use
seed-resolution import shim is only needed when kaggle_environments is absent;
these tests call _process_market on explicit initialized state, not game setup.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import itertools
import json
import random
import statistics
import subprocess
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path

import marketpath_receipt_prefix as patch

PINS = {
    'scheduler.py': 'a483b24dd72b580d7d8811636b54d2d44f391575',
    'selected_sell_core.py': 'f23d3a8b5ee5e82029026e7f8f44eb36c143a5a3',
    'mechanics.py': '044a4f9c0a4a44dde10ada57563238bcaf82075d',
    'reference/decision/decision.py': '2931aa55831204fbb473ab85a6f5b81ec947fcf7',
    'reference/next-panel/vendor/arlene.py': 'bdb9cf58148a3c7961c085f4902759537decabf6',
    'checks/reference/engine/kaggriculture.py': '3c202c7ee921da239356789e266b694635103fc4',
}
ROOT = None
COUNTS = {}
MODULES = {}


def blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def checked(path, expected):
    data = path.read_bytes()
    actual = blob(data)
    if actual != expected:
        raise ValueError(f'{path}: expected {expected}, got {actual}')
    return data.decode('utf-8')


def load_source(name, path, source):
    module = types.ModuleType(name)
    module.__file__ = str(path)
    sys.modules[name] = module
    exec(compile(source, str(path), 'exec'), module.__dict__)
    return module


def bootstrap(root):
    for path, expected in PINS.items():
        checked(root / path, expected)
    sys.path.insert(0, str(root))
    for filename in ('scheduler.py', 'selected_sell_core.py'):
        source = (root / filename).read_text()
        MODULES[filename] = tuple(load_source('meadow_' + label + '_' + filename[:-3],
                                              root / filename, code)
                                 for label, code in (('old', source), ('new', patch.transform(source))))
    try:
        import kaggle_environments.utils  # noqa: F401
    except ImportError:
        package = types.ModuleType('kaggle_environments')
        utils = types.ModuleType('kaggle_environments.utils')
        def forbidden_seed_resolution(*args, **kwargs):
            raise RuntimeError('initialization is outside this explicit-state market gate')
        utils.resolve_episode_seed = forbidden_seed_resolution
        package.utils = utils
        sys.modules['kaggle_environments'] = package
        sys.modules['kaggle_environments.utils'] = utils
    path = root / 'checks/reference/engine/kaggriculture.py'
    MODULES['engine'] = load_source('meadow_official_engine', path, path.read_text())


def model(module, item='MILK', inventory=10000, params=None):
    return module.MarketPath(item, inventory, params, ['SMOOTHIE_SHOP'], {}, 23, 31)


def outcome(function, *args):
    try:
        return ('value', function(*args))
    except Exception as error:
        return ('exception', type(error).__name__, str(error))


class Struct(dict):
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__


def official_market(item, inventory, own, rival, alignment, seat):
    engine = MODULES['engine']
    farms = [engine._new_farm(10, 0), engine._new_farm(10, 0)]
    market = engine._new_market()
    market['inventory'][item] = inventory
    state = []
    quantities = [0, 0]
    quantities[seat], quantities[1-seat] = own, rival
    for player in range(2):
        private = engine._new_private()
        private['shed'][item] = quantities[player]
        order = ['SELL', item, quantities[player]]
        delayed = (alignment == 'after' and player != seat or
                   alignment == 'before' and player == seat)
        queue = ([[]] if delayed else []) + [order]
        state.append(Struct(observation=Struct(player=player, step=23,
                            farms=farms, market=market, private=private),
                            action={'farmer': ['PASS'], 'hands': [], 'market': queue}))
    engine._process_market(state, Struct(configuration={}))
    return (int(farms[seat]['money']), int(farms[1-seat]['money']),
            market['inventory'][item], [s.observation.private['shed'][item] for s in state])


class SourceContract(unittest.TestCase):
    def test_exact_methods_and_idempotence(self):
        for filename in ('scheduler.py', 'selected_sell_core.py'):
            source = (ROOT / filename).read_text()
            revised = patch.transform(source)
            self.assertEqual(patch.transform(revised), revised)
            old_nodes, new_nodes = patch.methods(source), patch.methods(revised)
            for name in old_nodes:
                if name not in ('_single', '_joint'):
                    self.assertEqual(old_nodes[name][1], new_nodes[name][1])
            # Restore precisely the edited spans; all other text is identical.
            lines = revised.splitlines(keepends=True)
            changes = [(new_nodes[n][0], old_nodes[n][1]) for n in ('_single', '_joint')]
            node = new_nodes['_receipt_series'][0]
            # Include the one blank separator inserted with the helper.
            changes.append((node, ''))
            for node, replacement in sorted(changes, key=lambda pair: pair[0].lineno, reverse=True):
                stop = node.end_lineno + (1 if node.name == '_receipt_series' else 0)
                lines[node.lineno-1:stop] = [replacement]
            self.assertEqual(''.join(lines), source)

    def test_drift_duplicates_and_partial_postimages_fail_closed(self):
        source = (ROOT / 'scheduler.py').read_text()
        variants = [source.replace('return int(cash),inv', 'return int(cash)+1,inv'),
                    source.replace("if alignment=='after':", "if alignment=='later':"),
                    source + '\nclass MarketPath:\n    pass\n',
                    patch.transform(source).replace('len(cache) >= 64', 'len(cache) >= 65')]
        for variant in variants:
            with self.assertRaises(ValueError):
                patch.transform(variant)

    def test_unrelated_peer_method_is_preserved(self):
        source = (ROOT / 'scheduler.py').read_text()
        marker = '    def peer_prefix_repair(self):\n        return "retained"\n\n'
        source = source.replace('    def score(', marker + '    def score(', 1)
        self.assertIn(marker, patch.transform(source))

    def test_cli_refuses_overwrite_and_in_place(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'source.py'
            target = Path(temp) / 'target.py'
            source.write_bytes((ROOT / 'selected_sell_core.py').read_bytes())
            command = [sys.executable, str(Path(patch.__file__).resolve()), str(source)]
            first = subprocess.run(command + [str(target)], capture_output=True)
            self.assertEqual(first.returncode, 0, first.stderr.decode())
            before = target.read_bytes()
            self.assertNotEqual(subprocess.run(command + [str(target)], capture_output=True).returncode, 0)
            self.assertEqual(target.read_bytes(), before)
            self.assertNotEqual(subprocess.run(command + [str(source)], capture_output=True).returncode, 0)
            self.assertEqual(source.read_bytes(), (ROOT / 'selected_sell_core.py').read_bytes())


class NumericalContract(unittest.TestCase):
    def test_single_all_quantities_all_products(self):
        count = 0
        for old, new in (MODULES['scheduler.py'], MODULES['selected_sell_core.py']):
            for item, inv in itertools.product(old.m.PRODUCTS, (-20, 9700, 9999, 10000, 10030, 10075, 10076, 10200, 11000)):
                a, b = model(old, item, inv), model(new, item, inv)
                for quantity in range(101):
                    self.assertEqual(a.single(inv, quantity), b.single(inv, quantity), (item, inv, quantity))
                    count += 1
        COUNTS['single_equalities'] = count

    def test_joint_order_asymmetry_and_floor_boundaries(self):
        count = 0
        quantities = (0, 1, 2, 7, 19, 50, 99, 100)
        for old, new in (MODULES['scheduler.py'], MODULES['selected_sell_core.py']):
            for item, inv in itertools.product(old.m.PRODUCTS, (9999, 10000, 10075, 10076, 11000)):
                a, b = model(old, item, inv), model(new, item, inv)
                for own, rival, alignment in itertools.product(quantities, quantities, ('paired', 'before', 'after')):
                    self.assertEqual(a.joint(inv, own, rival, alignment), b.joint(inv, own, rival, alignment),
                                     (item, inv, own, rival, alignment))
                    count += 1
        COUNTS['joint_equalities'] = count

    def test_float_single_vs_integer_joint_discriminator(self):
        old, new = MODULES['selected_sell_core.py']
        params = old.m._resolve_market_params({'MILK': {'base': 2**53+2, 'above_target': 0, 'below_target': 0}})
        a, b = model(old, params=params), model(new, params=params)
        self.assertNotEqual(a.single(10000, 13)[0], a.joint(10000, 13, 0, 'paired')[0])
        for quantity in range(101):
            self.assertEqual(a.single(10000, quantity), b.single(10000, quantity))
            for alignment in ('paired', 'before', 'after'):
                self.assertEqual(a.joint(10000, quantity, 9, alignment), b.joint(10000, quantity, 9, alignment))
        COUNTS['large_price_discriminator'] = {'single_cash': a.single(10000, 13)[0],
            'paired_cash': a.joint(10000, 13, 0, 'paired')[0], 'preserved': True}

    def test_custom_market_curves_and_bounds(self):
        old, new = MODULES['selected_sell_core.py']
        count = 0
        for shape in ('linear', 'sq', 'sqrt', 'log', 'log10', 'hinge'):
            params = old.m._resolve_market_params({'MILK': {'above_func': shape,
                'below_func': shape, 'base': 173, 'T': 89, 'above_target': .87, 'below_target': .63}})
            a, b = model(old, params=params), model(new, params=params)
            for inv, quantity in itertools.product((-500, 9880, 9999, 10000, 10076, 10150), (0, 1, 7, 99, 100)):
                self.assertEqual(a.single(inv, quantity), b.single(inv, quantity))
                for alignment in ('paired', 'before', 'after'):
                    self.assertEqual(a.joint(inv, quantity, 31, alignment), b.joint(inv, quantity, 31, alignment))
                    count += 1
        COUNTS['custom_curve_equalities'] = count
        # Unusual API inputs retain the original value or exact exception.
        a, b = model(old), model(new)
        for inv, quantity in itertools.product((10000.0, 10000.5, True, 2**53+1, -(2**53+1), 10000),
                                              (-1, 0, 1, 100, 101, 200, True, 2.0, 2.5)):
            self.assertEqual(outcome(a.single, inv, quantity), outcome(b.single, inv, quantity), (inv, quantity))
            self.assertEqual(outcome(a.joint, inv, quantity, 2, 'paired'),
                             outcome(b.joint, inv, quantity, 2, 'paired'), (inv, quantity))

    def test_bounded_instance_cache_and_revisit_after_eviction(self):
        old, new = MODULES['selected_sell_core.py']
        a, b = model(old), model(new)
        for inv in range(9700, 10050):
            self.assertEqual(a.single(inv, 100), b.single(inv, 100))
            self.assertEqual(a.joint(inv, 99, 53, 'paired'), b.joint(inv, 99, 53, 'paired'))
            self.assertLessEqual(len(b._receipt_prefixes), 64)
            self.assertTrue(all(len(rows) <= 101 for rows in b._receipt_prefixes.values()))
        # Clear the external lru cache so a revisit really traverses this cache.
        a.single.cache_clear(); b.single.cache_clear()
        self.assertEqual(a.single(9700, 100), b.single(9700, 100))
        other = model(new)
        other.single(9700, 100)
        self.assertIsNot(other._receipt_prefixes, b._receipt_prefixes)
        COUNTS['max_series'] = 64
        COUNTS['max_entries_per_series'] = 101

    def test_price_quote_call_reduction_is_real(self):
        old, new = MODULES['selected_sell_core.py']
        calls = []
        for module in (old, new):
            instance = model(module)
            quote = instance.quote
            counter = [0]
            def counted(inv):
                counter[0] += 1
                return quote(inv)
            instance.quote = counted
            for quantity in range(101):
                instance.single(10000, quantity)
                instance.joint(10000, quantity, 30, 'paired')
            calls.append(counter[0])
        self.assertLess(calls[1], calls[0])
        COUNTS['quote_dispatches'] = {'before': calls[0], 'after': calls[1]}


class EngineAndOptimizer(unittest.TestCase):
    def test_actual_official_market_both_physical_seats(self):
        old, new = MODULES['selected_sell_core.py']
        count = 0
        for item, inv, own, rival, alignment, seat in itertools.product(
                old.m.PRODUCTS, (9999, 10000, 10075, 11000), (0, 1, 7, 100),
                (0, 2, 33), ('paired', 'before', 'after'), (0, 1)):
            actual = official_market(item, inv, own, rival, alignment, seat)
            expected = model(new, item, inv).joint(inv, own, rival, alignment)
            self.assertEqual(actual[:3], expected, (item, inv, own, rival, alignment, seat))
            self.assertEqual(actual[3], [0, 0])
            count += 1
        COUNTS['official_market_transitions'] = count

    def test_complete_optimizer_result_and_capacity_callback_order(self):
        count = 0
        for filename in ('scheduler.py', 'selected_sell_core.py'):
            old, new = MODULES[filename]
            for item, inv, quantity, mode in itertools.product(
                    old.m.PRODUCTS, (9990, 10030), (8, 25), ('feasible', 'forced', 'impossible')):
                args = dict(item=item, quantity=quantity, inventory=inv, params=None,
                            shops=['SMOOTHIE_SHOP', 'YARN_STORE', 'FARMERS_MARKET'],
                            config={}, now=241, dates=[241, 242, 245, 249],
                            reference=((241, quantity),), rival_quantity=quantity//2,
                            minimum_now=0)
                traces, results = [], []
                for module in (old, new):
                    calls = []
                    def capacity(plan):
                        calls.append(plan)
                        return mode == 'feasible' or mode == 'forced' and plan != args['reference']
                    results.append(module.optimize_lot(**args, capacity_ok=capacity))
                    traces.append(calls)
                self.assertEqual(results[0], results[1], (filename, item, inv, quantity, mode))
                self.assertEqual(traces[0], traces[1], (filename, item, inv, quantity, mode))
                count += 1
        COUNTS['complete_optimizer_equalities'] = count

    def test_scores_terminal_carry_and_mutable_absorption_context(self):
        count = 0
        for old, new in (MODULES['scheduler.py'], MODULES['selected_sell_core.py']):
            a, b = model(old), model(new)
            for terminal, plan, rival, alignment in itertools.product(
                    (False, True), (((23, 30),), ((23, 7), (28, 9)), ()),
                    (0, 9, ((24, 10), (29, 20))), ('paired', 'before', 'after')):
                self.assertEqual(a.score(plan, 30, rival, alignment, terminal),
                                 b.score(plan, 30, rival, alignment, terminal))
                count += 1
            for instance in (a, b):
                instance.shops.append('ICE_CREAM_SHOP')
                instance.config['townShopSellInterval'] = 3
            self.assertEqual(a.score(((25, 11),), 30, 12, 'paired'),
                             b.score(((25, 11),), 30, 12, 'paired'))
        COUNTS['score_equalities'] = count + 2


def benchmarks(repeats=5):
    old, new = MODULES['selected_sell_core.py']
    cases = [dict(item=item, quantity=quantity, inventory=inv, params=None,
                  shops=['SMOOTHIE_SHOP', 'YARN_STORE', 'FARMERS_MARKET']*2,
                  config={}, now=241, dates=[241,242,245,249],
                  reference=((241,quantity),), rival_quantity=quantity//2, minimum_now=0)
             for item, quantity, inv in itertools.product(('MILK','WOOL','TOMATO'), (30,100), (10000,10070))]
    # Predeclared deterministic order alternates the two implementations to
    # limit warmup/order bias. No assertion depends on a timing threshold.
    samples = [[], []]
    for repeat in range(repeats + 1):
        for which in ((0,1) if repeat % 2 == 0 else (1,0)):
            module = (old,new)[which]
            started = time.perf_counter()
            for args in cases:
                module.optimize_lot(**args)
            elapsed = time.perf_counter() - started
            if repeat:
                samples[which].append(elapsed)
    medians = [statistics.median(values) for values in samples]
    return {'scope': '12 fixed complete optimize_lot calls per sample; synthetic inputs, not games',
            'repeats': repeats, 'samples_seconds': {'before': samples[0], 'after': samples[1]},
            'median_seconds': {'before': medians[0], 'after': medians[1]},
            'ratio_before_over_after': medians[0] / medians[1], 'cases': cases}


def main():
    global ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--benchmark', action='store_true')
    args, unittest_args = parser.parse_known_args()
    ROOT = args.runtime.resolve()
    bootstrap(ROOT)
    program = unittest.main(argv=[sys.argv[0], *unittest_args], exit=False)
    report = {'pins': PINS, 'tests_run': program.result.testsRun,
              'failures': len(program.result.failures), 'errors': len(program.result.errors),
              'optimized_python': not __debug__, 'counts': COUNTS,
              'limits': ['explicit-state official market calls, not full games',
                         'no runtime/default/archive/Kaggle change',
                         'wall-clock deadline outcomes are not covered by numerical equality']}
    if program.result.wasSuccessful() and args.benchmark:
        report['benchmark'] = benchmarks()
    if args.report:
        with args.report.open('x') as handle:
            json.dump(report, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write('\n')
    raise SystemExit(0 if program.result.wasSuccessful() else 1)


if __name__ == '__main__':
    main()
