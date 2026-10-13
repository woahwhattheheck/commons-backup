# SPDX-License-Identifier: Apache-2.0
import unittest

from joint_assignment import (
    JointAssignmentError,
    _extract_bundle,
    _pickup_full,
    _position,
)


class PositionMechanics:
    def __init__(self, position):
        self.position = position

    def _farmer_position(self, farm, worker):
        return self.position


class JointAssignmentExactnessTests(unittest.TestCase):
    def test_exact_integer_position_is_preserved(self):
        self.assertEqual(_position(PositionMechanics([1, 2]), {}, 0, 5), (1, 2))

    def test_lossy_positions_fail_closed(self):
        malformed = ([1.5, 2], ["1", 2], [True, 2], [1, 2, 3], "12", None)
        for position in malformed:
            with self.subTest(position=position):
                with self.assertRaises(JointAssignmentError):
                    _position(PositionMechanics(position), {}, 0, 5)

    def test_out_of_bounds_position_fails_closed(self):
        for position in ([-1, 2], [5, 2], [2, -1], [2, 5]):
            with self.subTest(position=position):
                with self.assertRaises(JointAssignmentError):
                    _position(PositionMechanics(position), {}, 0, 5)

    def test_pickup_quantity_requires_plain_positive_integer(self):
        before = {"inventories": [{"WHEAT": 1}]}
        after = {"inventories": [{"WHEAT": 3}]}
        self.assertTrue(_pickup_full(before, after, 0, ["PICKUP", "WHEAT", 2]))
        for quantity in (2.0, "2", True, 0, -1):
            with self.subTest(quantity=quantity):
                self.assertFalse(
                    _pickup_full(before, after, 0, ["PICKUP", "WHEAT", quantity])
                )

    def test_bundle_rejects_malformed_pickup_before_simulation(self):
        route = [
            {"farmer": ["PICKUP", "WHEAT", "2"]},
            {"farmer": ["WATER"]},
            {"farmer": ["DROP"]},
        ]
        bundle, reason = _extract_bundle(
            PositionMechanics([0, 0]), {}, route, 0, 0, 2, 5
        )
        self.assertIsNone(bundle)
        self.assertEqual(reason, "malformed_pickup")


if __name__ == "__main__":
    unittest.main()
