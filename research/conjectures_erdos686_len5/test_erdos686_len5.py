import unittest

from erdos686_len5 import (
    centered_identity,
    centered_quintic,
    eligible_len5_witness,
    find_len5_candidate,
    scan_len5,
    window5,
)


class Erdos686Len5Tests(unittest.TestCase):
    def test_centered_identity_small(self):
        for x in range(1000):
            self.assertTrue(centered_identity(x))
            self.assertEqual(window5(x), centered_quintic(x + 3))

    def test_window_strictly_increasing(self):
        for x in range(1000):
            self.assertLess(window5(x), window5(x + 1))

    def test_upper_bracket(self):
        for n in range(1000):
            self.assertGreater(window5(2 * n + 10), 4 * window5(n))

    def test_candidate_matches_bruteforce(self):
        for n in range(300):
            got = find_len5_candidate(n).m
            brute = None
            for m in range(n + 5, 2 * n + 11):
                if eligible_len5_witness(n, m):
                    brute = m
                    break
            self.assertEqual(got, brute)

    def test_no_small_witness(self):
        report = scan_len5(10_000)
        self.assertEqual(report["witnesses"], 0)

    def test_known_overlap_is_not_eligible(self):
        self.assertFalse(eligible_len5_witness(0, 1))

    def test_negative_rejected(self):
        with self.assertRaises(ValueError):
            window5(-1)
        with self.assertRaises(ValueError):
            find_len5_candidate(-1)
        with self.assertRaises(ValueError):
            scan_len5(-1)


if __name__ == "__main__":
    unittest.main()
