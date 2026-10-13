#!/usr/bin/env python3
import unittest

import demand_velocity as d


class DemandVelocityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.panel = d.panel_absorption()

    def test_antigravity_per_shop_ratios_are_source_exact(self):
        self.assertEqual(d.per_shop_instance_velocity(), {
            "WHEAT": 0.625,
            "CARROT": 0.375,
            "TOMATO": 0.25,
            "STRAWBERRY": 0.5,
            "MELON": 0.0,
            "EGG": 0.25,
            "MILK": 0.375,
            "WOOL": 0.25,
            "FERTILIZER": 0.0,
        })

    def test_closed_form_adds_unlock_horizon_and_town_center(self):
        self.assertEqual(d.unlock_days(), (3, 6, 9, 12, 15, 18, 21, 24))
        self.assertEqual(d.closed_form_expected_depletion(), {
            "WHEAT": 525.0,
            "CARROT": 327.0,
            "TOMATO": 228.0,
            "STRAWBERRY": 426.0,
            "MELON": 30.0,
            "EGG": 228.0,
            "MILK": 327.0,
            "WOOL": 228.0,
            "FERTILIZER": 0.0,
        })

    def test_100_seed_means_match_existing_baseline_receipt(self):
        expected = {
            "WHEAT": 536.16,
            "CARROT": 363.18,
            "TOMATO": 231.96,
            "STRAWBERRY": 393.60,
            "MELON": 30.0,
            "EGG": 240.42,
            "MILK": 303.24,
            "WOOL": 217.20,
            "FERTILIZER": 0.0,
        }
        for item, value in expected.items():
            with self.subTest(item=item):
                self.assertAlmostEqual(self.panel[item]["mean"], value, places=8)

    def test_p10_exposes_tail_risk_hidden_by_mean_velocity(self):
        expected_p10 = {
            "WHEAT": 354.0,
            "CARROT": 30.0,
            "TOMATO": 66.0,
            "STRAWBERRY": 174.0,
            "MELON": 30.0,
            "EGG": 84.0,
            "MILK": 100.2,
            "WOOL": 30.0,
            "FERTILIZER": 0.0,
        }
        for item, value in expected_p10.items():
            with self.subTest(item=item):
                self.assertAlmostEqual(self.panel[item]["p10"], value, places=8)

    def test_headroom_is_not_decision_or_timing_authority(self):
        within = d.conservative_headroom("WHEAT", 354)
        over = d.conservative_headroom("WHEAT", 355)
        self.assertEqual(within["disposition"], "PANEL_NPC_HEADROOM_NOT_EXCEEDED")
        self.assertEqual(over["disposition"], "PANEL_NPC_HEADROOM_EXCEEDED")
        for result in (within, over):
            self.assertFalse(result["decision_authority"])
            self.assertFalse(result["timing_authority"])
            self.assertFalse(result["opponent_supply_accounted"])

    def test_fertilizer_has_zero_npc_absorption(self):
        self.assertEqual(d.conservative_headroom("FERTILIZER", 0)["npc_absorption_budget_units"], 0)
        self.assertEqual(
            d.conservative_headroom("FERTILIZER", 1)["disposition"],
            "PANEL_NPC_HEADROOM_EXCEEDED",
        )

    def test_full_horizon_window_matches_legacy_terminal_panel(self):
        seeds = (1, 2, 3)
        legacy = d.panel_absorption(seeds)["WHEAT"]
        window = d.panel_absorption_window("WHEAT", 0, 718, seeds)
        for key in ("min", "p10", "median", "mean", "p90", "max", "p10_floor_units"):
            with self.subTest(key=key):
                self.assertEqual(window[key], legacy[key])
        self.assertEqual(window["inclusive_callback_count"], 719)

    def test_window_custody_is_exact_at_step_zero_and_preunlock_quiet_steps(self):
        center = d.panel_absorption_window("WHEAT", 0, 0, (1,))
        fert = d.panel_absorption_window("FERTILIZER", 0, 0, (1,))
        quiet = d.panel_absorption_window("WHEAT", 1, 3, (1,))
        self.assertEqual(center["p10_floor_units"], 1)
        self.assertEqual(center["mean"], 1.0)
        self.assertEqual(fert["p10_floor_units"], 0)
        self.assertEqual(quiet["p10_floor_units"], 0)
        self.assertEqual(quiet["mean"], 0.0)

    def test_public_rival_stress_consumes_only_same_horizon_budget(self):
        no_candidate = d.horizon_public_pressure_headroom(
            "WHEAT", 0, 1,
            start_step=0, end_step=0,
            public_evidence_start_step=0, public_evidence_end_step=0,
            seeds=(1,)
        )
        candidate = d.horizon_public_pressure_headroom(
            "WHEAT", 1, 1,
            start_step=0, end_step=0,
            public_evidence_start_step=0, public_evidence_end_step=0,
            seeds=(1,)
        )
        self.assertEqual(no_candidate["npc_absorption_budget_units"], 1)
        self.assertEqual(no_candidate["residual_npc_headroom_after_public_rival_stress_units"], 0)
        self.assertEqual(
            no_candidate["disposition"],
            "HORIZON_PUBLIC_PRESSURE_HEADROOM_NOT_EXCEEDED",
        )
        self.assertEqual(candidate["public_competing_supply_stress_units"], 2)
        self.assertFalse(candidate["candidate_added_supply_fits_residual"])
        self.assertEqual(
            candidate["disposition"],
            "HORIZON_PUBLIC_PRESSURE_HEADROOM_EXCEEDED",
        )

    def test_rival_stress_can_exceed_budget_even_with_zero_candidate_supply(self):
        got = d.horizon_public_pressure_headroom(
            "FERTILIZER", 0, 1,
            start_step=0, end_step=0,
            public_evidence_start_step=0, public_evidence_end_step=0,
            seeds=(1,)
        )
        self.assertEqual(got["npc_absorption_budget_units"], 0)
        self.assertEqual(got["public_competing_supply_stress_units"], 1)
        self.assertEqual(
            got["disposition"],
            "HORIZON_PUBLIC_PRESSURE_HEADROOM_EXCEEDED",
        )

    def test_full_horizon_rival_zero_reduces_to_legacy_headroom(self):
        seeds = (1, 2, 3)
        legacy = d.conservative_headroom("WHEAT", 40, seeds=seeds)
        aligned = d.horizon_public_pressure_headroom(
            "WHEAT", 40, 0,
            start_step=0, end_step=718,
            public_evidence_start_step=0, public_evidence_end_step=718,
            seeds=seeds
        )
        self.assertEqual(
            aligned["npc_absorption_budget_units"],
            legacy["npc_absorption_budget_units"],
        )
        self.assertEqual(
            aligned["candidate_added_supply_fits_residual"],
            legacy["disposition"] == "PANEL_NPC_HEADROOM_NOT_EXCEEDED",
        )

    def test_horizon_pressure_report_is_non_authoritative_stress_not_prediction(self):
        got = d.horizon_public_pressure_headroom(
            "WOOL", 1, 2,
            start_step=0, end_step=0,
            public_evidence_start_step=0, public_evidence_end_step=0,
            seeds=(1,)
        )
        self.assertFalse(got["decision_authority"])
        self.assertFalse(got["timing_authority"])
        self.assertTrue(got["opponent_public_standing_supply_stress_accounted"])
        self.assertFalse(got["opponent_private_supply_accounted"])
        self.assertFalse(got["rival_sale_prediction"])
        self.assertIn("stress evidence", got["limitations"][0])

    def test_public_rival_evidence_window_must_match_budget_custody(self):
        with self.assertRaises(ValueError):
            d.horizon_public_pressure_headroom(
                "WHEAT", 0, 1,
                start_step=24, end_step=47,
                public_evidence_start_step=0, public_evidence_end_step=23,
                seeds=(1,),
            )

    def test_horizon_bad_inputs_fail_closed(self):
        with self.assertRaises(ValueError):
            d.panel_absorption_window("NOPE", 0, 0, (1,))
        with self.assertRaises(TypeError):
            d.panel_absorption_window("WHEAT", True, 0, (1,))
        with self.assertRaises(ValueError):
            d.panel_absorption_window("WHEAT", 0, 719, (1,))
        with self.assertRaises(ValueError):
            d.panel_absorption_window("WHEAT", 3, 2, (1,))
        with self.assertRaises(ValueError):
            d.panel_absorption_window("WHEAT", 0, 0, ())
        with self.assertRaises(TypeError):
            d.horizon_public_pressure_headroom(
                "WHEAT", True, 0,
                start_step=0, end_step=0,
                public_evidence_start_step=0, public_evidence_end_step=0,
                seeds=(1,)
            )
        with self.assertRaises(TypeError):
            d.horizon_public_pressure_headroom(
                "WHEAT", 0, True,
                start_step=0, end_step=0,
                public_evidence_start_step=0, public_evidence_end_step=0,
                seeds=(1,)
            )
        with self.assertRaises(ValueError):
            d.horizon_public_pressure_headroom(
                "WHEAT", 0, 0,
                start_step=0, end_step=0,
                public_evidence_start_step=0, public_evidence_end_step=0,
                q=1.1, seeds=(1,)
            )

    def test_bad_inputs_fail_closed(self):
        with self.assertRaises(ValueError):
            d.conservative_headroom("NOPE", 1)
        with self.assertRaises(TypeError):
            d.conservative_headroom("WHEAT", True)
        with self.assertRaises(ValueError):
            d.conservative_headroom("WHEAT", -1)
        with self.assertRaises(ValueError):
            d.conservative_headroom("WHEAT", 1, q=1.1)
        with self.assertRaises(ValueError):
            d.panel_absorption(())


if __name__ == "__main__":
    unittest.main()
