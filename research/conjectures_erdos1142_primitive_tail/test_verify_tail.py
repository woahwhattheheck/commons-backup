import hashlib
import json
import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import verify_tail as v


class PrimitiveRootTailTests(unittest.TestCase):
    def test_prime_scan(self):
        self.assertEqual(
            v.primes_upto(45),
            [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43],
        )

    def test_exact_primitive_root_classification(self):
        self.assertEqual(v.relevant_primitive_root_primes(), [3, 5, 11, 13, 19, 29, 37])

    def test_all_primitive_root_coverings_are_complete(self):
        for p in v.EXPECTED_PRIMITIVE_ROOT_PRIMES:
            witnesses = v.covering_witnesses(p)
            self.assertEqual(set(witnesses), set(range(1, p)))
            self.assertEqual(v.order_two_mod_prime(p), p - 1)

    def test_every_other_odd_prime_fails_covering(self):
        for p in v.primes_upto(45):
            if p == 2 or p in v.EXPECTED_PRIMITIVE_ROOT_PRIMES:
                continue
            witnesses = v.covering_witnesses(p)
            self.assertNotEqual(set(witnesses), set(range(1, p)))
            self.assertLess(v.order_two_mod_prime(p), p - 1)

    def test_new_instances(self):
        self.assertEqual(v.order_two_mod_prime(29), 28)
        self.assertEqual(v.threshold(29), 268435485)
        self.assertEqual(v.order_two_mod_prime(37), 36)
        self.assertEqual(v.threshold(37), 68719476773)

    def test_cumulative_products(self):
        rows = v.build_payload()["primitive_root_rows"]
        self.assertEqual(
            [r["cumulative_product"] for r in rows],
            [3, 15, 165, 2145, 40755, 1181895, 43730115],
        )

    def test_piecewise_residual_counts(self):
        intervals = v.tail_intervals()
        self.assertEqual([i.candidate_count for i in intervals], [121, 6580, 57916, 400718])
        self.assertEqual(
            [i.first_candidate for i in intervals],
            [4290, 285285, 269472060, 68743740780],
        )
        self.assertEqual(
            [i.last_candidate for i in intervals],
            [261690, 268412430, 68718920985, 17592144233235],
        )
        self.assertEqual(sum(i.candidate_count for i in intervals), 465335)

    def test_reduction_against_published_p19_tail(self):
        payload = v.build_payload()
        self.assertEqual(payload["existing_sharp_residual_candidate_count"], 431657237)
        self.assertEqual(payload["refined_residual_candidate_count"], 465335)
        self.assertGreater(
            payload["existing_sharp_residual_candidate_count"],
            900 * payload["refined_residual_candidate_count"],
        )

    def test_committed_receipt_matches_regeneration(self):
        committed = json.loads((HERE / "receipt.json").read_text())
        generated = v.build_receipt()
        self.assertEqual(committed, generated)
        self.assertEqual(
            committed["payload_sha256"],
            hashlib.sha256(v.canonical_json_bytes(committed["payload"])).hexdigest(),
        )


if __name__ == "__main__":
    unittest.main()
