import unittest
from sigma_growth import sigma, iterate_sigma, build_receipt


class SigmaGrowthTests(unittest.TestCase):
    def test_known_values(self):
        self.assertEqual(sigma(1), 1)
        self.assertEqual(sigma(2), 3)
        self.assertEqual(sigma(6), 12)
        self.assertEqual(sigma(12), 28)
        self.assertEqual(sigma(28), 56)

    def test_iterate(self):
        self.assertEqual(iterate_sigma(2, 0), 2)
        self.assertEqual(iterate_sigma(2, 1), 3)
        self.assertEqual(iterate_sigma(2, 2), 4)
        self.assertEqual(iterate_sigma(2, 3), 7)

    def test_strict_growth_small(self):
        for n in range(2, 2000):
            self.assertGreater(sigma(n), n)

    def test_receipt(self):
        r = build_receipt(limit=10000, orbit_seed_limit=256, orbit_steps=8)
        self.assertEqual(r['strict_growth_failures'], [])
        self.assertEqual(r['orbit_failures'], [])
        self.assertEqual(r['strict_growth_cases'], 9999)
        self.assertEqual(r['orbit_transition_cases'], 2040)
        self.assertEqual(len(r['orbit_stream_sha256']), 64)


if __name__ == '__main__':
    unittest.main()
