# SPDX-License-Identifier: Apache-2.0
"""Focused predecessors for the source-pinned day-close cadence authority."""
from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = _load("v5_cadence_certificate_builder", HERE / "certificate_builder.py")
candidate = _load("v5_cadence_candidate", HERE / "alternate_feed.py")


class Controller:
    def __init__(self, route_id, route):
        self.cur = route_id
        self.R = {route_id: route}


class CadenceCertificateBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = builder._lab_root()
        cls.mechanics = builder._load("v5_cadence_test_mechanics", root / "mechanics.py")
        cls.producer = builder._load(
            "v5_cadence_test_producer", root / "reference/next-panel/vendor/arlene.py")
        cls.route_id = cls.producer.MAIN
        cls.source_route = cls.producer.routes()[cls.route_id]
        cls.spawn = tuple(cls.mechanics._default_spawn(10))

    def setUp(self):
        self.step = 23
        self.cfg = {
            "turnsPerDay": 24,
            "episodeSteps": 720,
            "boardSize": 10,
            "shedCapacity": 100,
            "maxMarketOrdersPerTurn": 10,
            "farmHandCostMult": 1,
        }
        self.features = {
            "consumer": "frozen",
            "seed": True,
            "funding": True,
            "redundant_hire": True,
            "terminal_route": False,
            "committed": True,
            "terminal_history": False,
            "spatial_pathing": False,
            "spatial_tempo": False,
            "fourth_quadrant": False,
            "market_pressure": True,
            "committed_seed_retry": False,
            "operating_stock": True,
            "idle_fertilizer": True,
            "crop_release": True,
            "early_capital": True,
            "town_procurement": True,
            "exec_pace": False,
        }
        x, y = self.spawn
        tiles = [[None for _ in range(10)] for _ in range(10)]
        tiles[y][x] = {
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
        farm = {
            "farmer": list(self.spawn),
            "hands": [],
            "tiles": tiles,
            "money": 10000,
            "hires_today": 0,
            "unlocked_quadrants": ["NW"],
        }
        self.obs = {
            "player": 0,
            "step": self.step,
            "day": 0,
            "hour": 23,
            "farms": [farm, deepcopy(farm)],
            "private": {
                "shed": {},
                "inventories": [{"WHEAT": 1}],
                "seeds": {},
            },
            "market": {
                "inventory": {item: 10000 for item in self.mechanics.PRODUCTS},
                "params": None,
            },
        }
        self.selected = {"farmer": ["FEED"], "hands": [], "market": []}
        self.route = deepcopy(self.source_route)
        self._blank_day(24)
        self.route[24] = {"farmer": ["PICKUP", "WHEAT", 1], "hands": [], "market": []}
        self.route[25] = {"farmer": ["FEED"], "hands": [], "market": []}
        self.controller = Controller(self.route_id, self.route)

    def _blank_day(self, start):
        for step in range(start, start + 24):
            self.route[step] = {"farmer": ["PASS"], "hands": [], "market": []}

    def build(self, *, completed=True):
        return builder.build_next_feed_certificate(
            self.obs, self.selected, self.cfg, self.controller, self.features,
            completed=completed)

    def test_day_close_saved_wheat_round_trip_is_certified(self):
        route_identity, certificate, report = self.build()
        self.assertTrue(report["certified"], report)
        self.assertEqual(report["reason"], "day_close_saved_wheat_reclaimed_before_next_day_market")
        self.assertEqual(certificate["observation_step"], 23)
        self.assertEqual(certificate["turns_per_day"], 24)
        self.assertEqual(certificate["feeds"], [{"position": list(self.spawn), "next_feed_step": 25}])
        self.assertEqual(report["proof"]["pickup_step"], 24)
        self.assertEqual(report["proof"]["pickup_actor"], 0)
        self.assertEqual(report["proof"]["returned_wheat_before_eod"], 1)
        self.assertGreaterEqual(report["proof"]["protected_wheat_available"], 1)
        transformed, consume = candidate.apply_alternate_feed(
            self.obs,
            self.selected,
            next_feed_certificate=certificate,
            route_identity=route_identity,
            turns_per_day=24,
        )
        self.assertTrue(consume["changed"])
        self.assertEqual(transformed["farmer"], ["PASS"])
        self.assertEqual(transformed["market"], self.selected["market"])

    def test_source_custody_report_contains_every_pinned_blob(self):
        _, _, report = self.build()
        self.assertTrue(report["certified"], report)
        self.assertEqual(report["source_pins"], builder._SOURCE_PINS)
        self.assertEqual(
            report["source_pins"]["reference/engine/kaggriculture.py"],
            builder.OFFICIAL_ENGINE_GIT_BLOB,
        )
        self.assertEqual(
            report["source_pins"]["titan_runtime.py"], builder.RUNTIME_GIT_BLOB)
        self.assertEqual(
            report["source_pins"]["TITAN-CONFIG.json"], builder.CONFIG_GIT_BLOB)
        self.assertEqual(
            report["source_pins"]["frozen_selected.py"], builder.FROZEN_SELECTED_GIT_BLOB)
        self.assertEqual(
            report["source_pins"]["exec_pace_runtime.py"], builder.EXEC_PACE_RUNTIME_GIT_BLOB)
        self.assertEqual(
            report["source_pins"]["reference/titan-current/redundant_hire.py"],
            builder.REDUNDANT_HIRE_GIT_BLOB,
        )

    def test_deadline_or_other_noncompleted_action_is_never_certified(self):
        original = builder._lab_root

        def forbidden_root():
            raise AssertionError("noncompleted action reached source loading")

        builder._lab_root = forbidden_root
        try:
            route_identity, certificate, report = self.build(completed=False)
        finally:
            builder._lab_root = original
        self.assertIsNone(route_identity)
        self.assertIsNone(certificate)
        self.assertEqual(report["reason"], "runtime_action_not_completed")

    def test_exact_current_wrapper_profile_is_required(self):
        cases = (
            ("seed", False),
            ("funding", False),
            ("redundant_hire", False),
            ("market_pressure", False),
            ("early_capital", False),
            ("town_procurement", False),
            ("committed_seed_retry", True),
            ("exec_pace", True),
        )
        for field, value in cases:
            with self.subTest(field=field, value=value):
                original = self.features[field]
                self.features[field] = value
                try:
                    route_identity, certificate, report = self.build()
                finally:
                    self.features[field] = original
                self.assertIsNone(route_identity)
                self.assertIsNone(certificate)
                self.assertEqual(report["reason"], f"unsupported_feature_profile:{field}")

    def test_next_day_hire_surface_is_rejected_before_feed_proof(self):
        self.route[24]["market"] = [["HIRE"]]
        route_identity, certificate, report = self.build()
        self.assertIsNone(route_identity)
        self.assertIsNone(certificate)
        self.assertEqual(report["reason"], "next_day_has_dynamic_hire_surface")

    def test_route_identity_binds_entire_live_tail(self):
        first_identity, _, first = self.build()
        self.assertTrue(first["certified"], first)
        self.route[100] = {"farmer": ["PASS"], "hands": [], "market": [["SELL", "EGG", 1]]}
        second_identity, _, second = self.build()
        self.assertTrue(second["certified"], second)
        self.assertNotEqual(first_identity["tail_sha256"], second_identity["tail_sha256"])
        self.assertEqual(first_identity["route_source_git_blob"], builder.PRODUCER_GIT_BLOB)
        self.assertEqual(second_identity["route_source_git_blob"], builder.PRODUCER_GIT_BLOB)

    def test_public_clock_mismatch_fails_before_module_load(self):
        self.obs["day"] = 1
        original = builder._load

        def forbidden_load(*_args, **_kwargs):
            raise AssertionError("clock mismatch reached dynamic module load")

        builder._load = forbidden_load
        try:
            route_identity, certificate, report = self.build()
        finally:
            builder._load = original
        self.assertIsNone(route_identity)
        self.assertIsNone(certificate)
        self.assertEqual(report["reason"], "public_clock_mismatch")

    def test_partial_public_clock_fails_closed(self):
        for missing in ("day", "hour"):
            with self.subTest(missing=missing):
                saved = self.obs.pop(missing)
                try:
                    route_identity, certificate, report = self.build()
                finally:
                    self.obs[missing] = saved
                self.assertIsNone(route_identity)
                self.assertIsNone(certificate)
                self.assertEqual(report["reason"], "malformed_public_clock")

    def test_public_clock_fields_are_exact_plain_bounded_ints(self):
        cases = (
            ("day", True),
            ("day", -1),
            ("hour", True),
            ("hour", -1),
            ("hour", 24),
        )
        for field, value in cases:
            with self.subTest(field=field, value=value):
                original = self.obs[field]
                self.obs[field] = value
                try:
                    route_identity, certificate, report = self.build()
                finally:
                    self.obs[field] = original
                self.assertIsNone(route_identity)
                self.assertIsNone(certificate)
                self.assertEqual(report["reason"], "malformed_public_clock")

    def test_redundant_public_clock_may_be_fully_absent(self):
        day = self.obs.pop("day")
        hour = self.obs.pop("hour")
        try:
            route_identity, certificate, report = self.build()
        finally:
            self.obs["day"] = day
            self.obs["hour"] = hour
        self.assertIsNotNone(route_identity, report)
        self.assertIsNotNone(certificate, report)
        self.assertTrue(report["certified"], report)

    def test_non_day_close_never_mints_certificate(self):
        self.obs["step"] = 22
        self.obs["hour"] = 22
        route_identity, certificate, report = self.build()
        self.assertIsNone(route_identity)
        self.assertIsNone(certificate)
        self.assertEqual(report["reason"], "not_day_close")

    def test_next_day_route_checkpoint_fails_closed(self):
        # 215 is day close and the pinned producer has a decision at 226.
        self.obs["step"] = 215
        self.obs["day"] = 8
        self.obs["hour"] = 23
        self.route = deepcopy(self.source_route)
        self._blank_day(216)
        self.route[216] = {"farmer": ["PICKUP", "WHEAT", 1], "hands": [], "market": []}
        self.route[217] = {"farmer": ["FEED"], "hands": [], "market": []}
        self.controller = Controller(self.route_id, self.route)
        route_identity, certificate, report = self.build()
        self.assertIsNone(route_identity)
        self.assertIsNone(certificate)
        self.assertEqual(report["reason"], "next_day_crosses_route_checkpoint")

    def test_pickup_after_first_next_day_unit_stage_is_not_enough(self):
        self.route[24] = {"farmer": ["PASS"], "hands": [], "market": []}
        self.route[25] = {"farmer": ["PICKUP", "WHEAT", 1], "hands": [], "market": []}
        self.route[26] = {"farmer": ["FEED"], "hands": [], "market": []}
        _, certificate, report = self.build()
        self.assertIsNone(certificate)
        self.assertEqual(report["reason"], "no_certifiable_current_feed")
        self.assertTrue(any(
            failure["reason"] == "no_first_stage_pickup_for_same_tile_feed"
            for failure in report["failures"]
        ))

    def test_feed_without_protected_pickup_is_rejected(self):
        self.route[24] = {"farmer": ["PASS"], "hands": [], "market": []}
        _, certificate, report = self.build()
        self.assertIsNone(certificate)
        self.assertEqual(report["reason"], "no_certifiable_current_feed")
        self.assertTrue(any(
            failure["reason"] == "scheduled_feed_has_uncovered_carried_input"
            for failure in report["failures"]
        ))

    def test_full_shed_cannot_discard_the_saved_wheat_at_reset(self):
        self.obs["private"]["shed"] = {"EGG": 100}
        _, certificate, report = self.build()
        self.assertIsNone(certificate)
        self.assertEqual(report["reason"], "no_certifiable_current_feed")
        self.assertTrue(any(
            "reset_delivery" in failure["reason"]
            for failure in report["failures"]
        ))

    def test_current_market_can_free_exact_room_before_reset(self):
        self.obs["private"]["shed"] = {"EGG": 100}
        self.selected["market"] = [["SELL", "EGG", 1]]
        _, certificate, report = self.build()
        self.assertIsNotNone(certificate, report)
        self.assertTrue(report["certified"], report)
        self.assertEqual(report["proof"]["room"]["after_delivery_upper"], 100)

    def test_pathing_or_tempo_profile_cannot_reuse_current_theorem(self):
        for field in ("spatial_pathing", "spatial_tempo"):
            with self.subTest(field=field):
                self.features[field] = True
                _, certificate, report = self.build()
                self.assertIsNone(certificate)
                self.assertEqual(report["reason"], f"unsupported_feature_profile:{field}")
                self.features[field] = False

    def test_operating_stock_guard_is_part_of_feature_custody(self):
        self.features["operating_stock"] = False
        _, certificate, report = self.build()
        self.assertIsNone(certificate)
        self.assertEqual(report["reason"], "unsupported_feature_profile:operating_stock")

    def test_noncanonical_bool_calendar_is_rejected(self):
        self.cfg["turnsPerDay"] = True
        _, certificate, report = self.build()
        self.assertIsNone(certificate)
        self.assertEqual(report["reason"], "unsupported_configuration:turnsPerDay")

    def test_live_route_must_retain_pinned_source_lineage(self):
        self.route[0] = {"farmer": ["PASS"], "hands": [], "market": []}
        _, certificate, report = self.build()
        self.assertIsNone(certificate)
        self.assertEqual(report["reason"], "live_route_lineage_mismatch")

    def test_same_tile_requirement_rejects_a_different_feed_site(self):
        x, y = self.spawn
        other = (x + 1, y) if x + 1 < 10 else (x - 1, y)
        self.route[25] = {"farmer": ["EAST" if other[0] > x else "WEST"], "hands": [], "market": []}
        self.route[26] = {"farmer": ["FEED"], "hands": [], "market": []}
        _, certificate, report = self.build()
        self.assertIsNone(certificate)
        self.assertEqual(report["reason"], "no_certifiable_current_feed")


if __name__ == "__main__":
    unittest.main(verbosity=2)
