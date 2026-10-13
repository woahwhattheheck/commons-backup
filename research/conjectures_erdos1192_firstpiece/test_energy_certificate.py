import unittest

from energy_certificate import (
    check_coverage_lower_bound,
    check_finite_energy_lemma,
    exhaustive_receipt,
    finite_energy,
    normalize_set,
    representation_counts,
)


class EnergyCertificateTests(unittest.TestCase):
    def test_ordered_counts_small_control(self):
        self.assertEqual(representation_counts({0, 1}, 2), (1, 2, 1))
        self.assertEqual(finite_energy({0, 1}, 2), 6)

    def test_total_representations_identity(self):
        rec = check_finite_energy_lemma({0, 2, 5}, 3, 5)
        self.assertEqual(rec.total_representations, 27)
        self.assertEqual(rec.max_sum, 15)
        self.assertGreaterEqual(rec.lhs_scaled, rec.rhs_power)

    def test_truncation_is_explicit(self):
        rec = check_finite_energy_lemma({0, 1, 100}, 2, 1)
        self.assertEqual(rec.size, 2)
        self.assertEqual(rec.total_representations, 4)
        self.assertEqual(rec.energy, 6)

    def test_empty_set(self):
        rec = check_finite_energy_lemma(set(), 4, 7)
        self.assertEqual(rec.size, 0)
        self.assertEqual(rec.energy, 0)
        self.assertEqual(rec.rhs_power, 0)

    def test_coverage_lower_bound(self):
        # {0,1,2} with r=2 covers every sum 0..4, and 3^2 >= 5.
        self.assertTrue(check_coverage_lower_bound({0, 1, 2}, 2, 0, 4))
        # A sparse set does not satisfy the antecedent, so the helper reports False.
        self.assertFalse(check_coverage_lower_bound({0, 2}, 2, 0, 4))

    def test_input_validation(self):
        with self.assertRaises(ValueError):
            normalize_set({-1, 0})
        with self.assertRaises(ValueError):
            representation_counts({0, 1}, 0)
        with self.assertRaises(ValueError):
            check_finite_energy_lemma({0}, 2, -1)

    def test_exhaustive_receipt_is_deterministic(self):
        a = exhaustive_receipt(6, 2, 4)
        b = exhaustive_receipt(6, 2, 4)
        self.assertEqual(a, b)
        self.assertEqual(a["case_count"], 762)
        self.assertRegex(a["ordered_case_stream_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(a["minimum_slack"], 0)

    def test_default_receipt_shape(self):
        receipt = exhaustive_receipt()
        self.assertEqual(receipt["case_count"], 4088)
        self.assertGreater(receipt["equality_count"], 0)
        self.assertEqual(receipt["bounds"], {"max_m": 8, "min_r": 2, "max_r": 5})


if __name__ == "__main__":
    unittest.main()
