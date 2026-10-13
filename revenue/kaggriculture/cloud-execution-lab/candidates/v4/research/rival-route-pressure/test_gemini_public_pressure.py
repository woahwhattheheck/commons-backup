from __future__ import annotations

from copy import deepcopy
import math
import unittest

import gemini_public_pressure as G
import rival_route_pressure as R


CFG = {
    "episodeSteps": 720,
    "townShopSellInterval": 4,
    "townCenterSellInterval": 24,
}


def observation(
    *,
    step=40,
    own_quadrants=("NW",),
    rival_quadrants=("NW", "NE"),
    prices=None,
    shops=None,
    rival_tiles=None,
    private=None,
):
    own = {"tiles": [[None]], "money": 3000}
    rival = {
        "tiles": rival_tiles if rival_tiles is not None else [[None]],
        "money": 3000,
    }
    if own_quadrants is not None:
        own["unlocked_quadrants"] = list(own_quadrants)
    if rival_quadrants is not None:
        rival["unlocked_quadrants"] = list(rival_quadrants)
    return {
        "step": step,
        "player": 0,
        "farms": [own, rival],
        "private": private if private is not None else {"shed": {"WOOL": 999}},
        "town": {"unlocked_shops": list(shops or [])},
        "market": {"inventory": {}, "prices": dict(prices or {})},
    }


