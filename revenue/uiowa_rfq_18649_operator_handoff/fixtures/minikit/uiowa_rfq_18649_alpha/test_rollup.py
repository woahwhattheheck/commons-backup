import unittest
from rollup import rollup


class TestRollup(unittest.TestCase):
    def test_sums(self):
        self.assertEqual(rollup([{"count": 2}, {"count": 3}])["total"], 5)

    def test_absent_input_is_not_zero(self):
        out = rollup([{"count": 2}, {"count": None}])
        self.assertEqual(out["total"], 2)
        self.assertEqual(out["unknown_inputs"], 1)


if __name__ == "__main__":
    unittest.main()
