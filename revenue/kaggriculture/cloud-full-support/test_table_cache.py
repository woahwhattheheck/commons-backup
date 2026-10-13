# SPDX-License-Identifier: Apache-2.0
"""Cache contracts and exact-output consumer comparisons; no engine or games."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from fractions import Fraction as F
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import random
import sys
import unittest
from unittest.mock import patch

import full_support as core

THREE = [[0, 0, 0], [5, -2, -2], [-2, 5, -2], [-2, -2, 5]]
REFERENCE = None
WEIGHTED_DIR = Path(__file__).resolve().parent.parent / 'cloud-weighted-plan-selector'
T15_DIR = Path(__file__).resolve().parent.parent / 'cloud-market-game-theory'
EXECUTION = {'matrices': [], 'consumer_sequences': [], 'dependencies': {}}


def identity(path):
    data = Path(path).read_bytes()
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
            'git_blob': hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()}


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError('Cannot load the supplied source file')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def matrix_corpus():
    rng = random.Random(10713)  # Synthetic matrix generation, never game seeds.
    for n in range(1, 10):
        for m in range(1, 33):
            rows = [[0] * m] + [[rng.randint(-9, 13) for _ in range(m)] for _ in range(n-1)]
            if (n + m) % 5 == 0:
                rows = [[str(F(x, 7)) for x in row] for row in rows]
            yield rows


class CacheTests(unittest.TestCase):
    def setUp(self):
        core.clear_table_cache()

    def test_repeated_table_reuses_completed_certificate(self):
        with patch.object(core, 'verify_certificate', wraps=core.verify_certificate) as checked:
            first = core.solve_full_table(THREE)
            second = core.solve_full_table(THREE)
            self.assertEqual(checked.call_count, 1)
        self.assertEqual(first, second)
        self.assertIsNot(first, second)
        self.assertEqual(core.table_cache_info(), {'hits': 1, 'misses': 1, 'maxsize': 64, 'currsize': 1})

    def test_every_returned_collection_is_detached(self):
        pristine = core.solve_full_table(THREE)
        changed = core.solve_full_table(THREE)
        for key, value in changed.items():
            if isinstance(value, list):
                self.assertIsNot(value, pristine[key])
                value.append('changed')
        changed['value'] = '9000'
        changed['nested_by_caller'] = {'arbitrary': ['new']}
        self.assertEqual(core.solve_full_table(THREE), pristine)

    def test_input_mutation_is_a_new_table(self):
        data = deepcopy(THREE)
        prior = core.solve_full_table(data)
        data[1][0] = 6
        current = core.solve_full_table(data)
        self.assertNotEqual(prior['table_sha256'], current['table_sha256'])
        self.assertEqual(core.table_cache_info()['misses'], 2)
        self.assertEqual(core.solve_full_table(THREE), prior)

    def test_canonical_rationals_share_one_entry(self):
        a = [[0, 0], [1, -1], [-1, 2]]
        b = [['0.0', 0.0], [F(2, 2), '-1'], [-1.0, '2/1']]
        self.assertEqual(core.solve_full_table(a), core.solve_full_table(b))
        self.assertEqual(core.table_cache_info()['hits'], 1)

    def test_order_and_shape_are_part_of_identity(self):
        data = [[0, 0, 0], [1, 2, 3], [3, -1, 4]]
        variants = [data, [data[0], data[2], data[1]], [list(reversed(r)) for r in data], [[0], [1]]]
        answers = [core.solve_full_table(d) for d in variants]
        self.assertEqual(core.table_cache_info()['misses'], 4)
        self.assertEqual(len({a['table_sha256'] for a in answers}), 4)
        for d, answer in zip(variants, answers):
            self.assertTrue(core.verify_certificate(d, answer)['valid'])

    def test_pivot_and_bit_budgets_never_alias(self):
        complete = core.solve_full_table(THREE)
        limited = core.solve_full_table(THREE, max_pivots=0)
        bit_limited_table = [[0, 0], ['1/251', '-1/257'], ['-1/263', '2/269']]
        exact = core.solve_full_table(bit_limited_table)
        small = core.solve_full_table(bit_limited_table, max_bits=16)
        self.assertEqual(complete['status'], 'optimal')
        self.assertEqual(limited['status'], 'pivot_limit')
        self.assertEqual(limited['weights'], ['1', '0', '0', '0'])
        self.assertEqual(exact['status'], 'optimal')
        self.assertEqual(small['status'], 'bit_limit')
        self.assertEqual(core.solve_full_table(THREE, max_pivots=0), limited)
        self.assertEqual(core.solve_full_table(bit_limited_table, max_bits=16), small)
        self.assertEqual(core.table_cache_info()['currsize'], 4)

    def test_equal_boolean_budget_is_still_invalid_after_warmup(self):
        core.solve_full_table(THREE, max_pivots=1)
        with self.assertRaises(ValueError):
            core.solve_full_table(THREE, max_pivots=True)
        core.solve_full_table(THREE, max_pivots=0)
        with self.assertRaises(ValueError):
            core.solve_full_table(THREE, max_pivots=False)
        self.assertEqual(core.table_cache_info()['hits'], 0)

    def test_invalid_inputs_do_not_reuse_or_poison_results(self):
        good = core.solve_full_table([[0], [1]])
        before = core.table_cache_info()
        for bad in ([[0], [True]], [[1], [1]], [[0], [float('nan')]], [[0], [float('inf')]], [[]], []):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                core.solve_full_table(bad)
        self.assertEqual(core.table_cache_info(), before)
        for _ in range(2):
            with self.assertRaises(ValueError):
                core.solve_full_table([[0], [2**600]])
        self.assertEqual(core.table_cache_info()['currsize'], 1)
        self.assertEqual(core.solve_full_table([[0], [1]]), good)

    def test_bounded_lru_eviction_and_explicit_release(self):
        for value in range(65):
            core.solve_full_table([[0], [value]])
        self.assertEqual(core.table_cache_info()['currsize'], 64)
        misses = core.table_cache_info()['misses']
        core.solve_full_table([[0], [64]])
        self.assertEqual(core.table_cache_info()['hits'], 1)
        core.solve_full_table([[0], [0]])
        self.assertEqual(core.table_cache_info()['misses'], misses + 1)
        core.clear_table_cache()
        self.assertEqual(core.table_cache_info(), {'hits': 0, 'misses': 0, 'maxsize': 64, 'currsize': 0})

    def test_cache_information_is_detached(self):
        core.solve_full_table(THREE)
        data = core.table_cache_info(); data['currsize'] = 0
        self.assertEqual(core.table_cache_info()['currsize'], 1)

    def test_parallel_callers_receive_independent_results(self):
        expected = core.solve_full_table(THREE)
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(lambda _: core.solve_full_table(THREE), range(32)))
        self.assertEqual(len({id(x) for x in results}), 32)
        self.assertTrue(all(x == expected for x in results))
        results[0]['weights'][1] = '10'
        self.assertEqual(core.solve_full_table(THREE), expected)

    def test_full_results_match_exact_original_for_every_shape(self):
        if REFERENCE is None:
            self.skipTest('Pass --reference-file for original-source parity')
        for index, data in enumerate(matrix_corpus()):
            prior = REFERENCE.solve_full_table(data)
            fresh = core.solve_full_table(data)
            hit = core.solve_full_table(data)
            self.assertEqual(prior, fresh)
            self.assertEqual(prior, hit)
            self.assertTrue(core.verify_certificate(data, hit)['valid'])
            EXECUTION['matrices'].append({'index': index, 'rows': len(data), 'columns': len(data[0]),
                                          'table_sha256': hit['table_sha256'], 'value': hit['value'],
                                          'complete_result_matches': 2})
        self.assertEqual(len(EXECUTION['matrices']), 288)


class ActualConsumerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        needed = [T15_DIR / 'selector.py', T15_DIR / 'solver.py', WEIGHTED_DIR / 'weighted_selector.py']
        if REFERENCE is None or not all(p.is_file() for p in needed):
            raise unittest.SkipTest('Supply original core and actual T15/PRISM sources for joined tests')
        previous = sys.modules.get('solver')
        sys.modules['solver'] = load(needed[1], '_cache_old_t15_solver')
        try:
            cls.selector = load(needed[0], '_cache_t15_selector').WholePlanSelector
        finally:
            if previous is None:
                sys.modules.pop('solver', None)
            else:
                sys.modules['solver'] = previous
        cls.factory = staticmethod(load(needed[2], '_cache_weighted_selector').make_selector)
        for path in needed:
            EXECUTION['dependencies'][path.name] = identity(path)

    def setUp(self):
        core.clear_table_cache()

    def test_actual_selector_actions_and_state_match_across_actors(self):
        plans = [{'id': 'base', 'sales': [[1, 4]]}] + [
            {'id': 'p' + str(i), 'sales': [[1+i, 4]]} for i in range(1, 4)]
        base = {'farmer': ['PASS'], 'hands': [], 'market': [['SELL', 'EGG', 4], ['BUY_SEED', 'WHEAT', 1]]}
        window = {'key': 'same-economics', 'item': 'EGG', 'quantity': 4, 'now': 1, 'end': 4,
                  'slot': 0, 'plans': plans, 'deltas': THREE}
        for actor in range(12):
            old = self.factory(self.selector, REFERENCE.solve_full_table, rng=random.Random(actor))
            new = self.factory(self.selector, core.solve_full_table, rng=random.Random(actor))
            actions = []
            for step in range(1, 5):
                obs = {'player': 0, 'step': step, 'farms': [{'money': 1000}]}
                kw = {'window': window if step == 1 else None, 'post_unit_shed': {'EGG': 4},
                      'feasible': lambda plan: True}
                a = old.transform(obs, {}, base, **kw)
                b = new.transform(obs, {}, base, **kw)
                self.assertEqual(a, b)
                self.assertEqual(old.active, new.active)
                self.assertEqual(old.last_decision, new.last_decision)
                actions.append(b)
            self.assertEqual(new.draws, 1)
            self.assertEqual(new.provider_calls, 1)
            EXECUTION['consumer_sequences'].append({'actor_rng_fixture': actor, 'actions': actions,
                                                    'draws': new.draws, 'provider_calls': new.provider_calls})
        self.assertEqual(core.table_cache_info()['misses'], 1)
        self.assertEqual(core.table_cache_info()['hits'], 11)

    def test_cached_math_does_not_cache_physical_feasibility(self):
        core.solve_full_table(THREE)
        selected = self.factory(self.selector, core.solve_full_table, rng=random.Random(7))
        visited = []
        plans = [{'id': str(i)} for i in range(4)]
        def feasible(plan):
            visited.append(plan['id'])
            return plan['id'] != '2'
        self.assertIsNone(selected.choose('physical-change', plans, THREE, feasible=feasible))
        self.assertEqual(visited, ['0', '1', '2', '3'])
        self.assertEqual(selected.draws, 0)
        self.assertEqual(selected.provider_calls, 0)

    def test_actual_selector_budget_and_zero_keep_no_draw(self):
        for data, provider in [
            (THREE, lambda rows: core.solve_full_table(rows, max_pivots=0)),
            ([[0, 0], [-1, -1]], core.solve_full_table)]:
            for _ in range(2):
                selected = self.factory(self.selector, provider, rng=random.Random(3))
                self.assertIsNone(selected.choose('baseline', [{'id': str(i)} for i in range(len(data))],
                                                  data, feasible=lambda plan: True))
                self.assertEqual(selected.draws, 0)
                self.assertEqual(selected.provider_calls, 1)


def main():
    global REFERENCE, T15_DIR, WEIGHTED_DIR
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference-file', type=Path)
    parser.add_argument('--t15-dir', type=Path, default=T15_DIR)
    parser.add_argument('--weighted-dir', type=Path, default=WEIGHTED_DIR)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    T15_DIR, WEIGHTED_DIR = args.t15_dir, args.weighted_dir
    if args.reference_file:
        REFERENCE = load(args.reference_file, '_cache_original_core')
        EXECUTION['dependencies']['reference_full_support.py'] = identity(args.reference_file)
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]))
    report = {'schema': 'titan.full-support-cache.tests.v1', 'tests': result.testsRun,
              'failures': len(result.failures), 'errors': len(result.errors), 'skipped': len(result.skipped),
              'source': {name: identity(Path(__file__).with_name(name))
                         for name in ['full_support.py', 'test_table_cache.py']},
              'execution': EXECUTION, 'log': stream.getvalue(), 'games': 0, 'engine_transitions': 0}
    sys.stdout.write(stream.getvalue())
    if args.output:
        with args.output.open('x', encoding='utf-8') as handle:
            json.dump(report, handle, indent=2); handle.write('\n')
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
