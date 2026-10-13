import json
import unittest
from fractions import Fraction

import finite_crt_sieve as s


class TestFiniteCrtSieve(unittest.TestCase):
    def test_four_never_divides(self):
        for n in range(256):
            self.assertNotEqual((n**4 + 2) % 4, 0)

    def test_local_contract_primes_through_251(self):
        for p in s.primes_upto(251):
            s.assert_local_contract(s.prime_record(p))

    def test_mod8_obstruction_filter(self):
        for p in s.primes_upto(251):
            rec = s.prime_record(p)
            if rec.bad_count and p != 2:
                self.assertIn(p % 8, (1, 3))

    def test_crt_round_trip(self):
        primes = [3, 11, 19]
        residues = [4, 7, 33]
        x, m = s.crt(residues, [p * p for p in primes])
        self.assertEqual(m, 9 * 121 * 361)
        for a, p in zip(residues, primes):
            self.assertEqual(x % (p * p), a % (p * p))

    def test_formula_matches_direct_exhaustion(self):
        primes = [3, 11, 19]
        formula = s.finite_sieve_formula(primes)
        period, direct = s.direct_good_count(primes)
        self.assertEqual(period, formula["period"])
        self.assertEqual(direct, formula["good_count"])
        self.assertGreaterEqual(direct, formula["generic_lower_bound"])
        self.assertGreater(direct, 0)

    def test_construct_good_class(self):
        primes = [3, 11, 19]
        locals_ = []
        for p in primes:
            bad = set(s.bad_residues_mod_p2(p))
            locals_.append(next(a for a in range(p * p) if a not in bad))
        x, period = s.construct_good_class(locals_, primes)
        self.assertLess(x, period)
        for p in primes:
            self.assertNotEqual((x**4 + 2) % (p * p), 0)

    def test_receipt_is_deterministic_and_truthful(self):
        a = s.build_receipt(251)
        b = s.build_receipt(251)
        self.assertEqual(a, b)
        ctl = a["exhaustive_crt_control"]
        self.assertEqual(ctl["direct_good_count"], ctl["product_good_count"])
        self.assertEqual(Fraction(ctl["density_num"], ctl["density_den"]), Fraction(ctl["direct_good_count"], ctl["period"]))
        self.assertEqual(len(a["receipt_payload_sha256"]), 64)
        json.dumps(a, sort_keys=True)

    def test_invalid_inputs_fail_closed(self):
        with self.assertRaises(ValueError):
            s.finite_sieve_formula([3, 3])
        with self.assertRaises(ValueError):
            s.finite_sieve_formula([9])
        with self.assertRaises(ValueError):
            s.crt_pair(0, 6, 0, 9)
        with self.assertRaises(ValueError):
            s.construct_good_class([1], [3, 11])


if __name__ == "__main__":
    unittest.main()
