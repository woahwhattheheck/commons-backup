from __future__ import annotations

import hashlib
import json
import unittest

import primorial_bound as pb


class PrimorialBoundTests(unittest.TestCase):
    def test_first_primes(self) -> None:
        self.assertEqual(pb.first_primes(10), [2, 3, 5, 7, 11, 13, 17, 19, 23, 29])

    def test_primorials(self) -> None:
        self.assertEqual(
            pb.primorials(10),
            [1, 2, 6, 30, 210, 2310, 30030, 510510, 9699690, 223092870, 6469693230],
        )

    def test_known_omega(self) -> None:
        cases = {1: 0, 2: 1, 12: 2, 30: 3, 210: 4, 2310: 5, 30030: 6}
        for n, want in cases.items():
            self.assertEqual(pb.distinct_prime_factor_count(n), want)

    def test_sieve_matches_direct_factorization(self) -> None:
        omega = pb.omega_sieve(5000)
        for n in range(1, 5001):
            self.assertEqual(int(omega[n]), pb.distinct_prime_factor_count(n))

    def test_sharp_minima_through_six_factors(self) -> None:
        receipt = pb.build_receipt(100_000, 10)
        minima = receipt["observed_minimum_m_by_exact_omega"]
        self.assertEqual(
            minima,
            {"0": 1, "1": 2, "2": 6, "3": 30, "4": 210, "5": 2310, "6": 30030},
        )

    def test_every_scanned_integer_satisfies_bound(self) -> None:
        omega = pb.omega_sieve(50_000)
        prods = pb.primorials(10)
        for n in range(1, 50_001):
            self.assertLessEqual(prods[int(omega[n])], n)

    def test_payload_hash_is_self_consistent(self) -> None:
        receipt = pb.build_receipt(10_000, 10)
        got = receipt.pop("payload_sha256")
        canonical = json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.assertEqual(got, hashlib.sha256(canonical).hexdigest())

    def test_invalid_inputs_fail(self) -> None:
        with self.assertRaises(ValueError):
            pb.first_primes(-1)
        with self.assertRaises(ValueError):
            pb.omega_sieve(-1)
        with self.assertRaises(ValueError):
            pb.distinct_prime_factor_count(0)
        with self.assertRaises(ValueError):
            pb.build_receipt(0, 5)


if __name__ == "__main__":
    unittest.main()
