import unittest
from calc import ratio

class RatioReproduction(unittest.TestCase):
    def test_fraction(self):
        self.assertEqual(ratio(5, 2), 2.5)

if __name__ == "__main__":
    unittest.main()