class GeminiPublicPressureTests(unittest.TestCase):
    def test_expansion_and_dump_witnesses_can_coexist(self):
        obs = observation(step=40, prices={"WOOL": 20})
        got = G.public_pressure_profile(
            obs, CFG, {"WOOL": 40}, previous_step=39, horizon=1)
        self.assertTrue(got["expansion_evidence"]["gemini_early_expander_witness"])
        self.assertTrue(got["has_dump_witness"])
        self.assertEqual(got["dump_witness_products"], ["WOOL"])
        self.assertEqual(got["previous_price_step"], 39)

    def test_shop_arb_is_exact_drain_not_fractional_weight(self):
        obs = observation(step=4, shops=["YARN_STORE"], prices={"WOOL": 20})
        got = G.public_pressure_profile(
            obs, CFG, {"WOOL": 20}, previous_step=3, horizon=1)
        row = next(row for row in got["product_rows"] if row["product"] == "WOOL")
        self.assertEqual(row["known_current_town_drain"], 2)
        self.assertTrue(row["has_known_current_town_drain"])
        self.assertFalse(got["overrides_engine_absorption"])

    def test_rival_visible_supply_is_reported_without_private_inventory(self):
        tiles = [[{"kind": "PASTURE", "animal": "SHEEP", "yield_units": 3}]]
        a = observation(rival_tiles=tiles, private={"shed": {"WOOL": 0}})
        b = observation(rival_tiles=tiles, private={"shed": {"WOOL": 999999}})
        ga = G.public_pressure_profile(a, CFG, horizon=1)
        gb = G.public_pressure_profile(b, CFG, horizon=1)
        self.assertEqual(ga, gb)
        row = next(row for row in ga["product_rows"] if row["product"] == "WOOL")
        self.assertEqual(row["visible_rival_standing_yield"], 3)
        self.assertEqual(row["visible_rival_productive_sources"], 1)

    def test_missing_quadrant_surface_keeps_other_public_evidence(self):
        obs = observation(
            own_quadrants=None,
            rival_quadrants=None,
            prices={"MILK": 20},
            shops=["PIZZA_SHOP"],
        )
        got = G.public_pressure_profile(
            obs, CFG, {"MILK": 40}, previous_step=39, horizon=1)
        self.assertFalse(got["expansion_evidence"]["available"])
        self.assertEqual(got["dump_witness_products"], ["MILK"])

    def test_reachable_quadrant_prefixes_are_accepted(self):
        prefixes = [
            ("NW",),
            ("NW", "NE"),
            ("NW", "NE", "SW"),
            ("NW", "NE", "SW", "SE"),
        ]
        for prefix in prefixes:
            with self.subTest(prefix=prefix):
                got = G.public_pressure_profile(
                    observation(own_quadrants=prefix, rival_quadrants=prefix),
                    CFG,
                    horizon=1,
                )
                self.assertTrue(got["expansion_evidence"]["available"])
                self.assertEqual(
                    got["expansion_evidence"]["own_unlocked_quadrants"],
                    len(prefix),
                )

    def test_impossible_quadrant_states_fail_closed(self):
        for quadrants in [
            (),
            ("NE",),
            ("NW", "NW"),
            ("NW", "SW"),
            ("NW", "NE", "SE"),
            ("NW", "BOGUS"),
        ]:
            with self.subTest(quadrants=quadrants):
                with self.assertRaises(R.UnsupportedEvidence):
                    G.public_pressure_profile(
                        observation(rival_quadrants=quadrants), CFG, horizon=1)

    def test_horizon_is_clipped_to_last_executable_callback(self):
        got = G.public_pressure_profile(observation(step=718), CFG, horizon=24)
        self.assertEqual(got["end"], 718)
        self.assertEqual(got["last_executable_callback"], 718)

    def test_phantom_postterminal_callback_fails_closed(self):
        with self.assertRaises(R.UnsupportedEvidence):
            G.public_pressure_profile(observation(step=719), CFG, horizon=1)
        with self.assertRaises(R.UnsupportedEvidence):
            G.public_pressure_profile(observation(step=720), CFG)

    def test_stale_previous_price_snapshot_cannot_mint_dump_witness(self):
        obs = observation(step=40, prices={"WOOL": 20})
        with self.assertRaises(R.UnsupportedEvidence):
            G.public_pressure_profile(
                obs, CFG, {"WOOL": 40}, previous_step=38, horizon=1)
        with self.assertRaises(R.UnsupportedEvidence):
            G.public_pressure_profile(
                obs, CFG, {"WOOL": 40}, previous_step=40, horizon=1)

    def test_bare_previous_price_mapping_is_rejected(self):
        with self.assertRaises(R.UnsupportedEvidence):
            G.public_pressure_profile(
                observation(step=40, prices={"WOOL": 20}),
                CFG,
                {"WOOL": 40},
                horizon=1,
            )

    def test_previous_step_without_snapshot_is_rejected(self):
        with self.assertRaises(R.UnsupportedEvidence):
            G.public_pressure_profile(observation(step=40), CFG, previous_step=39)

    def test_step_zero_cannot_claim_prior_snapshot(self):
        with self.assertRaises(R.UnsupportedEvidence):
            G.public_pressure_profile(
                observation(step=0, prices={"WOOL": 20}),
                CFG,
                {"WOOL": 40},
                previous_step=0,
            )

    def test_nan_prior_price_fails_closed(self):
        with self.assertRaises(R.UnsupportedEvidence):
            G.public_pressure_profile(
                observation(prices={"WOOL": 20}),
                CFG,
                {"WOOL": math.nan},
                previous_step=39,
            )

    def test_too_short_episode_contract_fails_closed(self):
        with self.assertRaises(R.UnsupportedEvidence):
            G.public_pressure_profile(observation(step=0), {**CFG, "episodeSteps": 1})

    def test_report_is_non_authoritative_and_inputs_are_not_mutated(self):
        obs = observation(prices={"WOOL": 20}, shops=["YARN_STORE"])
        prior = {"WOOL": 40}
        before = deepcopy((obs, prior))
        got = G.public_pressure_profile(
            obs, CFG, prior, previous_step=39, horizon=2)
        self.assertEqual((obs, prior), before)
        self.assertFalse(got["decision_authority"])
        self.assertFalse(got["mutates_action"])
        self.assertNotIn("allow", got)
        self.assertNotIn("deny", got)
        self.assertNotIn("choose", got)

    def test_exact_threshold_matches_original_o01_boundary(self):
        got = G.public_pressure_profile(
            observation(prices={"WHEAT": 25}),
            CFG,
            {"WHEAT": 40},
            previous_step=39,
            horizon=1,
        )
        self.assertIn("WHEAT", got["dump_witness_products"])

    def test_named_witness_boundaries_are_canonical_and_reported(self):
        at_early_boundary = G.public_pressure_profile(
            observation(step=144), CFG, horizon=1)
        after_early_boundary = G.public_pressure_profile(
            observation(step=145), CFG, horizon=1)
        self.assertTrue(
            at_early_boundary["expansion_evidence"]["gemini_early_expander_witness"])
        self.assertFalse(
            after_early_boundary["expansion_evidence"]["gemini_early_expander_witness"])
        self.assertEqual(at_early_boundary["early_step_max"], 144)
        self.assertEqual(at_early_boundary["dump_threshold"], 15.0)

        at_dump_boundary = G.public_pressure_profile(
            observation(step=40, prices={"WHEAT": 25}),
            CFG,
            {"WHEAT": 40},
            previous_step=39,
            horizon=1,
        )
        below_dump_boundary = G.public_pressure_profile(
            observation(step=40, prices={"WHEAT": 26}),
            CFG,
            {"WHEAT": 40},
            previous_step=39,
            horizon=1,
        )
        self.assertIn("WHEAT", at_dump_boundary["dump_witness_products"])
        self.assertNotIn("WHEAT", below_dump_boundary["dump_witness_products"])

    def test_callers_cannot_override_named_witness_boundaries(self):
        with self.assertRaises(TypeError):
            G.public_pressure_profile(
                observation(step=200),
                CFG,
                horizon=1,
                early_step_max=718,
            )
        with self.assertRaises(TypeError):
            G.public_pressure_profile(
                observation(step=40, prices={"WOOL": 20}),
                CFG,
                {"WOOL": 20},
                previous_step=39,
                horizon=1,
                dump_threshold=0,
            )


if __name__ == "__main__":
    unittest.main()
