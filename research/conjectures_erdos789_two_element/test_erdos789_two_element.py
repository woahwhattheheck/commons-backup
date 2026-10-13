import unittest

from erdos789_two_element import (
    UPPER_BOUND_WITNESSES,
    choose_two_nonzero,
    is_separating,
    make_receipt,
    max_separating_subset_size,
)

class TestErdos789TwoElement(unittest.TestCase):
    def test_two_distinct_nonzero_always_separating(self):
        for a in range(-12, 13):
            for b in range(-12, 13):
                if a and b and a != b:
                    self.assertTrue(is_separating((a, b)), (a, b))

    def test_zero_breaks_two_element_set(self):
        for a in range(-12, 13):
            if a:
                self.assertFalse(is_separating((0, a)))

    def test_canonical_witness(self):
        self.assertEqual(choose_two_nonzero((-2, 0, 7)), (-2, 7))
        self.assertEqual(choose_two_nonzero((0, 8, 3, -1)), (-1, 3))

    def test_universal_bounded_grid(self):
        receipt = make_receipt(radius=5, max_n=7)
        self.assertGreater(receipt["bounded_construction_cases"], 0)
        self.assertEqual(receipt["evidence_ceiling"].split()[0], "bounded")

    def test_small_n_upper_controls(self):
        expected = {1: 1, 2: 1, 3: 2, 4: 2}
        for n, A in UPPER_BOUND_WITNESSES.items():
            self.assertEqual(max_separating_subset_size(A), expected[n], (n, A))

    def test_three_element_relation_control(self):
        self.assertFalse(is_separating((1, 2, 3)))
        self.assertTrue(is_separating((1, 2)))

    def test_four_element_relation_control(self):
        A = (-1, 0, 1, 2)
        self.assertEqual(max_separating_subset_size(A), 2)

    def test_receipt_deterministic(self):
        self.assertEqual(make_receipt(radius=4, max_n=6), make_receipt(radius=4, max_n=6))

if __name__ == "__main__":
    unittest.main()
