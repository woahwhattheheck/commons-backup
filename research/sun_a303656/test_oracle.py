from __future__ import annotations

import random
import unittest
from math import isqrt

from .modular import (
    a303656_coverage_mask,
    greedy_congruence_cover,
    missing_residues,
    power_residue_mask,
)
from .oracle import factor_u64, find_witness, is_prime_u64, sum_two_squares


def brute_two_squares(n: int) -> tuple[int, int] | None:
    for a in range(isqrt(n) + 1):
        b = isqrt(n - a * a)
        if a * a + b * b == n:
            return a, b
    return None


class OracleTests(unittest.TestCase):
    def test_primality_matches_trial_division(self):
        for n in range(20_000):
            expected = n >= 2 and all(n % d for d in range(2, isqrt(n) + 1))
            self.assertEqual(is_prime_u64(n), expected, n)

    def test_factorization_roundtrip(self):
        values = (
            1,
            2,
            3,
            4,
            2**32 - 1,
            600851475143,
            1_000_000_007 * 1_000_000_009,
            2**61 - 1,
        )
        for n in values:
            rebuilt = 1
            for p, exponent in factor_u64(n):
                self.assertTrue(is_prime_u64(p))
                rebuilt *= p**exponent
            self.assertEqual(rebuilt, n)

    def test_sum_two_squares_matches_bruteforce(self):
        for n in range(5_000):
            exact = sum_two_squares(n)
            brute = brute_two_squares(n)
            self.assertEqual(exact is None, brute is None, n)
            if exact is not None:
                self.assertEqual(exact[0] ** 2 + exact[1] ** 2, n)

    def test_known_and_dense_small_witnesses(self):
        for n in range(2, 2_000):
            witness = find_witness(n)
            self.assertIsNotNone(witness, n)
            witness.verify(n)

    def test_seeded_large_witnesses(self):
        rng = random.Random(303656)
        for scale in (10**9, 10**12, 10**15, 10**18):
            for _ in range(25):
                n = scale + rng.randrange(scale)
                witness = find_witness(n)
                self.assertIsNotNone(witness, n)
                witness.verify(n)


class ModularTests(unittest.TestCase):
    def test_power_orbit_matches_direct_prefix(self):
        for modulus in range(2, 100):
            for base in (3, 5):
                mask = power_residue_mask(base, modulus)
                direct = {pow(base, e, modulus) for e in range(4 * modulus + 1)}
                encoded = {r for r in range(modulus) if (mask >> r) & 1}
                self.assertEqual(encoded, direct)

    def test_coverage_matches_bruteforce(self):
        for modulus in range(2, 80):
            exact = a303656_coverage_mask(modulus)
            brute = 0
            for a in range(modulus):
                for b in range(modulus):
                    for c in range(4 * modulus + 1):
                        for d in range(4 * modulus + 1):
                            residue = (
                                a * a + b * b + pow(3, c, modulus) + pow(5, d, modulus)
                            ) % modulus
                            brute |= 1 << residue
                            if brute == (1 << modulus) - 1:
                                break
                        if brute == (1 << modulus) - 1:
                            break
                    if brute == (1 << modulus) - 1:
                        break
                if brute == (1 << modulus) - 1:
                    break
            self.assertEqual(exact, brute, modulus)

    def test_no_small_local_obstruction(self):
        for modulus in range(2, 501):
            self.assertEqual(missing_residues(modulus), (), modulus)

    def test_greedy_cover_receipt_is_deterministic(self):
        receipt = greedy_congruence_cover(24, 18, 300)
        self.assertEqual(receipt["pairCount"], 432)
        self.assertEqual(receipt["eligiblePrimeCount"], 31)
        self.assertGreater(receipt["uncoveredPairCount"], 0)
        self.assertEqual(len(receipt["uncoveredCoordinatesSha256"]), 64)


if __name__ == "__main__":
    unittest.main()
