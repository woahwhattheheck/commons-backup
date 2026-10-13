from __future__ import annotations

from copy import deepcopy
import unittest

from b5_current import (
    B5_CARROT_GIT_BLOB,
    B5_CARROT_SOURCE_SHA256,
    B5_JIT_GIT_BLOB,
    B5_JIT_SOURCE_SHA256,
    DONOR_COMMIT,
)
from b5_current_safe import B5CurrentABI


class B5CurrentABITests(unittest.TestCase):
    def observation(self, *, step=50, crop="CARROT", planted_day=0, yield_units=0,
                    fertilized_until_day=0, watered_today=False, fertilizer=1,
                    same_tile=False):
        tile = {
            "kind": "PLANT",
            "crop": crop,
            "planted_day": planted_day,
            "yield_units": yield_units,
            "fertilized_until_day": fertilized_until_day,
            "watered_today": watered_today,
        }
        tiles = [[{} for _ in range(10)] for _ in range(10)]
        tiles[2][2] = tile
        hands = [[2, 2] if same_tile else [3, 2]]
        return {
            "step": step,
            "player": 0,
            "farms": [
                {"farmer": [2, 2], "hands": hands, "tiles": tiles},
                {"farmer": [0, 0], "hands": [], "tiles": [[{} for _ in range(10)] for _ in range(10)]},
            ],
            "private": {
                "inventories": [
                    {"FERTILIZER": fertilizer},
                    {"FERTILIZER": fertilizer},
                ],
                "shed": {},
            },
        }

    def action(self, farmer=None, hand=None):
        return {
            "farmer": ["PASS"] if farmer is None else farmer,
            "hands": [["PASS"] if hand is None else hand],
            "market": [["SELL", "MILK", 2]],
        }

    def test_donor_authorities_are_exact(self):
        self.assertEqual(DONOR_COMMIT, "a90d888f03987ef0b35cfd20ec3519c6144db08a")
        self.assertEqual(B5_CARROT_GIT_BLOB, "2a9d606835b0d04d832a4737dcb381ad3fbef1ae")
        self.assertEqual(B5_CARROT_SOURCE_SHA256, "f2d03ab19e1a233566cfc9076bd8b9843c7f8d611703578218bd73c1af0f626f")
        self.assertEqual(B5_JIT_GIT_BLOB, "6ef7ddcd9590e3cb3f55ceb708b8026235d59410")
        self.assertEqual(B5_JIT_SOURCE_SHA256, "5ad6340bf31dab13aaba82bfe0b51e6cde18222155013be1e0e080f0a26242b2")

    def test_flags_are_exact_bool_and_default_off(self):
        adapter = B5CurrentABI()
        self.assertIs(adapter.carrot, False)
        self.assertIs(adapter.jit, False)
        for value in (0, 1, None, "true"):
            with self.assertRaises(TypeError):
                B5CurrentABI(carrot=value)
            with self.assertRaises(TypeError):
                B5CurrentABI(jit=value)

    def test_default_off_preserves_identity_and_inputs(self):
        obs = self.observation()
        selected = self.action()
        next_authored = self.action(farmer=["WATER"])
        before_obs = deepcopy(obs)
        before_selected = deepcopy(selected)
        before_next = deepcopy(next_authored)
        result, report = B5CurrentABI().transform(
            obs, selected, next_authored=next_authored, next_authored_step=51
        )
        self.assertIs(result, selected)
        self.assertFalse(report["changed"])
        self.assertEqual(obs, before_obs)
        self.assertEqual(selected, before_selected)
        self.assertEqual(next_authored, before_next)

    def test_carrot_port_replaces_only_literal_pass_and_preserves_market(self):
        obs = self.observation(step=50, fertilized_until_day=2)
        selected = self.action(farmer=["PASS"], hand=["WATER"])
        market = deepcopy(selected["market"])
        result, report = B5CurrentABI(carrot=True).transform(obs, selected)
        self.assertEqual(result["farmer"], ["FERTILIZE"])
        self.assertEqual(result["hands"], [["WATER"]])
        self.assertEqual(result["market"], market)
        self.assertEqual(len(report["carrot_activations"]), 1)
        self.assertTrue(report["changed"])

    def test_carrot_malformed_coverage_fails_closed_atomically(self):
        obs = self.observation(fertilized_until_day=0)
        obs["farms"][0]["tiles"][2][2]["fertilized_until_day"] = "0"
        selected = self.action()
        result, report = B5CurrentABI(carrot=True).transform(obs, selected)
        self.assertIs(result, selected)
        self.assertEqual(report["carrot_activations"], ())

    def test_jit_requires_exact_authenticated_next_step(self):
        obs = self.observation(step=50, planted_day=0, yield_units=0,
                               fertilized_until_day=1)
        selected = self.action(farmer=["PASS"], hand=["DIG"])
        next_authored = self.action(farmer=["WATER"], hand=["PASS"])
        adapter = B5CurrentABI(jit=True)
        for next_step in (None, 50, 52, True):
            result, report = adapter.transform(
                obs, selected, next_authored=next_authored,
                next_authored_step=next_step,
            )
            self.assertIs(result, selected)
            self.assertFalse(report["jit_route_bound"])
            self.assertFalse(report["changed"])
        result, report = adapter.transform(
            obs, selected, next_authored=next_authored, next_authored_step=51
        )
        self.assertEqual(result["farmer"], ["FERTILIZE"])
        self.assertEqual(result["hands"], [["DIG"]])
        self.assertEqual(result["market"], selected["market"])
        self.assertTrue(report["jit_route_bound"])
        self.assertEqual(len(report["jit_activations"]), 1)

    def test_jit_refuses_day_boundary_and_non_yield_water(self):
        next_authored = self.action(farmer=["WATER"])
        adapter = B5CurrentABI(jit=True)
        boundary = self.observation(step=47, planted_day=0, fertilized_until_day=0)
        selected = self.action()
        result, report = adapter.transform(
            boundary, selected, next_authored=next_authored,
            next_authored_step=48,
        )
        self.assertIs(result, selected)
        self.assertEqual(report["jit_activations"], ())

        capped = self.observation(step=50, planted_day=0, yield_units=3,
                                  fertilized_until_day=0)
        result, report = adapter.transform(
            capped, selected, next_authored=next_authored,
            next_authored_step=51,
        )
        self.assertIs(result, selected)
        self.assertEqual(report["jit_activations"], ())

    def test_submitted_composition_order_carrot_preempts_jit_on_same_pass(self):
        obs = self.observation(step=50, planted_day=0, yield_units=0,
                               fertilized_until_day=1)
        selected = self.action()
        next_authored = self.action(farmer=["WATER"])
        result, report = B5CurrentABI(carrot=True, jit=True).transform(
            obs, selected, next_authored=next_authored, next_authored_step=51
        )
        self.assertEqual(result["farmer"], ["FERTILIZE"])
        self.assertEqual(len(report["carrot_activations"]), 1)
        self.assertEqual(report["jit_activations"], ())

    def test_jit_shared_tile_matches_fail_closed_for_duplicate_fertilization(self):
        obs = self.observation(step=50, crop="WHEAT", planted_day=0,
                               yield_units=0, fertilized_until_day=0, same_tile=True)
        selected = self.action()
        next_authored = self.action(farmer=["WATER"], hand=["WATER"])
        result, report = B5CurrentABI(jit=True).transform(
            obs, selected, next_authored=next_authored, next_authored_step=51
        )
        self.assertIs(result, selected)
        self.assertEqual(report["jit_activations"], ())

    def test_malformed_selected_cardinality_fails_closed_without_market_edit(self):
        obs = self.observation(step=50, fertilized_until_day=0)
        selected = {"farmer": ["PASS"], "hands": [], "market": [["SELL", "MILK", 2]]}
        result, report = B5CurrentABI(carrot=True, jit=True).transform(
            obs, selected,
            next_authored={"farmer": ["WATER"], "hands": []},
            next_authored_step=51,
        )
        self.assertIs(result, selected)
        self.assertEqual(result["market"], [["SELL", "MILK", 2]])
        self.assertFalse(report["changed"])
        self.assertEqual(report["reason"], "selected_worker_envelope_invalid")

    def test_malformed_next_route_cardinality_disables_jit_but_not_carrot(self):
        obs = self.observation(step=50, planted_day=0, yield_units=0,
                               fertilized_until_day=1)
        selected = self.action()
        result, report = B5CurrentABI(carrot=True, jit=True).transform(
            obs, selected,
            next_authored={"farmer": ["WATER"], "hands": []},
            next_authored_step=51,
        )
        self.assertEqual(result["farmer"], ["FERTILIZE"])
        self.assertEqual(len(report["carrot_activations"]), 1)
        self.assertFalse(report["jit_route_bound"])
        self.assertEqual(report["jit_activations"], ())


if __name__ == "__main__":
    unittest.main()
