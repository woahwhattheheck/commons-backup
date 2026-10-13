# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
import copy
from fractions import Fraction as F
import itertools
import json
import math
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest

from full_support import solve_full_table, verify_certificate

THREE = [[0, 0, 0], [5, -2, -2], [-2, 5, -2], [-2, -2, 5]]


class ExactSolverTests(unittest.TestCase):
    def test_three_support_has_strict_positive_gain(self):
        r = solve_full_table(THREE)
        self.assertEqual(r['weights'], ['0', '1/3', '1/3', '1/3'])
        self.assertEqual(r['value'], '1/3')
        self.assertEqual(r['dual_weights'], ['1/3'] * 3)
        self.assertTrue(verify_certificate(THREE, r)['optimal'])
        for i, j in itertools.combinations(range(1, 4), 2):
            pair = solve_full_table([THREE[0], THREE[i], THREE[j]])
            self.assertEqual(pair['value'], '0')

    def test_eight_alternative_support(self):
        d = [[0] * 8] + [[8 if i == j else -1 for j in range(8)] for i in range(8)]
        r = solve_full_table(d)
        self.assertEqual(r['weights'], ['0'] + ['1/8'] * 8)
        self.assertEqual(r['value'], '1/8')

    def test_published_strawberry_table(self):
        r = solve_full_table([[0, 0], [1, -1], [-1, 2]])
        self.assertEqual(r['weights'], ['0', '3/5', '2/5'])
        self.assertEqual(r['value'], '1/5')

    def test_published_added_negative_stream(self):
        r = solve_full_table([[0, 0, 0], [1, -1, -1], [-1, 2, -1]])
        self.assertEqual(r['weights'], ['1', '0', '0'])
        self.assertEqual(r['value'], '0')

    def test_constant_pure_and_baseline(self):
        for d, value in [([[0]], '0'), ([[0], [3]], '3'), ([[0], [-1]], '0'),
                         ([[0, 0], [4, 4]], '4'), ([[0, 0], [0, 0]], '0')]:
            with self.subTest(d=d):
                r = solve_full_table(d)
                self.assertEqual(r['value'], value)
                self.assertTrue(verify_certificate(d, r)['valid'])

    def test_zero_tie_preserves_baseline(self):
        r = solve_full_table([[0, 0], [2, -2], [-2, 2]])
        self.assertEqual(r['weights'], ['1', '0', '0'])
        self.assertEqual(r['value'], '0')

    def test_fractions_and_decimal_floats(self):
        d = [[0, 0], [F(1, 10), '-1/10'], [-0.1, 0.2]]
        r = solve_full_table(d)
        self.assertEqual(r['value'], '1/50')
        self.assertEqual(r['weights'], ['0', '3/5', '2/5'])

    def test_duplicate_rows_and_columns(self):
        d = [r + r for r in THREE] + [THREE[1] * 2]
        r = solve_full_table(d)
        self.assertEqual(r['value'], '1/3')
        self.assertTrue(verify_certificate(d, r)['optimal'])

    def test_row_and_column_permutations(self):
        for p in itertools.permutations(range(3)):
            d = [[row[j] for j in p] for row in [THREE[0], THREE[3], THREE[1], THREE[2]]]
            self.assertEqual(solve_full_table(d)['value'], '1/3')

    def test_budget_preserves_baseline_and_exact_bounds(self):
        for pivots in [0, 1, 2]:
            r = solve_full_table(THREE, max_pivots=pivots)
            self.assertEqual(r['status'], 'pivot_limit')
            self.assertFalse(r['exact'])
            self.assertEqual(r['weights'], ['1', '0', '0', '0'])
            self.assertGreaterEqual(F(r['upper_bound']), F(1, 3))
            self.assertTrue(verify_certificate(THREE, r)['valid'])

    def test_certificate_detects_modified_table(self):
        r = solve_full_table(THREE)
        d = copy.deepcopy(THREE); d[1][0] = 6
        self.assertFalse(verify_certificate(d, r)['valid'])

    def test_certificate_detects_corruption(self):
        r = solve_full_table(THREE)
        for key, value in [('weights', ['0', '1/2', '1/2', '0']),
                           ('dual_weights', ['-1', '1', '1']), ('value', '9'),
                           ('gap', '9'), ('upper_bound', '1'),
                           ('column_expectations', ['1', '1', '1']),
                           ('row_expectations_under_dual', ['1'] * 4),
                           ('exact', False), ('weights', ['1']), ('status', 'unknown')]:
            with self.subTest(key=key):
                changed = copy.deepcopy(r); changed[key] = value
                self.assertFalse(verify_certificate(THREE, changed)['valid'])

    def test_invalid_tables_and_limits(self):
        bad = [[], [[]], [[1]], [[0, 0], [1]], [[0]] * 10, [[0] * 33],
               [[0], [float('nan')]], [[0], [float('inf')]], [[0], [True]],
               [[0], ['not a rational']], [[0], [2**600]]]
        for d in bad:
            with self.subTest(d=str(d)[:90]), self.assertRaises(ValueError):
                solve_full_table(d)
        for kwargs in [{'max_pivots': -1}, {'max_pivots': True}, {'max_bits': 10},
                       {'max_bits': 6000}, {'max_pivots': 99999}]:
            with self.assertRaises(ValueError):
                solve_full_table(THREE, **kwargs)

    def test_no_input_mutation_or_cached_result_alias(self):
        d = copy.deepcopy(THREE); before = copy.deepcopy(d)
        a = solve_full_table(d); a['weights'][1] = '99'
        self.assertEqual(d, before)
        self.assertEqual(solve_full_table(d)['weights'][1], '1/3')

    def test_deterministic_repeated_results(self):
        self.assertEqual(solve_full_table(THREE), solve_full_table(THREE))

    def test_full_width_and_degenerate_random_certificates(self):
        rng = random.Random(64107)  # Offline matrix generation, not game seeds.
        for _ in range(80):
            n, m = rng.randint(2, 9), rng.randint(1, 32)
            d = [[0] * m] + [[rng.randint(-5, 9) for _ in range(m)] for _ in range(n - 1)]
            r = solve_full_table(d)
            self.assertEqual(r['status'], 'optimal')
            self.assertTrue(verify_certificate(d, r)['optimal'])

    def test_arithmetic_budget_before_and_after_a_pivot(self):
        for d, pivots in [([[0,0], ['1/251','-1/257'], ['-1/263','2/269']], 0),
                          ([[0,0,0], [317,-211,-223], [-227,331,-229], [-233,-239,337]], 1)]:
            result = solve_full_table(d, max_bits=16)
            self.assertEqual(result['status'], 'bit_limit')
            self.assertEqual(result['pivots'], pivots)
            self.assertEqual(result['weights'], ['1'] + ['0'] * (len(d)-1))
            self.assertFalse(result['exact'])
            self.assertTrue(verify_certificate(d, result)['valid'])
            full = solve_full_table(d)
            self.assertGreaterEqual(F(result['upper_bound']), F(full['value']))

    def test_canonical_equivalent_rational_inputs(self):
        a = solve_full_table([[0,0], [1,-1], [-1,2]])
        b = solve_full_table([['0.0',0.0], [F(2,2),'-1'], [-1.0,'2/1']])
        self.assertEqual(a, b)

    def test_positive_scale_preserves_value_and_strategy(self):
        scale = F(13,17)
        result = solve_full_table([[x*scale for x in row] for row in THREE])
        self.assertEqual(F(result['value']), scale/3)
        self.assertEqual(result['weights'], ['0','1/3','1/3','1/3'])

    def test_budget_completion_and_bound_proof_are_distinct(self):
        result = solve_full_table([[0,0],[-1,-1]], max_pivots=0)
        self.assertEqual(result['status'], 'pivot_limit')
        self.assertFalse(result['exact'])
        self.assertEqual(result['weights'], ['1','0'])
        self.assertTrue(verify_certificate([[0,0],[-1,-1]], result)['optimal'])

    def test_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'input.json'; p.write_text(json.dumps({'deltas': THREE}))
            out = Path(tmp) / 'result.json'
            subprocess.run([sys.executable, str(Path(__file__).with_name('full_support.py')),
                            str(p), '--output', str(out)], check=True, capture_output=True)
            self.assertEqual(json.loads(out.read_text())['value'], '1/3')


if __name__ == '__main__':
    unittest.main()
