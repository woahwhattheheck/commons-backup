import copy
import json
import sys
import unittest
from itertools import product
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import residue_cover as rc


class ResidueCoverTests(unittest.TestCase):
    def test_candidate_set_is_exact_small_exponent_family(self):
        candidates = rc.small_exponent_candidates()
        self.assertEqual(len(candidates), 15)
        self.assertEqual(
            {c.shift for c in candidates},
            {2, 5, 8, 10, 13, 26, 29, 34, 37, 40, 61, 101, 104, 109, 136},
        )
        for c in candidates:
            self.assertEqual(c.shift, 4**c.a * 9**c.b + 4**c.c * 25**c.d)

    def test_four_adic_lifting_is_exact(self):
        core = 499
        witness = rc.SunWitness(11, 19, 0, 0, 2, 0)
        self.assertTrue(rc.check_sun_witness(core, witness))
        for q in range(6):
            lifted = rc.lift_witness_by_four(witness, q)
            self.assertTrue(rc.check_sun_witness(core * 4**q, lifted))
            self.assertEqual(rc.four_adic_core(core * 4**q), (core, q))

    def test_default_certificate_is_local_cover(self):
        cert = rc.build_certificate()
        self.assertEqual(cert["status"], "LOCAL_COVER_CERTIFIED")
        self.assertIsNone(cert["adversary"])
        rc.verify_certificate(cert)

    def test_default_certificate_digest_rejects_tamper(self):
        cert = rc.build_certificate()
        tampered = copy.deepcopy(cert)
        tampered["primes"][0] = 7
        with self.assertRaises(ValueError):
            rc.verify_certificate(tampered)

    def test_three_prime_band_bruteforce_matches_certificate(self):
        primes = (3, 7, 11)
        candidates = rc.small_exponent_candidates()
        modulus = 1
        for p in primes:
            modulus *= p * p
        for n in range(modulus):
            self.assertTrue(
                any(
                    all(not rc.is_exact_v1_mod_p2(n % (p * p), c.shift, p) for p in primes)
                    for c in candidates
                ),
                n,
            )

    def test_prime_31_breaks_same_small_candidate_local_cover(self):
        primes = rc.DEFAULT_PRIMES + (31,)
        candidates = rc.small_exponent_candidates()
        adversary = rc.find_adversarial_assignment(primes, candidates)
        self.assertIsNotNone(adversary)
        n = int(adversary["crt_residue"])
        modulus = int(adversary["crt_modulus"])
        self.assertEqual(modulus, 9_792_875_233_449)
        for c in candidates:
            self.assertTrue(
                any(rc.is_exact_v1_mod_p2(n % (p * p), c.shift, p) for p in primes),
                (n, c),
            )

    def test_small_family_global_hypothesis_fails_first_at_primitive_499(self):
        self.assertEqual(rc.first_small_family_failure(1000, primitive_only=True), 499)
        self.assertIsNone(rc.small_family_witness(499))
        witness = rc.brute_sun_witness(499)
        self.assertIsNotNone(witness)
        self.assertTrue(rc.check_sun_witness(499, witness))
        self.assertGreaterEqual(max(witness.a, witness.b, witness.c, witness.d), 2)

    def test_any_fixed_finite_shift_family_has_a_crt_killer_progression(self):
        shifts = [c.shift for c in rc.small_exponent_candidates()]
        killer = rc.fixed_shift_crt_killer(shifts)
        n = int(killer["positive_representative"])
        modulus = int(killer["crt_modulus"])
        self.assertGreater(n, max(shifts))
        self.assertGreater(modulus, 0)
        self.assertEqual(len(killer["assignments"]), len(shifts))
        for item in killer["assignments"]:
            shift = int(item["shift"])
            p = int(item["prime"] )
            self.assertEqual(p % 4, 3)
            self.assertEqual((n - shift) % p, 0)
            self.assertNotEqual((n - shift) % (p * p), 0)

    def test_fixed_shift_crt_killer_rejects_duplicates(self):
        with self.assertRaises(ValueError):
            rc.fixed_shift_crt_killer([2, 2])

    def test_crt(self):
        value, modulus = rc.crt_pairwise([4, 19, 24], [9, 49, 121])
        self.assertEqual(modulus, 53_361)
        self.assertEqual(value % 9, 4)
        self.assertEqual(value % 49, 19)
        self.assertEqual(value % 121, 24)

    def test_bad_mask_semantics(self):
        candidates = rc.small_exponent_candidates()
        for p in (3, 7, 11):
            for residue in range(p * p):
                mask = rc.bad_mask(p, residue, candidates)
                for i, c in enumerate(candidates):
                    self.assertEqual(bool(mask & (1 << i)), rc.is_exact_v1_mod_p2(residue, c.shift, p))

    def test_all_default_primes_are_valid_two_square_obstruction_primes(self):
        self.assertEqual(rc.validate_obstruction_primes(rc.DEFAULT_PRIMES), rc.DEFAULT_PRIMES)
        for bad in ((5,), (9,), (2,), (3, 3)):
            with self.assertRaises(ValueError):
                rc.validate_obstruction_primes(bad)


if __name__ == "__main__":
    unittest.main()
