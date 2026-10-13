from __future__ import annotations

import unittest

from adapter import AdapterError, Scale, VoxelBounds, solve_all


class SolveAllEmptyInputTests(unittest.TestCase):
    def test_empty_input_fails_before_tracker_construction(self):
        constructions = 0

        def factory():
            nonlocal constructions
            constructions += 1
            raise AssertionError("tracker must not be constructed for empty solve_all input")

        with self.assertRaisesRegex(AdapterError, "empty detection collection"):
            solve_all(
                [],
                scale=Scale(),
                bounds=VoxelBounds(0, 1, 0, 1, 0, 1),
                configuration="cfg.json",
                max_search_radius=1.0,
                tracker_factory=factory,
            )

        self.assertEqual(constructions, 0)


if __name__ == "__main__":
    unittest.main()
