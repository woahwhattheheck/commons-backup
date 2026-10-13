#!/usr/bin/env python3
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import erdos366_search as s


def naive_k_full(n: int, k: int) -> bool:
    if n <= 0:
        return False
    if n == 1:
        return True
    x = n
    p = 2
    while p * p <= x:
        if x % p == 0:
            e = 0
            while x % p == 0:
                x //= p
                e += 1
            if e < k:
                return False
        p += 1
    return x == 1 or k <= 1


class Erdos366SearchTests(unittest.TestCase):
    def test_integer_nth_root(self):
        for n in range(1000):
            for k in (2, 3, 4, 5):
                r = s.integer_nth_root(n, k)
                self.assertLessEqual(r ** k, n)
                self.assertGreater((r + 1) ** k, n)

    def test_generator_matches_bruteforce(self):
        for k in (2, 3):
            bound = 20_000
            got = [n for n, _ in s.enumerate_k_full(bound, k)]
            want = [n for n in range(2, bound + 1) if naive_k_full(n, k)]
            self.assertEqual(got, want)

    def test_factorizations_multiply_back(self):
        for n, fs in s.enumerate_k_full(100_000, 3):
            self.assertEqual(s.factors_product(fs), n)
            self.assertTrue(all(e >= 3 for _, e in fs))

    def test_orientation_regressions(self):
        primes = s.primes_upto(1000)
        self.assertTrue(s.check_k_full(8, 3, primes).is_full)
        self.assertTrue(s.check_k_full(8, 2, primes).is_full)
        self.assertTrue(s.check_k_full(9, 2, primes).is_full)
        self.assertFalse(s.check_k_full(9, 3, primes).is_full)

        self.assertTrue(s.check_k_full(12167, 3, primes).is_full)
        self.assertTrue(s.check_k_full(12168, 2, primes).is_full)
        self.assertFalse(s.check_k_full(12168, 3, primes).is_full)

    def test_small_search_crosscheck(self):
        bound = 100_000
        result = s.search(bound)
        brute = []
        primes = s.primes_upto(s.integer_nth_root(bound, 2))
        for n in range(1, bound):
            if (
                s.check_k_full(n, 2, primes).is_full
                and s.check_k_full(n + 1, 3, primes).is_full
            ):
                brute.append(n)
        self.assertEqual([w["n"] for w in result["witnesses"]], brute)

    def test_oeis_list_orientation(self):
        receipt = s.check_oeis_baseline()
        self.assertEqual(receipt["listed_terms_checked"], 39)
        self.assertTrue(receipt["none_has_3full_successor"])


if __name__ == "__main__":
    unittest.main()
