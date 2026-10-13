# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("plant_guard", HERE / "plant_guard.py")
mod = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = mod
SPEC.loader.exec_module(mod)


def observation(
    *, hour=23, step=None, farmer=(1, 1), hands=(), seeds=None, occupied=()
):
    if step is None:
        step = hour
    size = 4
    tiles = [[None for _ in range(size)] for _ in range(size)]
    for x, y in occupied:
        tiles[y][x] = "LOCKED"
    seed_map = {crop: 10 for crop in mod.CROPS}
    if seeds is not None:
        seed_map.update(seeds)
    farm = {
        "farmer": list(farmer),
        "hands": [list(pos) for pos in hands],
        "tiles": tiles,
    }
    return {
        "player": 0,
        "hour": hour,
        "step": step,
        "farms": [farm],
        "private": {"seeds": seed_map},
    }


def action(farmer=("PASS",), hands=(), market=()):
    return {
        "farmer": list(farmer),
        "hands": [list(row) for row in hands],
        "market": [list(row) for row in market],
    }


def assess(
    obs, selected, suffix=(), config=None, *, config_authenticated=False
):
    return mod.assess_same_eod_plant_survival(
        obs,
        selected,
        suffix,
        config,
        suffix_authenticated=True,
        configuration_authenticated=config_authenticated,
    )


