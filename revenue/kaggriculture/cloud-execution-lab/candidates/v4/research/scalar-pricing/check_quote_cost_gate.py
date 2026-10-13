# SPDX-License-Identifier: Apache-2.0
"""Executed regressions for PRISM's OFFLINE experiment, including rejected arms."""
from __future__ import annotations
import argparse
import copy
from functools import lru_cache
import inspect
import json
from pathlib import Path
import random
import sys
import tempfile
import unittest

import quote_cost_gate as gate

ROOT = None
COUNTS = {'official_scalar_comparisons': 0, 'experimental_scalar_comparisons': 0,
          'complete_optimizer_comparisons': 0, 'behavioral_mutants_rejected': 0,
          'source_mutations_rejected': 0}


class QuoteCostGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m, cls.core, cls.native_pins = gate.load_native(ROOT)
        cls.engine, cls.engine_pins = gate.load_engine(ROOT)

    def compare(self, fn, expected, inventories):
        for inv in inventories:
            self.assertEqual(fn(inv), expected(inv), f'inventory={inv}')

    def test_01_pins_and_actual_call_path(self):
        self.assertEqual(len(self.native_pins), 3)
        self.assertEqual(len(self.engine_pins), 5)
        self.assertIs(self.core.m, self.m)
        self.assertEqual(self.core.MarketPath.__module__, 'prism_native_core')

    def test_02_default_price_matches_full_pinned_engine(self):
        rng = random.Random(19091143)
        xs = list(range(9800, 10250)) + [rng.randrange(-100000, 200000) for _ in range(300)]
        xs += [1713383321442, 1713383321443, 10058, 10059, 10061, 10062, 10075, 10076]
        for item in self.m.PRODUCTS:
            for inv in xs:
                self.assertEqual(self.m.market_price(item, inv), self.engine.market_price(item, inv))
                COUNTS['official_scalar_comparisons'] += 1

    def test_03_default_experimental_quotes(self):
        xs = list(range(9700, 10401)) + [-100000, -1, 0, 1713383321443]
        for item in self.m.PRODUCTS:
            for factory in (gate.amplitude_quote, gate.snapshot_quote):
                fn = factory(self.m, item, None)
                for inv in xs:
                    self.assertEqual(fn(inv), self.engine.market_price(item, inv))
                    COUNTS['experimental_scalar_comparisons'] += 1

    def test_04_all_shapes_and_custom_parameters(self):
        rng = random.Random(4043)
        for below in ('linear', 'sq', 'sqrt', 'log', 'log10', 'hinge', 'unknown'):
            for above in ('linear', 'sq', 'sqrt', 'log', 'log10', 'hinge', 'unknown'):
                patch = {'base': 137, 'I0': 200, 'T': 17.5, 'below_func': below,
                         'above_func': above, 'below_target': 0.37, 'above_target': 0.59}
                params = self.m._resolve_market_params({'WHEAT': patch})
                frozen = copy.deepcopy(params)
                fs = [f(self.m, 'WHEAT', params) for f in (gate.amplitude_quote, gate.snapshot_quote)]
                for inv in [199, 200, 201] + [rng.randrange(-300, 750) for _ in range(150)]:
                    want = self.engine.market_price('WHEAT', inv, params)
                    self.assertEqual(self.m.market_price('WHEAT', inv, params), want)
                    COUNTS['official_scalar_comparisons'] += 1
                    for fn in fs:
                        self.assertEqual(fn(inv), want)
                        COUNTS['experimental_scalar_comparisons'] += 1
                self.assertEqual(params, frozen)

    def test_05_bankers_rounding_and_negative_inventory(self):
        params = self.m._resolve_market_params({'WHEAT': {
            'base': 4, 'I0': 10, 'T': 1, 'below_func': 'linear', 'above_func': 'linear',
            'below_target': 0.125, 'above_target': 0.125}})
        expected = [6, 5, 4, 4, 4, 3, 2]
        for factory in (gate.amplitude_quote, gate.snapshot_quote):
            fn = factory(self.m, 'WHEAT', params)
            self.assertEqual([fn(i) for i in range(7, 14)], expected)
            self.compare(fn, lambda i: self.engine.market_price('WHEAT', i, params), range(-20, 21))

    def test_06_large_prices_preserve_operation_order(self):
        for base in (10**15 + 37, float(10**15 + 37), 123456789):
            p = self.m._resolve_market_params({'EGG': {'base': base}})
            for factory in (gate.amplitude_quote, gate.snapshot_quote):
                self.compare(factory(self.m, 'EGG', p),
                    lambda i: self.engine.market_price('EGG', i, p), range(9700, 10301, 3))

    def test_07_live_mutation_exposes_snapshot_non_equivalence(self):
        p = self.m._resolve_market_params({})
        native = lru_cache(2048)(lambda i: self.m.market_price('WHEAT', i, p))
        live = lru_cache(2048)(gate.amplitude_quote(self.m, 'WHEAT', p))
        frozen = lru_cache(2048)(gate.snapshot_quote(self.m, 'WHEAT', p))
        for fn in (native, live, frozen):
            self.assertEqual(fn(10000), 25)
        p['WHEAT']['base'] = 50
        self.assertEqual(native(10000), 25)  # Existing outer LRU semantics retained.
        self.assertEqual(live(10000), native(10000))
        self.assertEqual(live(10001), native(10001))
        self.assertNotEqual(frozen(10001), native(10001))  # Snapshot must NOT be installed.

    def test_08_unused_branch_validation_exposes_snapshot(self):
        p = self.m._resolve_market_params({})
        p['WHEAT']['above_target'] = None
        want = self.m.market_price('WHEAT', 9999, p)
        self.assertEqual(gate.amplitude_quote(self.m, 'WHEAT', p)(9999), want)
        with self.assertRaises(TypeError):
            gate.snapshot_quote(self.m, 'WHEAT', p)

    def test_09_price_override_falls_back_in_live_arm(self):
        fn = gate.amplitude_quote(self.m, 'WHEAT', None)
        fn(9999)
        old = self.m.market_price
        try:
            self.m.market_price = lambda item, inv, params=None: 777
            self.assertEqual(fn(9998), 777)
        finally:
            self.m.market_price = old

    def test_10_shape_override_falls_back_in_live_arm(self):
        fn = gate.amplitude_quote(self.m, 'WHEAT', None)
        fn(9999)
        old = self.m._shape
        try:
            self.m._shape = lambda f, x, T=None: max(1.0, float(x))
            self.assertEqual(fn(9998), self.m.market_price('WHEAT', 9998))
        finally:
            self.m._shape = old

    def test_11_empty_params_and_hinge_gain_changes(self):
        fn = gate.amplitude_quote(self.m, 'CARROT', {})
        self.assertEqual(fn(8000), self.m.market_price('CARROT', 8000))
        old = self.m.HINGE_GAIN
        try:
            self.m.HINGE_GAIN = 17.0
            self.assertEqual(fn(8000), self.m.market_price('CARROT', 8000))
        finally:
            self.m.HINGE_GAIN = old

    def test_12_selected_branch_errors_remain_errors(self):
        p = self.m._resolve_market_params({'WHEAT': {'T': 0}})
        fn = gate.amplitude_quote(self.m, 'WHEAT', p)
        with self.assertRaises(ZeroDivisionError):
            self.m.market_price('WHEAT', 9999, p)
        with self.assertRaises(ZeroDivisionError):
            fn(9999)
        with self.assertRaises(KeyError):
            gate.amplitude_quote(self.m, 'BAD_ITEM', None)(10000)

    def test_13_whole_optimizer_outputs_and_capacity_calls(self):
        rows = gate.fixtures(self.m)
        untouched = copy.deepcopy(rows)
        native, _ = gate.run_panel(self.core, rows)
        recorded, tables = gate.run_panel(self.core, rows, record=True)
        self.assertEqual(recorded, native)
        for mode in gate.MODES[1:]:
            got, _ = gate.run_panel(self.core, rows, mode, tables)
            self.assertEqual(got, native)
            COUNTS['complete_optimizer_comparisons'] += len(rows)
        self.assertEqual(rows, untouched)
        self.assertTrue(any(native['capacity_calls']))

    def test_14_oracle_is_closed_and_restores_class(self):
        original = self.core.MarketPath
        rows = gate.fixtures(self.m)[:1]
        with self.assertRaises(KeyError):
            gate.run_panel(self.core, rows, 'oracle_table', [{}])
        self.assertIs(self.core.MarketPath, original)
        with self.assertRaises(ValueError):
            gate.run_panel(self.core, [], 'oracle_table', [{}])
        self.assertIs(self.core.MarketPath, original)
        with self.assertRaises(ValueError):
            gate.run_panel(self.core, rows, 'not-an-arm')

    def test_15_interrupt_restores_local_module(self):
        original = self.core.MarketPath
        with self.assertRaises(KeyboardInterrupt):
            with gate.quote_arm(self.core, 'snapshot'):
                raise KeyboardInterrupt()
        self.assertIs(self.core.MarketPath, original)

    def test_16_mechanics_import_restoration(self):
        sentinel = object()
        before = sys.modules.get('mechanics', sentinel)
        marker = object()
        try:
            sys.modules['mechanics'] = marker
            gate.load_native(ROOT)
            self.assertIs(sys.modules['mechanics'], marker)
            sys.modules.pop('mechanics')
            gate.load_native(ROOT)
            self.assertNotIn('mechanics', sys.modules)
        finally:
            if before is sentinel:
                sys.modules.pop('mechanics', None)
            else:
                sys.modules['mechanics'] = before

    def test_17_all_native_source_drift_rejected(self):
        for changed in gate.NATIVE_PINS:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                for relative in gate.NATIVE_PINS:
                    path = root / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    data = (ROOT / relative).read_bytes()
                    path.write_bytes(data + (b'\n# drift\n' if relative == changed else b''))
                with self.assertRaisesRegex(ValueError, 'source mismatch'):
                    gate.load_native(root)
                COUNTS['source_mutations_rejected'] += 1

    def test_18_four_bad_math_mutants_are_observed(self):
        source = inspect.getsource(gate.snapshot_quote)
        mutations = [
            ('floor', 'return max(floor, int(round(price)))', 'return int(round(price))'),
            ('round', 'return max(floor, int(round(price)))', 'return max(floor, int(price))'),
            ('sign', 'price = base - upper *', 'price = base + upper *'),
            ('hinge_width', 'shape(below, width, width)', 'shape(below, width)'),
        ]
        for name, old, new in mutations:
            self.assertEqual(source.count(old), 1)
            scope = {'copy': copy}
            exec(compile(source.replace(old, new), f'<prism-mutant-{name}>', 'exec'), scope)
            factory = scope['snapshot_quote']
            found = False
            for item in self.m.PRODUCTS:
                fn = factory(self.m, item, None)
                for inv in range(8000, 11201, 3):
                    if fn(inv) != self.engine.market_price(item, inv):
                        found = True
                        break
                if found:
                    break
            self.assertTrue(found, f'undetected mathematical mutation: {name}')
            COUNTS['behavioral_mutants_rejected'] += 1

    def test_19_whole_optimizer_detects_bad_quote(self):
        rows = gate.fixtures(self.m)[:3]
        native, _ = gate.run_panel(self.core, rows)
        old = gate.amplitude_quote
        try:
            gate.amplitude_quote = lambda m, item, p: lambda inv: m.market_price(item, inv, p) + 1
            wrong, _ = gate.run_panel(self.core, rows, 'amplitude_cache')
            self.assertNotEqual(wrong, native)
        finally:
            gate.amplitude_quote = old

    def test_20_repetition_and_missing_source_guards(self):
        with self.assertRaises(ValueError):
            gate.experiment(ROOT, 2)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileNotFoundError):
                gate.load_native(Path(directory))


def main():
    global ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-root', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    ROOT = args.native_root.resolve()
    if args.output and args.output.exists():
        parser.error('output already exists')
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(QuoteCostGate)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    receipt = {'schema': 'prism-quote-checks/v1', 'optimized': bool(sys.flags.optimize),
               'tests_run': result.testsRun, 'failures': len(result.failures),
               'errors': len(result.errors), 'skipped': len(result.skipped),
               'successful': result.wasSuccessful(), 'counts': COUNTS}
    if args.output:
        with args.output.open('x', encoding='utf-8') as handle:
            json.dump(receipt, handle, indent=2, sort_keys=True)
            handle.write('\n')
    print(json.dumps(receipt, sort_keys=True))
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == '__main__':
    main()
