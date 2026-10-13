#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import unittest
from pathlib import Path

import barnpipe_place_service as bp


class BarnpipePlaceServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = bp.upc.read_engine()
        cls.payload = bp.run_witnesses(cls.source)

    def test_engine_and_actor_order_are_source_bound(self):
        self.assertEqual(self.payload["engine_git_blob"], bp.ENGINE_GIT_BLOB)
        self.assertEqual(self.payload["unit_phase_chaining_git_blob"], bp.UNIT_CHAINING_GIT_BLOB)
        contract = self.payload["interpreter_contract"]
        self.assertLess(contract["farmer_statement_index"], contract["hands_statement_index"])
        self.assertTrue(contract["market_after_player_loop"])

    def test_chaining_dependency_blob_drift_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "unit-phase-chaining drift"):
            bp._load_upc_module(Path(__file__))

    def test_place_feed_care_succeeds_for_every_animal(self):
        for animal in bp.ANIMAL_ORDER:
            with self.subTest(animal=animal):
                w = self.payload["animals"][animal]["place_feed_care"]["forward"]
                tile = w["tile_0_0"]
                self.assertEqual(tile["animal"], animal)
                self.assertTrue(tile["fed_today"])
                self.assertTrue(tile["cared_today"])
                self.assertEqual(tile["pending_care_bonus"], 0)
                self.assertEqual(w["inventories"], [{}, {}, {}])

    def test_feed_before_place_is_a_noop_and_resource_stays_actor_local(self):
        for animal in bp.ANIMAL_ORDER:
            with self.subTest(animal=animal):
                w = self.payload["animals"][animal]["place_feed_care"]["feed_before_place"]
                tile = w["tile_0_0"]
                self.assertEqual(tile["animal"], animal)
                self.assertFalse(tile["fed_today"])
                self.assertTrue(tile["cared_today"])
                self.assertEqual(w["inventories"][0].get("WHEAT"), 1)

    def test_care_before_place_is_a_noop(self):
        for animal in bp.ANIMAL_ORDER:
            with self.subTest(animal=animal):
                w = self.payload["animals"][animal]["place_feed_care"]["care_before_place"]
                tile = w["tile_0_0"]
                self.assertEqual(tile["animal"], animal)
                self.assertTrue(tile["fed_today"])
                self.assertFalse(tile["cared_today"])

    def test_build_place_feed_care_succeeds_for_every_animal(self):
        for animal in bp.ANIMAL_ORDER:
            with self.subTest(animal=animal):
                family = self.payload["animals"][animal]["build_place_feed_care"]
                tile = family["forward"]["tile_0_0"]
                self.assertEqual(tile["kind"], family["structure"])
                self.assertEqual(tile["animal"], animal)
                self.assertTrue(tile["fed_today"])
                self.assertTrue(tile["cared_today"])
                self.assertEqual(family["forward"]["inventories"], [{}, {}, {}, {}])

    def test_place_before_build_does_not_retroactively_place(self):
        for animal in bp.ANIMAL_ORDER:
            with self.subTest(animal=animal):
                family = self.payload["animals"][animal]["build_place_feed_care"]
                w = family["place_before_build"]
                self.assertEqual(w["tile_0_0"], {"kind": family["structure"]})
                self.assertEqual(w["inventories"][0].get(animal), 1)
                self.assertEqual(w["inventories"][2].get("WHEAT"), 1)

    def test_place_requires_the_placing_actors_animal_inventory(self):
        for animal in bp.ANIMAL_ORDER:
            with self.subTest(animal=animal):
                family = self.payload["animals"][animal]
                w = family["custody_controls"]["wrong_animal_actor"]
                self.assertEqual(w["tile_0_0"], {"kind": family["place_feed_care"]["structure"]})
                self.assertEqual(w["inventories"][0].get(animal), 1)
                self.assertEqual(w["inventories"][2].get("WHEAT"), 1)

    def test_feed_requires_the_feeding_actors_wheat(self):
        for animal in bp.ANIMAL_ORDER:
            with self.subTest(animal=animal):
                w = self.payload["animals"][animal]["custody_controls"]["wrong_wheat_actor"]
                tile = w["tile_0_0"]
                self.assertEqual(tile["animal"], animal)
                self.assertFalse(tile["fed_today"])
                self.assertTrue(tile["cared_today"])
                self.assertEqual(w["inventories"][0].get("WHEAT"), 1)

    def test_wrong_structure_rejects_animal_placement(self):
        for animal in bp.ANIMAL_ORDER:
            with self.subTest(animal=animal):
                w = self.payload["animals"][animal]["custody_controls"]["wrong_structure"]
                self.assertNotIn("animal", w["tile_0_0"])
                self.assertEqual(w["inventories"][0].get(animal), 1)
                self.assertEqual(w["inventories"][1].get("WHEAT"), 1)

    def test_service_does_not_cross_tiles(self):
        for animal in bp.ANIMAL_ORDER:
            with self.subTest(animal=animal):
                family = self.payload["animals"][animal]
                w = family["custody_controls"]["distinct_tile"]
                placed = w["tile_0_0"]
                self.assertEqual(placed["animal"], animal)
                self.assertFalse(placed["fed_today"])
                self.assertFalse(placed["cared_today"])
                self.assertEqual(w["tile_1_0"], {"kind": family["place_feed_care"]["structure"]})
                self.assertEqual(w["inventories"][1].get("WHEAT"), 1)

    def test_placement_day_feed_and_care_banks_one_bonus_without_producing(self):
        for animal in bp.ANIMAL_ORDER:
            with self.subTest(animal=animal):
                w = self.payload["animals"][animal]["eod_bonus"]["with_placement_day_care"]
                before = w["before_placement_eod"]["tile_0_0"]
                after = w["after_placement_eod"]["tile_0_0"]
                self.assertEqual(before["yield_units"], 0)
                self.assertTrue(before["fed_today"])
                self.assertTrue(before["cared_today"])
                self.assertEqual(after["yield_units"], 0)
                self.assertEqual(after["pending_care_bonus"], 1)
                self.assertFalse(after["fed_today"])
                self.assertFalse(after["cared_today"])

    def test_placement_day_bonus_is_consumed_on_first_later_production(self):
        for animal in bp.ANIMAL_ORDER:
            with self.subTest(animal=animal):
                eod = self.payload["animals"][animal]["eod_bonus"]
                with_care = eod["with_placement_day_care"]["first_production"]["tile_0_0"]
                without = eod["without_placement_day_care"]["first_production"]["tile_0_0"]
                self.assertGreaterEqual(eod["first_yield_day"], 4)
                self.assertEqual(with_care["yield_units"], 2)
                self.assertEqual(without["yield_units"], 1)
                self.assertEqual(with_care["pending_care_bonus"], 0)
                self.assertEqual(without["pending_care_bonus"], 0)

    def test_policy_boundary_stays_research_only(self):
        b = self.payload["policy_boundary"]
        self.assertTrue(b["research_only"])
        self.assertTrue(b["requires_actor_order"])
        self.assertTrue(b["requires_shared_tile"])
        self.assertFalse(b["cross_actor_inventory_transfer"])
        self.assertFalse(b["placement_day_production_claimed"])
        self.assertFalse(b["runtime_activation_authority"])
        self.assertIn("UNASSESSED", self.payload["disposition"])

    def test_engine_blob_drift_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "engine drift"):
            bp.upc.read_engine(Path(__file__), expected_blob=bp.ENGINE_GIT_BLOB)


if __name__ == "__main__":
    unittest.main()
