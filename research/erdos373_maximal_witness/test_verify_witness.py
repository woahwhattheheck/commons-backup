import hashlib
import json
import unittest

import verify_witness as v


class WitnessTests(unittest.TestCase):
    def test_sponsor_witness_is_member(self):
        r = v.verify_member(16, [14, 5, 2])
        self.assertTrue(r.member_of_S)
        self.assertEqual(r.n_factorial, 20_922_789_888_000)
        self.assertEqual(r.factor_factorials, (87_178_291_200, 120, 2))
        self.assertEqual(r.rhs_product, r.n_factorial)

    def test_factorial_identity_is_exact(self):
        self.assertEqual(15 * 16, 5 * 4 * 3 * 2 * 1 * 2)
        self.assertEqual(240, 240)

    def test_wrong_last_factor_fails(self):
        self.assertFalse(v.verify_member(16, [14, 5, 3]).member_of_S)

    def test_wrong_order_fails(self):
        self.assertFalse(v.verify_member(16, [5, 14, 2]).member_of_S)

    def test_head_bound_fails(self):
        self.assertFalse(v.verify_member(16, [15, 2]).member_of_S)

    def test_entry_gt_one_fails(self):
        self.assertFalse(v.verify_member(16, [14, 5, 2, 1]).member_of_S)

    def test_receipt_is_deterministic(self):
        r = v.verify_member(16, [14, 5, 2])
        c1 = v.canonical_json(r)
        c2 = v.canonical_json(v.verify_member(16, [14, 5, 2]))
        self.assertEqual(c1, c2)
        self.assertEqual(hashlib.sha256(c1.encode()).hexdigest(), hashlib.sha256(c2.encode()).hexdigest())
        json.loads(c1)

    def test_scope_does_not_claim_maximality(self):
        self.assertEqual(v.verify_member(16, [14, 5, 2]).evidence_scope,
                         "FIRST_CONJUNCT_ONLY_NO_UNIVERSAL_MAXIMALITY_CLAIM")


if __name__ == "__main__":
    unittest.main()
