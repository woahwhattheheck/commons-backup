"""Tests the new quantized-pair/merge composition, not old archive or solver suites."""
from fractions import Fraction as F
from itertools import combinations_with_replacement, product
import unittest

from certify_b12_prefix import (common_prefix, merge_disjoint_bounds,
    minimum_quantized_pair, quantized_pair, sorted_union, truncate_micro)


def block(index, pair):
    return {'coordinates': [[0, index, index + 1], [0, index, index + 2]],
            'minimum_quantized_pair': list(pair)}


class PrefixBoundTests(unittest.TestCase):
    def test_minimize_after_quantization_not_before(self):
        choices = [(F('1.0000001'), F('0.9')), (F('1.0000002'), F('0.1'))]
        exact_best = min(tuple(sorted(p, reverse=True)) for p in choices)
        self.assertEqual(quantized_pair(exact_best), (1000000, 900000))
        self.assertEqual(minimum_quantized_pair(choices), (1000000, 100000))
        self.assertLess(minimum_quantized_pair(choices), quantized_pair(exact_best))

    def test_floor_is_exact_and_not_nearest_rounding(self):
        self.assertEqual(truncate_micro(F('0.1234569')), 123456)
        self.assertEqual(truncate_micro(F('0.0000009')), 0)
        self.assertEqual(truncate_micro(F('1.000000')), 1000000)
        self.assertEqual(quantized_pair((F('0.1'), F('0.8'))), (800000, 100000))

    def test_lex_order_survives_common_multiset_merge_exhaustively(self):
        pairs = [tuple(sorted(p, reverse=True)) for p in combinations_with_replacement(range(5), 2)]
        compared = 0
        for a, b, c in product(pairs, repeat=3):
            if a >= b:
                self.assertGreaterEqual(sorted_union(a, c), sorted_union(b, c))
                compared += 1
        self.assertEqual(compared, 1800)

    def test_independent_local_minima_match_full_product_minimum(self):
        groups = [((9, 3), (8, 7), (10, 0)), ((6, 4), (6, 2), (7, 1)), ((4, 4), (5, 0), (4, 2))]
        merged = merge_disjoint_bounds([block(10 * i, min(g)) for i, g in enumerate(groups)], 10)
        exhaustive = min(sorted_union(*choices, (0, 0, 0, 0)) for choices in product(*groups))
        self.assertEqual(merged, exhaustive)
        self.assertEqual(merged, (8, 7, 6, 4, 2, 2, 0, 0, 0, 0))

    def test_prefix_bound_is_not_componentwise_invariance(self):
        best = (600000, 580000)
        worse = (650000, 400000)
        self.assertGreater(worse, best)
        self.assertLess(worse[1], best[1])
        self.assertGreater(sorted_union(worse, (700000,)), sorted_union(best, (700000,)))

    def test_overlapping_or_malformed_blocks_are_rejected(self):
        a = block(10, (3, 2))
        cases = [([a, a], 4), ([a], 1),
                 ([{'coordinates': [[0, 1, 2], [0, 1, 2]], 'minimum_quantized_pair': [3, 2]}], 2),
                 ([block(10, (2, 3))], 2), ([block(10, (3, -1))], 2)]
        for blocks, size in cases:
            with self.subTest(blocks=blocks, size=size), self.assertRaises(ValueError):
                merge_disjoint_bounds(blocks, size)

    def test_inexact_or_invalid_load_inputs_are_rejected(self):
        for value in (F(-1), 0.1, 1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                truncate_micro(value)
        with self.assertRaises(ValueError):
            quantized_pair((F(1),))
        with self.assertRaises(ValueError):
            minimum_quantized_pair([])

    def test_prefix_boundary_and_dimensions(self):
        self.assertEqual(common_prefix((9, 8, 7), (9, 8, 6)), 2)
        self.assertEqual(common_prefix((9, 8), (9, 8)), 2)
        self.assertEqual(common_prefix((), ()), 0)
        self.assertEqual(common_prefix((9,), (8,)), 0)
        with self.assertRaises(ValueError):
            common_prefix((1,), ())


if __name__ == '__main__':
    unittest.main(verbosity=2)
