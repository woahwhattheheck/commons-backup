# SPDX-License-Identifier: Apache-2.0
"""Pinned-engine predecessors plus conservative alternate-feed candidate tests."""
from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
EVALUATOR = ROOT / "reference/evaluator/evaluate.py"
ENGINE_DIR = ROOT / "reference/engine"
LOADER = ROOT / "reference/evaluator/loader.py"
_DEFAULT = object()

candidate_spec = importlib.util.spec_from_file_location("v5_animal_cadence", HERE / "alternate_feed.py")
candidate = importlib.util.module_from_spec(candidate_spec)
candidate_spec.loader.exec_module(candidate)


class AlternateFeedCandidateTests(unittest.TestCase):
    def setUp(self):
        self.tile = {
            "kind": "PASTURE",
            "animal": "COW",
            "placed_day": 0,
            "yield_units": 0,
            "consecutive_unfed": 0,
            "fed_today": False,
            "cared_today": False,
            "fertilizer_available": False,
            "pending_care_bonus": 0,
        }
        tiles = [[None for _ in range(10)] for _ in range(10)]
        tiles[4][4] = self.tile
        self.farm = {"farmer": [0, 0], "hands": [[4, 4]], "tiles": tiles}
        self.obs = {
            "player": 0,
            "step": 100,
            "farms": [self.farm, {}],
            "private": {"inventories": [{}, {"WHEAT": 2}]},
        }
        self.selected = {
            "farmer": ["PASS"],
            "hands": [["FEED"]],
            "market": [["SELL", "EGG", 1]],
        }
        self.turns_per_day = 24
        self.route_identity = {
            "route_id": "test-route",
            "route_source_git_blob": "a" * 40,
            "tail_sha256": "b" * 64,
        }
        self.certificate = {
            "schema": "titan-v5/animal-cadence/next-feed-certificate/v1",
            "observation_step": 100,
            "turns_per_day": 24,
            **self.route_identity,
            "feeds": [{"position": [4, 4], "next_feed_step": 120}],
        }

    def apply(self, certificate=_DEFAULT, route_identity=_DEFAULT, turns_per_day=_DEFAULT):
        cert = deepcopy(self.certificate) if certificate is _DEFAULT else certificate
        route = deepcopy(self.route_identity) if route_identity is _DEFAULT else route_identity
        calendar = self.turns_per_day if turns_per_day is _DEFAULT else turns_per_day
        return candidate.apply_alternate_feed(
            self.obs,
            self.selected,
            next_feed_certificate=cert,
            route_identity=route,
            turns_per_day=calendar,
        )

    def test_safe_zero_strike_feed_becomes_pass_without_other_edits(self):
        before = deepcopy((self.obs, self.selected))
        result, report = self.apply()
        self.assertEqual(result["hands"], [["PASS"]])
        self.assertEqual(result["farmer"], self.selected["farmer"])
        self.assertEqual(result["market"], self.selected["market"])
        self.assertTrue(report["changed"])
        self.assertEqual(report["feed_actions_suppressed"], 1)
        self.assertEqual(report["wheat_saved"], 1)
        self.assertEqual(report["edits"][0]["animal"], "COW")
        self.assertEqual(report["edits"][0]["certified_next_feed_step"], 120)
        self.assertEqual(report["certificate_provenance"]["observation_step"], 100)
        self.assertEqual(report["certificate_provenance"]["turns_per_day"], 24)
        self.assertEqual(report["certificate_provenance"]["next_day_start_step"], 120)
        self.assertEqual(report["certificate_provenance"]["next_day_end_step"], 143)
        self.assertEqual((self.obs, self.selected), before)

    def test_uncertified_next_feed_keeps_selected(self):
        result, report = self.apply(certificate=None)
        self.assertIs(result, self.selected)
        self.assertEqual(report["reason"], "next_feed_uncertified")

    def test_missing_or_malformed_route_identity_keeps_selected(self):
        for route in (None, {}, {"route_id": "test-route"}):
            with self.subTest(route=route):
                result, report = self.apply(route_identity=route)
                self.assertIs(result, self.selected)
                self.assertEqual(report["reason"], "malformed_route_identity")

    def test_turns_per_day_must_be_exact_positive_plain_int(self):
        for value in (None, True, 0, -1, 24.0, "24"):
            with self.subTest(value=value):
                result, report = self.apply(turns_per_day=value)
                self.assertIs(result, self.selected)
                self.assertEqual(report["reason"], "malformed_turns_per_day")

    def test_certificate_must_bind_exact_public_step(self):
        certificate = deepcopy(self.certificate)
        certificate["observation_step"] = 99
        result, report = self.apply(certificate=certificate)
        self.assertIs(result, self.selected)
        self.assertEqual(report["reason"], "next_feed_certificate_mismatch")

    def test_certificate_must_bind_exact_calendar(self):
        certificate = deepcopy(self.certificate)
        certificate["turns_per_day"] = 25
        result, report = self.apply(certificate=certificate)
        self.assertIs(result, self.selected)
        self.assertEqual(report["reason"], "next_feed_certificate_mismatch")

    def test_certificate_must_bind_current_route_source_and_tail(self):
        replacements = {
            "route_id": "other-route",
            "route_source_git_blob": "c" * 40,
            "tail_sha256": "d" * 64,
        }
        for key, value in replacements.items():
            with self.subTest(key=key):
                certificate = deepcopy(self.certificate)
                certificate[key] = value
                result, report = self.apply(certificate=certificate)
                self.assertIs(result, self.selected)
                self.assertEqual(report["reason"], "next_feed_certificate_mismatch")

    def test_certificate_rejects_bad_hashes_duplicate_tiles_and_wrong_day(self):
        cases = []
        route = deepcopy(self.route_identity)
        route["route_source_git_blob"] = "A" * 40
        cases.append((deepcopy(self.certificate), route, "malformed_route_identity"))
        for next_step in (119, 144):
            certificate = deepcopy(self.certificate)
            certificate["feeds"][0]["next_feed_step"] = next_step
            cases.append((certificate, deepcopy(self.route_identity), "malformed_next_feed_certificate"))
        certificate = deepcopy(self.certificate)
        certificate["feeds"].append({"position": [4, 4], "next_feed_step": 121})
        cases.append((certificate, deepcopy(self.route_identity), "malformed_next_feed_certificate"))
        for certificate, route_identity, reason in cases:
            with self.subTest(reason=reason):
                result, report = self.apply(certificate=certificate, route_identity=route_identity)
                self.assertIs(result, self.selected)
                self.assertEqual(report["reason"], reason)

    def test_certificate_for_another_tile_does_not_authorize_edit(self):
        certificate = deepcopy(self.certificate)
        certificate["feeds"] = [{"position": [3, 4], "next_feed_step": 120}]
        result, report = self.apply(certificate=certificate)
        self.assertIs(result, self.selected)
        self.assertFalse(report["changed"])

    def test_duplicate_feed_actions_save_one_wheat_per_unique_tile(self):
        self.farm["farmer"] = [4, 4]
        self.obs["private"]["inventories"][0]["WHEAT"] = 1
        self.selected["farmer"] = ["FEED"]
        result, report = self.apply()
        self.assertEqual(result["farmer"], ["PASS"])
        self.assertEqual(result["hands"], [["PASS"]])
        self.assertEqual(report["feed_actions_suppressed"], 2)
        self.assertEqual(report["wheat_saved"], 1)

    def test_one_strike_leg_keeps_feed(self):
        self.tile["consecutive_unfed"] = 1
        result, report = self.apply()
        self.assertIs(result, self.selected)
        self.assertFalse(report["changed"])

    def test_noncanonical_animal_state_fails_closed(self):
        for field, value in (("consecutive_unfed", False), ("pending_care_bonus", False)):
            with self.subTest(field=field):
                self.tile["consecutive_unfed"] = 0
                self.tile["pending_care_bonus"] = 0
                self.tile[field] = value
                result, report = self.apply()
                self.assertIs(result, self.selected)
                self.assertFalse(report["changed"])

    def test_missing_pending_care_state_fails_closed(self):
        del self.tile["pending_care_bonus"]
        result, report = self.apply()
        self.assertIs(result, self.selected)
        self.assertFalse(report["changed"])

    def test_malformed_inventory_fails_closed(self):
        self.obs["private"]["inventories"][0] = []
        result, report = self.apply()
        self.assertIs(result, self.selected)
        self.assertEqual(report["reason"], "malformed_inventories")

    def test_no_actual_wheat_spend_keeps_feed(self):
        self.obs["private"]["inventories"][1].clear()
        result, report = self.apply()
        self.assertIs(result, self.selected)
        self.assertFalse(report["changed"])

    def test_current_or_pending_care_value_keeps_feed(self):
        for field, value in (("cared_today", True), ("pending_care_bonus", 1)):
            with self.subTest(field=field):
                self.tile["cared_today"] = False
                self.tile["pending_care_bonus"] = 0
                self.tile[field] = value
                result, report = self.apply()
                self.assertIs(result, self.selected)
                self.assertFalse(report["changed"])

    def test_same_tile_selected_care_keeps_feed(self):
        self.farm["farmer"] = [4, 4]
        self.selected["farmer"] = ["CARE"]
        result, report = self.apply()
        self.assertIs(result, self.selected)
        self.assertFalse(report["changed"])

    def test_malformed_public_identity_fails_closed(self):
        for field, value in (("player", True), ("step", True), ("step", "100"), ("step", -1)):
            with self.subTest(field=field, value=value):
                self.obs["player"] = 0
                self.obs["step"] = 100
                self.obs[field] = value
                result, report = self.apply()
                self.assertIs(result, self.selected)
                self.assertEqual(report["reason"], "malformed_public_identity")


class PinnedEngineAnimalCadenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        evaluator_spec = importlib.util.spec_from_file_location("animal_cadence_evaluator", EVALUATOR)
        cls.ev = importlib.util.module_from_spec(evaluator_spec)
        evaluator_spec.loader.exec_module(cls.ev)
        cls.engine, cls.hashes = cls.ev.get_engine(ENGINE_DIR, LOADER)

    def goose(self):
        farm = self.engine._new_farm(10, 3000)
        farm["tiles"][0][0] = self.engine._new_animal("GOOSE", 0)
        return farm, farm["tiles"][0][0]

    def test_unfed_production_day_survives_and_still_produces(self):
        farm, tile = self.goose()
        self.engine._daily_refresh_animals(farm, 3)
        self.assertIs(farm["tiles"][0][0], tile)
        self.assertEqual(tile["consecutive_unfed"], 1)
        self.assertEqual(tile["yield_units"], 1)

    def test_pending_care_bonus_is_lost_on_first_unfed_production_refresh(self):
        unfed_farm, unfed = self.goose()
        unfed["pending_care_bonus"] = 1
        self.engine._daily_refresh_animals(unfed_farm, 3)
        self.assertEqual(unfed["yield_units"], 1)
        self.assertEqual(unfed["pending_care_bonus"], 0)

        fed_farm, fed = self.goose()
        fed["pending_care_bonus"] = 1
        fed["fed_today"] = True
        self.engine._daily_refresh_animals(fed_farm, 3)
        self.assertEqual(fed["yield_units"], 2)
        self.assertEqual(fed["pending_care_bonus"], 0)

    def test_second_consecutive_unfed_day_is_the_escape_boundary(self):
        farm, tile = self.goose()
        self.engine._daily_refresh_animals(farm, 3)
        self.assertIn("animal", farm["tiles"][0][0])
        self.engine._daily_refresh_animals(farm, 4)
        self.assertEqual(farm["tiles"][0][0], {"kind": "COOP"})

    def test_alternate_day_feed_preserves_daily_goose_base_yield(self):
        farm, tile = self.goose()
        self.engine._daily_refresh_animals(farm, 3)
        self.assertEqual((tile["consecutive_unfed"], tile["yield_units"]), (1, 1))
        tile["fed_today"] = True
        self.engine._daily_refresh_animals(farm, 4)
        self.assertEqual((tile["consecutive_unfed"], tile["yield_units"]), (0, 2))

    def test_duplicate_feed_actions_spend_one_wheat_per_animal_tile(self):
        farm, tile = self.goose()
        farm["farmer"] = [0, 0]
        farm["hands"] = [[0, 0]]
        private = self.engine._new_private()
        private["inventories"] = [{"WHEAT": 1}, {"WHEAT": 1}]
        self.engine._apply_unit_action(farm, private, 0, ["FEED"], 10, 0, 24, 100)
        self.engine._apply_unit_action(farm, private, 1, ["FEED"], 10, 0, 24, 100)
        self.assertTrue(tile["fed_today"])
        self.assertNotIn("WHEAT", private["inventories"][0])
        self.assertEqual(private["inventories"][1].get("WHEAT"), 1)

    def test_surviving_animal_refreshes_fertilizer_every_day(self):
        farm, tile = self.goose()
        tile["fed_today"] = True
        self.engine._daily_refresh_animals(farm, 0)
        self.assertTrue(tile["fertilizer_available"])
        tile["fertilizer_available"] = False  # model a successful collection
        tile["fed_today"] = True
        self.engine._daily_refresh_animals(farm, 1)
        self.assertTrue(tile["fertilizer_available"])

    def test_fertilize_extends_bonus_window_but_does_not_mint_yield(self):
        farm = self.engine._new_farm(10, 3000)
        farm["farmer"] = [0, 0]
        farm["tiles"][0][0] = self.engine._new_plant("MELON", 0, 24)
        private = self.engine._new_private()
        private["inventories"][0]["FERTILIZER"] = 1
        tile = farm["tiles"][0][0]
        before = tile["yield_units"]
        self.engine._apply_unit_action(farm, private, 0, ["FERTILIZE"], 10, 1, 24)
        self.assertEqual(tile["yield_units"], before)
        self.assertEqual(tile["fertilized_until_day"], 3)
        self.assertNotIn("FERTILIZER", private["inventories"][0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
