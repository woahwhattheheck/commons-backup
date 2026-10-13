"""Exact arithmetic/assumption tests; no solver or checker is launched."""
from decimal import Decimal
from fractions import Fraction as F
from itertools import permutations
import unittest

from certify_b12_peak import minimum_two_link_peak

V = (F('88.898232'), F('38.309735'), F('2.455752'))
C = (F(101), F(114))
BOUND = F(127207967, 202000000)


def exact(record):
    return F(record['numerator'], record['denominator'])


class PeakBoundTests(unittest.TestCase):
    def test_b12_exact_bound_and_unique_allocation(self):
        result = minimum_two_link_peak(V, C)
        self.assertEqual(result['case_count'], 27)
        self.assertEqual(len({tuple(x['twice_fraction_on_link0']) for x in result['all_cases']}), 27)
        self.assertEqual(exact(result['minimum_peak']), BOUND)
        self.assertEqual([x['twice_fraction_on_link0'] for x in result['minimizers']], [[1, 1, 0]])
        self.assertEqual(exact(result['minimizers'][0]['link1_first_departure_load']), F(132119471, 228000000))

    def test_swapping_exits_complements_the_minimizer(self):
        result = minimum_two_link_peak(V, C[::-1])
        self.assertEqual(exact(result['minimum_peak']), BOUND)
        self.assertEqual([x['twice_fraction_on_link0'] for x in result['minimizers']], [[1, 1, 2]])

    def test_permuting_demands_preserves_the_bound(self):
        for order in permutations(range(3)):
            with self.subTest(order=order):
                result = minimum_two_link_peak(tuple(V[i] for i in order), C)
                self.assertEqual(exact(result['minimum_peak']), BOUND)
                self.assertEqual(result['minimizers'][0]['twice_fraction_on_link0'], [[1, 1, 0][i] for i in order])

    def test_arbitrary_fractional_cut_is_strictly_weaker(self):
        continuous = sum(V, F()) / sum(C, F())
        self.assertEqual(continuous, F(129663719, 215000000))
        self.assertLess(continuous, BOUND)
        self.assertEqual((BOUND.numerator * 1000000) // BOUND.denominator, 629742)
        self.assertGreater(BOUND, F(Decimal('0.629742')))
        self.assertLess(BOUND, F(Decimal('0.6297425')))

    def test_single_symmetric_demand_has_exact_half_split(self):
        result = minimum_two_link_peak((F(2),), (F(1), F(1)))
        self.assertEqual(result['case_count'], 3)
        self.assertEqual(exact(result['minimum_peak']), F(1))
        self.assertEqual(result['minimizers'][0]['twice_fraction_on_link0'], [1])

    def test_every_case_conserves_first_departure_flow(self):
        result = minimum_two_link_peak(V, C)
        for row in result['all_cases']:
            with self.subTest(allocation=row['twice_fraction_on_link0']):
                left = exact(row['link0_first_departure_load'])
                right = exact(row['link1_first_departure_load'])
                self.assertEqual(left * C[0] + right * C[1], sum(V, F()))
                self.assertEqual(exact(row['peak']), max(left, right))
                # Independent integer numerator reconstruction, not a repeated optimization call.
                n = sum(int(v * 1000000) * a for v, a in zip(V, row['twice_fraction_on_link0']))
                self.assertEqual(left, F(n, 2000000 * 101))
                self.assertGreaterEqual(max(left + F(1, 1000), right), exact(row['peak']))

    def test_unsupported_volume_inputs_are_rejected(self):
        for volumes in ((), (F(0),), (F(-1),), (F(1),) * 9, (0.1,)):
            with self.subTest(volumes=volumes), self.assertRaises(ValueError):
                minimum_two_link_peak(volumes, C)

    def test_unsupported_capacity_inputs_are_rejected(self):
        for capacities in ((), (F(1),), (F(1),) * 3, (F(0), F(1)), (F(-1), F(1)), (101.0, 114.0)):
            with self.subTest(capacities=capacities), self.assertRaises(ValueError):
                minimum_two_link_peak(V, capacities)


if __name__ == '__main__':
    unittest.main(verbosity=2)