class PlantGuardTests(unittest.TestCase):
    def test_last_hour_single_actor_plant_is_doomed(self):
        result = assess(observation(), action(("PLANT", "WHEAT")))
        self.assertEqual(result["verdict"], "DOOMED_AUTHORED_SUFFIX")
        self.assertEqual(result["doomed_actor_indices"], [0])

    def test_same_callback_later_water_rescues(self):
        obs = observation(hands=((1, 1),))
        selected = action(("PLANT", "WHEAT"), hands=(("WATER",),))
        result = assess(obs, selected)
        self.assertEqual(result["reason"], "water_found_before_eod")
        self.assertEqual(result["watered_actor_indices"], [0])

    def test_same_callback_water_before_plant_does_not_rescue(self):
        obs = observation(farmer=(1, 1), hands=((1, 1),))
        selected = action(("WATER",), hands=(("PLANT", "WHEAT"),))
        result = assess(obs, selected)
        self.assertEqual(result["verdict"], "DOOMED_AUTHORED_SUFFIX")
        self.assertEqual(result["doomed_actor_indices"], [1])

    def test_next_callback_same_actor_water_rescues(self):
        obs = observation(hour=22)
        selected = action(("PLANT", "WHEAT"))
        suffix = [action(("WATER",))]
        result = assess(obs, selected, suffix)
        self.assertEqual(result["reason"], "water_found_before_eod")

    def test_move_away_then_water_wrong_tile_is_doomed(self):
        obs = observation(hour=21)
        selected = action(("PLANT", "WHEAT"))
        suffix = [action(("EAST",)), action(("WATER",))]
        result = assess(obs, selected, suffix)
        self.assertEqual(result["verdict"], "DOOMED_AUTHORED_SUFFIX")

    def test_other_actor_can_move_then_water_target(self):
        obs = observation(hour=21, farmer=(1, 1), hands=((0, 1),))
        selected = action(("PLANT", "WHEAT"), hands=(("PASS",),))
        suffix = [
            action(("PASS",), hands=(("EAST",),)),
            action(("PASS",), hands=(("WATER",),)),
        ]
        result = assess(obs, selected, suffix)
        self.assertEqual(result["reason"], "water_found_before_eod")
        self.assertEqual(result["watered_actor_indices"], [0])

    def test_out_of_bounds_move_is_noop_so_later_water_rescues(self):
        obs = observation(hour=21, farmer=(0, 0))
        selected = action(("PLANT", "WHEAT"))
        suffix = [action(("WEST",)), action(("WATER",))]
        result = assess(obs, selected, suffix)
        self.assertEqual(result["reason"], "water_found_before_eod")

    def test_incomplete_suffix_is_not_certified(self):
        obs = observation(hour=21)
        result = assess(obs, action(("PLANT", "WHEAT")), [action(("PASS",))])
        self.assertEqual(result["verdict"], "NOT_CERTIFIED")
        self.assertEqual(result["reason"], "incomplete_authored_suffix")

    def test_current_hire_before_last_hour_is_ambiguity(self):
        obs = observation(hour=22)
        selected = action(("PLANT", "WHEAT"), market=(("HIRE",),))
        result = assess(obs, selected, [action(("PASS",))])
        self.assertEqual(result["reason"], "current_hire_actor_ambiguity")

    def test_final_hour_hire_cannot_create_pre_eod_water_actor(self):
        obs = observation(hour=23)
        selected = action(("PLANT", "WHEAT"), market=(("HIRE",),))
        result = assess(obs, selected)
        self.assertEqual(result["verdict"], "DOOMED_AUTHORED_SUFFIX")

    def test_future_final_hour_hire_is_irrelevant(self):
        obs = observation(hour=22)
        selected = action(("PLANT", "WHEAT"))
        suffix = [action(("PASS",), market=(("HIRE",),))]
        result = assess(obs, selected, suffix)
        self.assertEqual(result["verdict"], "DOOMED_AUTHORED_SUFFIX")

    def test_hire_beyond_market_cap_is_inert_for_ambiguity(self):
        obs = observation(hour=22)
        selected = action(
            ("PLANT", "WHEAT"),
            market=(("SELL", "WOOL", 1), ("HIRE",)),
        )
        result = assess(
            obs,
            selected,
            [action(("PASS",))],
            {"maxMarketOrdersPerTurn": 1, "turnsPerDay": 24},
            config_authenticated=True,
        )
        self.assertEqual(result["verdict"], "DOOMED_AUTHORED_SUFFIX")

    def test_atomic_seed_overshoot_means_no_executable_plant(self):
        obs = observation(hands=((2, 2),), seeds={"WHEAT": 1})
        selected = action(
            ("PLANT", "WHEAT"),
            hands=(("PLANT", "WHEAT"),),
        )
        result = assess(obs, selected)
        self.assertEqual(result["reason"], "no_executable_current_plant")

    def test_only_first_colocated_plant_can_execute(self):
        obs = observation(hands=((1, 1),), seeds={"WHEAT": 2, "CARROT": 2})
        selected = action(
            ("PLANT", "WHEAT"),
            hands=(("PLANT", "CARROT"),),
        )
        result = assess(obs, selected)
        self.assertEqual(result["candidate_actor_indices"], [0])
        self.assertEqual(result["doomed_actor_indices"], [0])

    def test_nonempty_tile_is_not_a_candidate(self):
        obs = observation(occupied=((1, 1),))
        result = assess(obs, action(("PLANT", "WHEAT")))
        self.assertEqual(result["reason"], "no_executable_current_plant")

    def test_unauthenticated_suffix_never_rejects(self):
        obs = observation()
        result = mod.assess_same_eod_plant_survival(
            obs, action(("PLANT", "WHEAT")), (), suffix_authenticated=False
        )
        self.assertEqual(result["verdict"], "NOT_CERTIFIED")
        self.assertEqual(result["reason"], "suffix_not_authenticated")

    def test_actor_cardinality_change_fails_closed(self):
        obs = observation(hour=22, hands=((0, 0),))
        selected = action(("PLANT", "WHEAT"), hands=(("PASS",),))
        bad_suffix = [action(("PASS",), hands=())]
        result = assess(obs, selected, bad_suffix)
        self.assertEqual(result["verdict"], "NOT_CERTIFIED")
        self.assertIn("cardinality", result["reason"])

    def test_mixed_multiple_plants_report_only_unwatered_actors(self):
        obs = observation(
            hour=22,
            farmer=(1, 1),
            hands=((2, 1), (0, 1)),
            seeds={"WHEAT": 2, "CARROT": 2},
        )
        selected = action(
            ("PLANT", "WHEAT"),
            hands=(("PLANT", "CARROT"), ("PASS",)),
        )
        suffix = [
            action(
                ("WATER",),
                hands=(("PASS",), ("PASS",)),
            )
        ]
        result = assess(obs, selected, suffix)
        self.assertEqual(result["verdict"], "DOOMED_AUTHORED_SUFFIX")
        self.assertEqual(result["watered_actor_indices"], [0])
        self.assertEqual(result["doomed_actor_indices"], [1])

    def test_build_coop_before_colocated_plant_fails_closed(self):
        obs = observation(hands=((1, 1),))
        selected = action(("BUILD_COOP",), hands=(("PLANT", "WHEAT"),))
        result = assess(obs, selected)
        self.assertEqual(result["verdict"], "NOT_CERTIFIED")
        self.assertEqual(result["reason"], "current_stage_tile_effect_ambiguity")
        self.assertEqual(result["doomed_actor_indices"], [])

    def test_build_pasture_before_colocated_plant_fails_closed(self):
        obs = observation(hands=((1, 1),))
        selected = action(("BUILD_PASTURE",), hands=(("PLANT", "WHEAT"),))
        result = assess(obs, selected)
        self.assertEqual(result["verdict"], "NOT_CERTIFIED")
        self.assertEqual(result["reason"], "current_stage_tile_effect_ambiguity")
        self.assertEqual(result["doomed_actor_indices"], [])

    def test_build_on_other_tile_does_not_hide_executable_plant(self):
        obs = observation(farmer=(0, 0), hands=((1, 1),))
        selected = action(("BUILD_COOP",), hands=(("PLANT", "WHEAT"),))
        result = assess(obs, selected)
        self.assertEqual(result["verdict"], "DOOMED_AUTHORED_SUFFIX")
        self.assertEqual(result["doomed_actor_indices"], [1])

    def test_hour_step_mismatch_fails_closed(self):
        result = assess(
            observation(hour=23, step=22), action(("PLANT", "WHEAT"))
        )
        self.assertEqual(result["verdict"], "NOT_CERTIFIED")
        self.assertEqual(result["reason"], "hour_step_mismatch")

    def test_step_type_poison_fails_closed(self):
        result = assess(
            observation(hour=23, step=True), action(("PLANT", "WHEAT"))
        )
        self.assertEqual(result["verdict"], "NOT_CERTIFIED")
        self.assertIn("step_must_be_int", result["reason"])

    def test_terminal_partial_day_unused_authored_row_cannot_certify(self):
        obs = observation(hour=22, step=718)
        selected = action(("PLANT", "WHEAT"))
        # Step 719/hour23 is nominally the next clock row, but the standard
        # 720-step interpreter never executes it or that day's EOD.
        result = assess(obs, selected, [action(("PASS",))])
        self.assertEqual(result["verdict"], "NOT_CERTIFIED")
        self.assertEqual(result["reason"], "eod_not_reachable_before_terminal")

    def test_last_real_eod_callback_can_still_certify(self):
        obs = observation(hour=23, step=695)
        result = assess(obs, action(("PLANT", "WHEAT")))
        self.assertEqual(result["verdict"], "DOOMED_AUTHORED_SUFFIX")
        self.assertEqual(result["doomed_actor_indices"], [0])

    def test_after_final_executable_callback_fails_closed(self):
        obs = observation(hour=23, step=719)
        result = assess(obs, action(("PLANT", "WHEAT")))
        self.assertEqual(result["verdict"], "NOT_CERTIFIED")
        self.assertEqual(
            result["reason"], "step_after_final_executable_callback"
        )

    def test_custom_episode_horizon_controls_eod_reachability(self):
        obs = observation(hour=22, step=46)
        result = assess(
            obs,
            action(("PLANT", "WHEAT")),
            [action(("PASS",))],
            {"episodeSteps": 48, "turnsPerDay": 24},
            config_authenticated=True,
        )
        self.assertEqual(result["verdict"], "NOT_CERTIFIED")
        self.assertEqual(result["reason"], "eod_not_reachable_before_terminal")

    def test_episode_steps_type_poison_fails_closed(self):
        result = assess(
            observation(),
            action(("PLANT", "WHEAT")),
            config={"episodeSteps": True},
            config_authenticated=True,
        )
        self.assertEqual(result["verdict"], "NOT_CERTIFIED")
        self.assertIn("episodeSteps_must_be_int", result["reason"])

    def test_custom_configuration_requires_authentication(self):
        result = assess(
            observation(),
            action(("PLANT", "WHEAT")),
            config={"episodeSteps": 720, "turnsPerDay": 24},
        )
        self.assertEqual(result["verdict"], "NOT_CERTIFIED")
        self.assertEqual(result["reason"], "configuration_not_authenticated")

    def test_authenticated_custom_configuration_can_use_exact_values(self):
        result = assess(
            observation(hour=23, step=47),
            action(("PLANT", "WHEAT")),
            config={"episodeSteps": 48, "turnsPerDay": 24},
            config_authenticated=True,
        )
        self.assertEqual(result["verdict"], "NOT_CERTIFIED")
        self.assertEqual(
            result["reason"], "step_after_final_executable_callback"
        )

    def test_same_callback_later_dig_removes_candidate(self):
        obs = observation(hands=((1, 1),))
        selected = action(("PLANT", "WHEAT"), hands=(("DIG",),))
        result = assess(obs, selected)
        self.assertEqual(result["verdict"], "NOT_CERTIFIED")
        self.assertEqual(result["reason"], "plant_removed_before_eod")
        self.assertEqual(result["removed_actor_indices"], [0])
        self.assertEqual(result["doomed_actor_indices"], [])

    def test_same_callback_dig_before_plant_is_noop(self):
        obs = observation(farmer=(1, 1), hands=((1, 1),))
        selected = action(("DIG",), hands=(("PLANT", "WHEAT"),))
        result = assess(obs, selected)
        self.assertEqual(result["verdict"], "DOOMED_AUTHORED_SUFFIX")
        self.assertEqual(result["doomed_actor_indices"], [1])
        self.assertEqual(result["removed_actor_indices"], [])

    def test_future_callback_dig_removes_candidate(self):
        obs = observation(hour=22)
        selected = action(("PLANT", "WHEAT"))
        result = assess(obs, selected, [action(("DIG",))])
        self.assertEqual(result["verdict"], "NOT_CERTIFIED")
        self.assertEqual(result["reason"], "plant_removed_before_eod")
        self.assertEqual(result["removed_actor_indices"], [0])

    def test_unrelated_future_dig_does_not_hide_doom(self):
        obs = observation(hour=22, farmer=(1, 1), hands=((0, 0),))
        selected = action(("PLANT", "WHEAT"), hands=(("PASS",),))
        suffix = [action(("PASS",), hands=(("DIG",),))]
        result = assess(obs, selected, suffix)
        self.assertEqual(result["verdict"], "DOOMED_AUTHORED_SUFFIX")
        self.assertEqual(result["doomed_actor_indices"], [0])
        self.assertEqual(result["removed_actor_indices"], [])

    def test_mixed_removed_and_unwatered_candidates_only_dooms_survivor(self):
        obs = observation(hour=22, farmer=(1, 1), hands=((2, 2),))
        selected = action(
            ("PLANT", "WHEAT"),
            hands=(("PLANT", "CARROT"),),
        )
        suffix = [action(("DIG",), hands=(("PASS",),))]
        result = assess(obs, selected, suffix)
        self.assertEqual(result["verdict"], "DOOMED_AUTHORED_SUFFIX")
        self.assertEqual(result["removed_actor_indices"], [0])
        self.assertEqual(result["doomed_actor_indices"], [1])

    def test_result_pins_engine_and_configuration_sources(self):
        result = assess(observation(), action(("PLANT", "WHEAT")))
        self.assertEqual(
            result["engine_git_blob"],
            "3c202c7ee921da239356789e266b694635103fc4",
        )
        self.assertEqual(
            result["configuration_git_blob"],
            "b354d06b742fe48402513792253f1a5c29366b20",
        )

    def test_inputs_are_not_mutated(self):
        obs = observation(hour=22, hands=((0, 1),))
        selected = action(("PLANT", "WHEAT"), hands=(("PASS",),))
        suffix = [action(("WATER",), hands=(("PASS",),))]
        before = copy.deepcopy((obs, selected, suffix))
        assess(obs, selected, suffix)
        self.assertEqual((obs, selected, suffix), before)


if __name__ == "__main__":
    unittest.main()
