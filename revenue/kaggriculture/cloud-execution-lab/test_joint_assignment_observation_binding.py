# SPDX-License-Identifier: Apache-2.0
"""P07 certificates must be bound to the exact public seat and clock."""
import copy
import unittest

from joint_assignment import JointAssignmentError, propose_pair_swap
from test_joint_assignment import crossing_fixture


class JointAssignmentObservationBindingTests(unittest.TestCase):
    def certify(self, obs, route, *, start_step=0, end_step=14, configuration=None):
        mechanics, _, _ = crossing_fixture()
        return propose_pair_swap(
            mechanics,
            obs,
            route,
            0,
            1,
            start_step=start_step,
            end_step=end_step,
            configuration=configuration,
        )

    def fixture(self):
        mechanics, obs, route = crossing_fixture()
        return mechanics, copy.deepcopy(obs), copy.deepcopy(route)

    def test_exact_public_clock_remains_certifiable(self):
        mechanics, obs, route = self.fixture()
        obs.update(step=0, day=0, hour=0)
        result = propose_pair_swap(
            mechanics, obs, route, 0, 1, start_step=0, end_step=14
        )
        self.assertTrue(result.changed, result.reason)

    def test_clock_absent_legacy_helper_fixture_remains_supported(self):
        mechanics, obs, route = self.fixture()
        result = propose_pair_swap(
            mechanics, obs, route, 0, 1, start_step=0, end_step=14
        )
        self.assertTrue(result.changed, result.reason)

    def test_stale_or_future_step_cannot_relabel_current_state(self):
        mechanics, obs, route = self.fixture()
        obs.update(step=1, day=0, hour=1)
        with self.assertRaisesRegex(JointAssignmentError, "step does not match start_step"):
            propose_pair_swap(
                mechanics, obs, route, 0, 1, start_step=0, end_step=14
            )

    def test_day_and_hour_must_match_start_step(self):
        for field, value in (("day", 1), ("hour", 1)):
            with self.subTest(field=field):
                mechanics, obs, route = self.fixture()
                obs.update(step=0, day=0, hour=0)
                obs[field] = value
                with self.assertRaisesRegex(
                    JointAssignmentError, rf"{field} does not match start_step"
                ):
                    propose_pair_swap(
                        mechanics, obs, route, 0, 1, start_step=0, end_step=14
                    )

    def test_public_clock_rejects_coercible_non_integer_values(self):
        for field in ("step", "day", "hour"):
            for value in (False, 0.0, "0"):
                with self.subTest(field=field, value=value):
                    mechanics, obs, route = self.fixture()
                    obs.update(step=0, day=0, hour=0)
                    obs[field] = value
                    with self.assertRaisesRegex(
                        JointAssignmentError, rf"{field} must be a plain integer"
                    ):
                        propose_pair_swap(
                            mechanics, obs, route, 0, 1,
                            start_step=0, end_step=14,
                        )

    def test_player_rejects_coercible_and_out_of_range_values(self):
        for player in (False, 0.0, "0", -1, 1):
            with self.subTest(player=player):
                mechanics, obs, route = self.fixture()
                obs.update(step=0, day=0, hour=0)
                obs["player"] = player
                message = ("player must be a plain integer"
                           if type(player) is not int else "player is out of range")
                with self.assertRaisesRegex(JointAssignmentError, message):
                    propose_pair_swap(
                        mechanics, obs, route, 0, 1,
                        start_step=0, end_step=14,
                    )

    def test_nondefault_clock_uses_existing_turns_per_day_contract(self):
        mechanics, obs, route = self.fixture()
        # Re-key the same 15-row route into a 30-turn day without changing the
        # already-tested config parser owned by the sibling exactness lane.
        route = {30 + step: row for step, row in enumerate(route)}
        obs.update(step=30, day=1, hour=0)
        result = propose_pair_swap(
            mechanics, obs, route, 0, 1,
            start_step=30, end_step=44,
            configuration={"turnsPerDay": 30},
        )
        self.assertTrue(result.changed, result.reason)


if __name__ == "__main__":
    unittest.main()
