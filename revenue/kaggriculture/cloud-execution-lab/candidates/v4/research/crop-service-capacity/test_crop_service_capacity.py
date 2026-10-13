# SPDX-License-Identifier: Apache-2.0
import copy
import importlib.util
from pathlib import Path
import unittest
import sys

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("crop_service_capacity", HERE / "crop_service_capacity.py")
mod = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = mod
SPEC.loader.exec_module(mod)


def obs(*, hour=0, step=None, hands=0, empty=25, player=0):
    if step is None:
        step = hour
    side = 5
    cells = [None] * empty + ["LOCKED"] * (side * side - empty)
    rows = [cells[i:i + side] for i in range(0, len(cells), side)]
    farm = {
        "farmer": [2, 2],
        "hands": [[2, 2] for _ in range(hands)],
        "tiles": rows,
    }
    return {"player": player, "hour": hour, "step": step, "farms": [farm]}


class CapacityTests(unittest.TestCase):
    def test_opening_current_labor_cap_is_twelve(self):
        e = mod.capacity_envelope(obs(hour=0, hands=0))
        self.assertEqual(e.callbacks_remaining, 24)
        self.assertEqual(e.current_labor_action_slots, 24)
        self.assertEqual(e.current_labor_ceiling, 12)

    def test_last_hour_one_actor_cannot_establish_plant(self):
        e = mod.capacity_envelope(obs(hour=23, hands=0))
        self.assertEqual(e.current_labor_action_slots, 1)
        self.assertEqual(e.future_hire_action_slots_upper, 0)
        self.assertEqual(e.absolute_action_ceiling, 0)

    def test_last_hour_two_actors_can_have_one_pair_of_unit_actions(self):
        e = mod.capacity_envelope(obs(hour=23, hands=1))
        self.assertEqual(e.absolute_action_ceiling, 1)

    def test_future_hires_are_only_in_absolute_bound(self):
        e = mod.capacity_envelope(
            obs(hour=22, hands=0),
            {"turnsPerDay": 24, "maxMarketOrdersPerTurn": 10},
            configuration_authenticated=True,
        )
        self.assertEqual(e.current_labor_action_slots, 2)
        self.assertEqual(e.current_labor_ceiling, 1)
        self.assertEqual(e.future_hire_action_slots_upper, 10)
        self.assertEqual(e.absolute_action_ceiling, 6)

    def test_current_empty_tiles_are_telemetry_not_hard_future_cap(self):
        e = mod.capacity_envelope(obs(hour=0, hands=4, empty=3))
        self.assertEqual(e.empty_owned_tiles, 3)
        self.assertEqual(e.board_tiles, 25)
        self.assertEqual(e.current_labor_ceiling, 25)
        self.assertEqual(e.absolute_action_ceiling, 25)

    def test_future_land_prevents_false_impossible_under_no_hire_bound(self):
        # At hour 20 a BUY_LAND can execute after this callback and unlock cells
        # for hours 21-23. The bound is intentionally not a schedule proof; it
        # must not reject 2 plants merely because only 1 cell is empty *now*.
        result = mod.assess_proposed_expansion(
            obs(hour=20, hands=1, empty=1), 2, no_future_hires=True
        )
        self.assertEqual(result["verdict"], "NOT_CERTIFIED")
        self.assertEqual(result["envelope"]["empty_owned_tiles"], 1)
        self.assertEqual(result["envelope"]["board_tiles"], 25)
        self.assertEqual(result["ceiling"], 4)

    def test_locked_or_occupied_tiles_are_not_current_empty(self):
        o = obs(hour=0, empty=25)
        o["farms"][0]["tiles"][0][0] = "LOCKED"
        o["farms"][0]["tiles"][0][1] = {"kind": "PLANT", "crop": "WHEAT"}
        o["farms"][0]["tiles"][0][2] = {"kind": "COOP"}
        e = mod.capacity_envelope(o)
        self.assertEqual(e.empty_owned_tiles, 22)
        self.assertEqual(e.board_tiles, 25)

    def test_custom_turns_and_market_cap(self):
        e = mod.capacity_envelope(
            obs(hour=4, hands=1),
            {"turnsPerDay": 8, "maxMarketOrdersPerTurn": 2},
            configuration_authenticated=True,
        )
        self.assertEqual(e.callbacks_remaining, 4)
        self.assertEqual(e.current_labor_action_slots, 8)
        self.assertEqual(e.future_hire_action_slots_upper, 12)
        self.assertEqual(e.current_labor_ceiling, 4)
        self.assertEqual(e.absolute_action_ceiling, 10)

    def test_conditional_no_hire_rejection(self):
        result = mod.assess_proposed_expansion(obs(hour=22), 2, no_future_hires=True)
        self.assertEqual(result["verdict"], "IMPOSSIBLE_ACTION_BUDGET")
        self.assertEqual(result["ceiling"], 1)
        self.assertEqual(result["bound"], "current_labor")

    def test_absolute_bound_refuses_false_safe_claim(self):
        result = mod.assess_proposed_expansion(obs(hour=22), 6)
        self.assertEqual(result["verdict"], "NOT_CERTIFIED")
        self.assertEqual(result["ceiling"], 6)

    def test_above_absolute_bound_is_impossible(self):
        result = mod.assess_proposed_expansion(obs(hour=22), 7)
        self.assertEqual(result["verdict"], "IMPOSSIBLE_ACTION_BUDGET")

    def test_board_cell_cap_still_bounds_enormous_labor(self):
        e = mod.capacity_envelope(obs(hour=0, hands=50, empty=1))
        self.assertEqual(e.current_labor_ceiling, 25)
        self.assertEqual(e.absolute_action_ceiling, 25)

    def test_zero_proposal_is_not_certified_not_promoted(self):
        result = mod.assess_proposed_expansion(obs(hour=23), 0)
        self.assertEqual(result["verdict"], "NOT_CERTIFIED")

    def test_bool_poison_rejected_for_hour(self):
        with self.assertRaises(mod.CapacityInputError):
            mod.capacity_envelope(obs(hour=True))

    def test_bool_poison_rejected_for_proposal(self):
        with self.assertRaises(mod.CapacityInputError):
            mod.assess_proposed_expansion(obs(), True)

    def test_invalid_player_refused(self):
        o = obs()
        o["player"] = 1
        with self.assertRaises(mod.CapacityInputError):
            mod.capacity_envelope(o)

    def test_nonrectangular_tiles_refused(self):
        o = obs()
        o["farms"][0]["tiles"][0].append(None)
        with self.assertRaises(mod.CapacityInputError):
            mod.capacity_envelope(o)

    def test_out_of_day_hour_refused(self):
        with self.assertRaises(mod.CapacityInputError):
            mod.capacity_envelope(obs(hour=24))

    def test_terminal_partial_day_does_not_require_phantom_water(self):
        # Standard episodeSteps=720 makes step 718 the final executable callback.
        # Starting the final day at step 696 leaves 23 executable callbacks but
        # no hour-23 EOD. Thirteen one-action PLANTs are therefore not impossible
        # by action count even though the old PLANT+WATER theorem capped at 12.
        result = mod.assess_proposed_expansion(
            obs(hour=0, step=696, hands=0), 13, no_future_hires=True
        )
        self.assertEqual(result["verdict"], "NOT_CERTIFIED")
        self.assertEqual(result["ceiling"], 23)
        self.assertEqual(result["envelope"]["callbacks_remaining"], 23)
        self.assertFalse(result["envelope"]["eod_reachable_before_terminal"])
        self.assertEqual(
            result["envelope"]["unit_actions_per_surviving_new_plant"], 1
        )

    def test_last_real_eod_keeps_two_action_charge(self):
        result = mod.assess_proposed_expansion(
            obs(hour=23, step=695, hands=0), 1, no_future_hires=True
        )
        self.assertEqual(result["verdict"], "IMPOSSIBLE_ACTION_BUDGET")
        self.assertEqual(result["ceiling"], 0)
        self.assertTrue(result["envelope"]["eod_reachable_before_terminal"])
        self.assertEqual(
            result["envelope"]["unit_actions_per_surviving_new_plant"], 2
        )

    def test_after_final_executable_callback_refused(self):
        with self.assertRaisesRegex(
            mod.CapacityInputError, "^step_after_final_executable_callback$"
        ):
            mod.capacity_envelope(obs(hour=23, step=719))

    def test_hour_step_mismatch_refused(self):
        with self.assertRaisesRegex(mod.CapacityInputError, "^hour_step_mismatch$"):
            mod.capacity_envelope(obs(hour=23, step=22))

    def test_inputs_not_mutated(self):
        o = obs(hour=7, hands=2)
        before = copy.deepcopy(o)
        mod.assess_proposed_expansion(o, 3)
        self.assertEqual(o, before)

    def test_engine_config_and_donor_identity_exposed(self):
        r = mod.assess_proposed_expansion(obs(), 1)
        self.assertEqual(r["engine_git_blob"], "3c202c7ee921da239356789e266b694635103fc4")
        self.assertEqual(
            r["configuration_git_blob"],
            "b354d06b742fe48402513792253f1a5c29366b20",
        )
        self.assertEqual(r["historical_donor_pr"], 9806)

    def test_explicit_configuration_requires_authentication_for_envelope(self):
        with self.assertRaisesRegex(
            mod.CapacityInputError, "^configuration_not_authenticated$"
        ):
            mod.capacity_envelope(
                obs(hour=0),
                {"turnsPerDay": 1, "maxMarketOrdersPerTurn": 1},
            )

    def test_unauthenticated_custom_config_cannot_certify_impossibility(self):
        # With trusted turnsPerDay=1, one actor has only one unit slot and
        # proposal 1 exceeds the zero-plant PLANT+WATER ceiling. Without custody,
        # those caller values cannot be allowed to manufacture IMPOSSIBLE.
        result = mod.assess_proposed_expansion(
            obs(hour=0),
            1,
            {"turnsPerDay": 1, "maxMarketOrdersPerTurn": 1},
        )
        self.assertEqual(result["verdict"], "NOT_CERTIFIED")
        self.assertEqual(result["reason"], "configuration_not_authenticated")
        self.assertIsNone(result["ceiling"])
        self.assertIsNone(result["envelope"])

    def test_authenticated_custom_config_can_certify_exact_bound(self):
        result = mod.assess_proposed_expansion(
            obs(hour=0),
            1,
            {"turnsPerDay": 1, "maxMarketOrdersPerTurn": 1},
            configuration_authenticated=True,
        )
        self.assertEqual(result["verdict"], "IMPOSSIBLE_ACTION_BUDGET")
        self.assertEqual(result["ceiling"], 0)
        self.assertEqual(result["envelope"]["turns_per_day"], 1)


if __name__ == "__main__":
    unittest.main()
