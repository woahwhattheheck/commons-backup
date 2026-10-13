# SPDX-License-Identifier: Apache-2.0
from copy import deepcopy
from pathlib import Path
import hashlib
import importlib.util
import unittest

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "ongoing_water_skip.py"
spec = importlib.util.spec_from_file_location("ongoing_water_skip", SOURCE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def _engine_path():
    for parent in HERE.parents:
        candidate = parent / "reference" / "engine" / "kaggriculture.py"
        if candidate.is_file():
            return candidate
    return None


def _git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def tile(crop="TOMATO", *, planted_day=0, streak=0, watered=False, units=0, fertilized=-1):
    return {
        "kind": "PLANT", "crop": crop, "planted_day": planted_day,
        "watered_today": watered, "consecutive_unwatered": streak,
        "yield_units": units, "max_lifespan_step": -1,
        "fertilized_until_day": fertilized,
    }


def fixture(*, day=3, crop="TOMATO", planted_day=0, streak=0, fertilized=-1, units=0):
    tiles = [[None for _ in range(10)] for _ in range(10)]
    tiles[0][0] = tile(crop, planted_day=planted_day, streak=streak,
                       fertilized=fertilized, units=units)
    farm = {"tiles": tiles, "farmer": [0, 0], "hands": []}
    obs = {"step": day * 24 + 5, "player": 0, "farms": [farm, deepcopy(farm)]}
    action = {"farmer": ["WATER"], "hands": [], "market": []}
    cfg = {"boardSize": 10, "turnsPerDay": 24, "episodeSteps": 720}
    return action, obs, cfg


class HydrationGuardTests(unittest.TestCase):
    def test_off_is_object_identity(self):
        action, obs, cfg = fixture()
        self.assertIs(mod.apply_ongoing_water_skip(action, obs, cfg), action)

    def test_established_tomato_skip(self):
        action, obs, cfg = fixture(day=3)
        self.assertEqual(len(mod.plan_ongoing_water_skip(action, obs, cfg)), 1)
        self.assertEqual(mod.apply_ongoing_water_skip(action, obs, cfg, enabled=True)["farmer"], ["PASS"])
        self.assertEqual(action["farmer"], ["WATER"])

    def test_established_strawberry_skip(self):
        action, obs, cfg = fixture(day=4, crop="STRAWBERRY")
        self.assertEqual(len(mod.plan_ongoing_water_skip(action, obs, cfg)), 1)

    def test_planting_day_is_mandatory_water(self):
        action, obs, cfg = fixture(day=3, planted_day=3, streak=1)
        self.assertEqual(mod.plan_ongoing_water_skip(action, obs, cfg), [])

    def test_prior_skip_makes_next_water_mandatory(self):
        action, obs, cfg = fixture(day=3, streak=1)
        self.assertEqual(mod.plan_ongoing_water_skip(action, obs, cfg), [])

    def test_nonongoing_crop_is_not_owned(self):
        action, obs, cfg = fixture(day=3)
        obs["farms"][0]["tiles"][0][0]["crop"] = "WHEAT"
        self.assertEqual(mod.plan_ongoing_water_skip(action, obs, cfg), [])

    def test_current_fertilizer_bonus_blocks_tomato_production_day(self):
        action, obs, cfg = fixture(day=7, crop="TOMATO", fertilized=7)
        plant = obs["farms"][0]["tiles"][0][0]
        self.assertTrue(mod._production_due(plant, 7, mod.CROPS["TOMATO"]))
        self.assertEqual(mod.plan_ongoing_water_skip(action, obs, cfg), [])

    def test_fertilized_strawberry_nonproduction_day_can_skip(self):
        action, obs, cfg = fixture(day=10, crop="STRAWBERRY", fertilized=10)
        plant = obs["farms"][0]["tiles"][0][0]
        self.assertFalse(mod._production_due(plant, 10, mod.CROPS["STRAWBERRY"]))
        self.assertEqual(len(mod.plan_ongoing_water_skip(action, obs, cfg)), 1)

    def test_saturated_yield_makes_fertilizer_bonus_valueless(self):
        action, obs, cfg = fixture(day=7, crop="TOMATO", fertilized=7, units=4)
        self.assertEqual(len(mod.plan_ongoing_water_skip(action, obs, cfg)), 1)

    def test_already_watered_is_not_rewritten(self):
        action, obs, cfg = fixture(day=3)
        obs["farms"][0]["tiles"][0][0]["watered_today"] = True
        self.assertEqual(mod.plan_ongoing_water_skip(action, obs, cfg), [])

    def test_duplicate_same_site_water_is_left_to_existing_dedupe_surfaces(self):
        action, obs, cfg = fixture(day=3)
        obs["farms"][0]["hands"] = [[0, 0]]
        action["hands"] = [["WATER"]]
        self.assertEqual(mod.plan_ongoing_water_skip(action, obs, cfg), [])

    def test_empty_visible_tile_preserves_same_turn_plant_water(self):
        action, obs, cfg = fixture(day=3)
        obs["farms"][0]["tiles"][0][0] = None
        self.assertEqual(mod.plan_ongoing_water_skip(action, obs, cfg), [])

    def test_nonstandard_engine_configuration_fails_closed(self):
        action, obs, cfg = fixture(day=3)
        cfg["turnsPerDay"] = 12
        self.assertEqual(mod.plan_ongoing_water_skip(action, obs, cfg), [])

    def test_malformed_tile_fails_closed(self):
        action, obs, cfg = fixture(day=3)
        obs["farms"][0]["tiles"][0][0]["consecutive_unwatered"] = "0"
        self.assertEqual(mod.plan_ongoing_water_skip(action, obs, cfg), [])

    def test_inputs_not_mutated(self):
        action, obs, cfg = fixture(day=3)
        before = deepcopy((action, obs, cfg))
        mod.apply_ongoing_water_skip(action, obs, cfg, enabled=True)
        self.assertEqual((action, obs, cfg), before)

    def test_pinned_engine_blob_and_required_mechanics(self):
        engine = _engine_path()
        if engine is None:
            self.skipTest("reference engine unavailable outside repository checkout")
        data = engine.read_bytes()
        self.assertEqual(_git_blob(data), mod.PINNED_ENGINE_BLOB)
        text = data.decode()
        self.assertIn('"consecutive_unwatered": 1,  # planting day counts as unwatered', text)
        self.assertIn('if tile["consecutive_unwatered"] >= 2:', text)
        self.assertIn('fertilized = was_watered and tile.get("fertilized_until_day", -1) >= current_day', text)


if __name__ == "__main__":
    unittest.main()
