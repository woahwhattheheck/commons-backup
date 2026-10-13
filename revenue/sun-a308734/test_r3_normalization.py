from __future__ import annotations

import itertools
import unittest
from math import isqrt

import verify_r3_normalization as m


class R3Normalization(unittest.TestCase):
    def test_base_counts(self):
        self.assertEqual(m.r3_nonnegative(1), 3)
        self.assertEqual(m.r3_nonnegative(2), 3)
        self.assertEqual(m.r3_nonnegative(3), 1)
        self.assertEqual(m.r3_nonnegative(4), 3)

    def test_four_adic_identity_exact_range(self):
        for n in range(1, 257):
            with self.subTest(n=n):
                self.assertEqual(m.r3_nonnegative(4 * n), m.r3_nonnegative(n))

    def test_power_of_four_family_is_constant(self):
        for k in range(9):
            with self.subTest(k=k):
                self.assertEqual(m.r3_nonnegative(4**k), 3)

    def test_four_free_core(self):
        cases = {1:(1,0), 4:(1,1), 16:(1,2), 12:(3,1), 320:(5,3), 7:(7,0)}
        for n, expected in cases.items():
            with self.subTest(n=n):
                self.assertEqual(m.four_free_core(n), expected)

    def test_halving_lemma_exhaustive_small_cube(self):
        for triple in itertools.product(range(17), repeat=3):
            n = sum(v * v for v in triple)
            if n % 4 == 0:
                halved = m.assert_halving_lemma(*triple)
                self.assertEqual(sum(v*v for v in halved), n // 4)

    def test_doubling_inverse_on_small_representations(self):
        for n in range(1, 65):
            limit = isqrt(n)
            for x in range(limit + 1):
                for y in range(limit + 1):
                    rem = n - x*x - y*y
                    if rem < 0:
                        continue
                    z = isqrt(rem)
                    if z*z == rem:
                        self.assertEqual(m.assert_halving_lemma(2*x, 2*y, 2*z), (x,y,z))

    def test_invalid_inputs_fail(self):
        for value in (-1, 1.0, True, "1"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                m.r3_nonnegative(value)
        for value in (0, -4, 4.0, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                m.four_free_core(value)

    def test_parity_guard_rejects_nondivisible_sum(self):
        with self.assertRaises(ValueError):
            m.assert_halving_lemma(1, 0, 0)

    def test_helpers(self):
        self.assertEqual(m.verify_range(32), {"checked_n": 32, "max_n": 32})
        self.assertEqual(m.verify_powers(6), {"checked_powers": 7, "max_k": 6})


if __name__ == "__main__":
    unittest.main()
