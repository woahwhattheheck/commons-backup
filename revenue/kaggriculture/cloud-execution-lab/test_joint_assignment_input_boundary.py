# SPDX-License-Identifier: Apache-2.0
import unittest

from joint_assignment import JointAssignmentError, propose_pair_swap


class JointAssignmentInputBoundaryTests(unittest.TestCase):
    @staticmethod
    def _obs():
        return {"player": 0, "farms": [{}], "private": {}}

    def test_config_requires_plain_positive_integers(self):
        malformed = (24.0, "24", True, 0, -1, None)
        for key in ("turnsPerDay", "shedCapacity"):
            for value in malformed:
                with self.subTest(key=key, value=value):
                    with self.assertRaises(JointAssignmentError):
                        propose_pair_swap(
                            None,
                            self._obs(),
                            [],
                            0,
                            1,
                            start_step=0,
                            end_step=0,
                            configuration={key: value},
                            checkpoints=(),
                        )

    def test_one_shot_checkpoint_iterator_detects_late_boundary(self):
        checkpoints = (step for step in (2,))
        result = propose_pair_swap(
            None,
            self._obs(),
            [],
            0,
            1,
            start_step=0,
            end_step=2,
            configuration={"turnsPerDay": 24, "shedCapacity": 100},
            checkpoints=checkpoints,
        )
        self.assertFalse(result.changed)
        self.assertEqual(result.reason, "checkpoint_boundary")

    def test_checkpoint_values_require_plain_nonnegative_integers(self):
        for checkpoint in (2.0, "2", True, -1, None):
            with self.subTest(checkpoint=checkpoint):
                with self.assertRaises(JointAssignmentError):
                    propose_pair_swap(
                        None,
                        self._obs(),
                        [],
                        0,
                        1,
                        start_step=0,
                        end_step=2,
                        checkpoints=(checkpoint,),
                    )

    def test_valid_nondefault_config_and_tuple_checkpoint_remain_supported(self):
        result = propose_pair_swap(
            None,
            self._obs(),
            [],
            0,
            1,
            start_step=0,
            end_step=2,
            configuration={"turnsPerDay": 12, "shedCapacity": 75},
            checkpoints=(2,),
        )
        self.assertFalse(result.changed)
        self.assertEqual(result.reason, "checkpoint_boundary")


if __name__ == "__main__":
    unittest.main()
