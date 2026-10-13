import hashlib
import json
import unittest

from prime_exponent_reduction import (
    ap_product,
    build_receipt,
    canonical_receipt_json,
    perfect_power_certificate,
    reduce_power_exponent,
    scan_ap_window,
    scan_exponent_reductions,
    smallest_prime_divisor,
)


class PrimeExponentReductionTests(unittest.TestCase):
    def test_smallest_prime_divisor(self):
        expected = {2: 2, 3: 3, 4: 2, 6: 2, 9: 3, 25: 5, 49: 7, 77: 7, 97: 97}
        self.assertEqual({n: smallest_prime_divisor(n) for n in expected}, expected)

    def test_power_reduction_identity(self):
        for l in range(2, 129):
            for q in range(17):
                cert = reduce_power_exponent(q, l)
                self.assertTrue(cert.verify())
                self.assertEqual(l % cert.prime_exponent, 0)

    def test_perfect_power_certificates(self):
        for value in [1, 4, 8, 9, 16, 27, 32, 36, 64, 81, 125, 729, 4096]:
            cert = perfect_power_certificate(value)
            self.assertIsNotNone(cert, value)
            self.assertTrue(cert.verify())
        for value in [2, 3, 6, 10, 12, 18, 72, 360, 2310]:
            self.assertIsNone(perfect_power_certificate(value), value)

    def test_progression_product_control(self):
        self.assertEqual(ap_product(4, 1, 1), 24)
        self.assertEqual(ap_product(5, 1, 2), 1 * 3 * 5 * 7 * 9)

    def test_exponent_regression_digest(self):
        got = scan_exponent_reductions(10_000)
        self.assertEqual(got["rows"], 9_999)
        self.assertEqual(got["sha256"], "a71037ca58b44b3f87b0d984acd4ca4cbd2a6c835118e1d6e16cd705942817fe")

    def test_ap_scan_digest_and_no_hits(self):
        got = scan_ap_window(max_n=256, max_d=256, k_min=4, k_max=8)
        self.assertEqual(got["coprime_ap_candidates"], 199_475)
        self.assertEqual(got["perfect_power_hit_count"], 0)
        self.assertEqual(got["perfect_power_hits"], [])
        self.assertEqual(got["stream_sha256"], "1cae8794c66733beb4716bcb155c9d645dd33744375b9cd71187142159c4f7db")

    def test_receipt_is_canonical_and_stable(self):
        receipt = build_receipt()
        raw = canonical_receipt_json(receipt)
        self.assertEqual(raw, canonical_receipt_json(json.loads(raw)))
        self.assertEqual(hashlib.sha256(raw.encode()).hexdigest(), "8e1bc6fcbe3383a095fd0868516cc88a6d9e5c8745091b70639b63670241d18a")


if __name__ == "__main__":
    unittest.main()
