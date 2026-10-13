#!/usr/bin/env python3
from __future__ import annotations

import unittest
from pathlib import Path

import unit_phase_chaining as upc


class UnitPhaseChainingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = upc.read_engine()
        cls.payload = upc.run_witnesses(cls.source)

    def test_interpreter_contract_is_farmer_then_hands_then_market(self):
        c = self.payload["interpreter_contract"]
        self.assertLess(c["farmer_statement_index"], c["hands_statement_index"])
        self.assertTrue(c["market_after_player_loop"])
        self.assertTrue(c["atomic_plant_preflight_pinned"])

    def test_dig_then_plant_is_order_sensitive(self):
        w = self.payload["witnesses"]["dig_then_plant"]
        self.assertEqual(w["forward"]["tile_0_0"]["kind"], "PLANT")
        self.assertEqual(w["forward"]["tile_0_0"]["crop"], "WHEAT")
        self.assertEqual(w["forward"]["seeds"]["WHEAT"], 0)
        self.assertIsNone(w["reverse"]["tile_0_0"])
        self.assertEqual(w["reverse"]["seeds"]["WHEAT"], 1)

    def test_harvest_then_replant_is_order_sensitive(self):
        w = self.payload["witnesses"]["harvest_then_plant"]
        self.assertEqual(w["forward"]["tile_0_0"]["kind"], "PLANT")
        self.assertEqual(w["forward"]["inventories"][0].get("WHEAT"), 3)
        self.assertIsNone(w["reverse"]["tile_0_0"])
        self.assertEqual(w["reverse"]["inventories"][1].get("WHEAT"), 3)

    def test_fertilize_then_water_exposes_written_bonus(self):
        w = self.payload["witnesses"]["fertilize_then_water"]
        self.assertEqual(w["forward"]["tile_0_0"]["yield_units"], 3)
        self.assertEqual(w["reverse"]["tile_0_0"]["yield_units"], 2)
        self.assertEqual(w["forward"]["tile_0_0"]["fertilized_until_day"], 5)
        self.assertEqual(w["reverse"]["tile_0_0"]["fertilized_until_day"], 5)

    def test_build_then_place_requires_late_actor_inventory(self):
        w = self.payload["witnesses"]["build_then_place"]
        self.assertEqual(w["forward"]["tile_0_0"]["animal"], "GOOSE")
        self.assertEqual(w["reverse"]["tile_0_0"], {"kind": "COOP"})
        self.assertEqual(w["forward"]["inventories"][1], {})
        self.assertEqual(w["reverse"]["inventories"][0].get("GOOSE"), 1)

    def test_distinct_tiles_do_not_form_tile_pipeline(self):
        w = self.payload["witnesses"]["distinct_tile_control"]
        self.assertIsNone(w["tile_0_0"])
        self.assertEqual(w["tile_1_0"], {"kind": "WEED"})
        self.assertEqual(w["seeds"]["WHEAT"], 1)

    def test_atomic_seed_preflight_still_blocks_all_same_crop_plants(self):
        w = self.payload["witnesses"]["atomic_seed_control"]
        self.assertEqual(w["filtered"], [["PASS"], ["PASS"]])

    def test_atomic_seed_filter_preserves_independent_crop(self):
        got = upc.atomic_plant_filter(
            [["PLANT", "WHEAT"], ["PLANT", "WHEAT"], ["PLANT", "CARROT"]],
            {"WHEAT": 1, "CARROT": 1},
        )
        self.assertEqual(got, [["PASS"], ["PASS"], ["PLANT", "CARROT"]])

    def test_hand_order_drift_is_rejected(self):
        mutated = self.source.replace(
            "for h_idx, hand_action in enumerate(hands_actions):",
            "for h_idx, hand_action in reversed(list(enumerate(hands_actions))):",
            1,
        )
        self.assertNotEqual(mutated, self.source)
        with self.assertRaisesRegex(AssertionError, "hand execution order drift"):
            upc.assert_interpreter_contract(mutated)

    def test_atomic_preflight_drift_is_rejected(self):
        mutated = self.source.replace(
            "n > seeds.get(crop, 0)",
            "n >= seeds.get(crop, 0)",
            1,
        )
        self.assertNotEqual(mutated, self.source)
        with self.assertRaisesRegex(AssertionError, "atomic PLANT preflight drift"):
            upc.assert_interpreter_contract(mutated)

    def test_engine_blob_drift_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "engine drift"):
            upc.read_engine(Path(__file__), expected_blob=upc.ENGINE_GIT_BLOB)

    def test_policy_boundary_is_explicitly_non_controller(self):
        b = self.payload["policy_boundary"]
        self.assertFalse(b["same_callback_market_credit"])
        self.assertFalse(b["cross_actor_inventory_transfer"])
        self.assertTrue(b["requires_actor_order"])
        self.assertTrue(b["atomic_plant_collateral_still_applies"])
        self.assertIn("UNASSESSED", self.payload["disposition"])


if __name__ == "__main__":
    unittest.main()
