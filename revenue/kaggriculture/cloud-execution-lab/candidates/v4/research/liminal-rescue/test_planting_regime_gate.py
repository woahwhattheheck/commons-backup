import math
import unittest

from planting_regime_gate import PlantingProposal, evaluate_planting


class PlantingRegimeGateTests(unittest.TestCase):
    def test_existing_commitment_is_never_blocked(self):
        d = evaluate_planting(
            PlantingProposal(
                "TOMATO", 500, 0, 0, verified_floor=True, existing_commitment=True
            )
        )
        self.assertTrue(d.admit)
        self.assertEqual(d.reason, "existing_commitment")

    def test_required_obligation_is_never_blocked(self):
        d = evaluate_planting(
            PlantingProposal(
                "WHEAT", 500, 0, 0, verified_floor=True, required_for_obligation=True
            )
        )
        self.assertTrue(d.admit)
        self.assertEqual(d.reason, "required_for_obligation")

    def test_unverified_floor_fails_open(self):
        d = evaluate_planting(PlantingProposal("MELON", 100, 1, 1))
        self.assertTrue(d.admit)
        self.assertEqual(d.reason, "unverified_floor_fail_open")

    def test_missing_or_nonfinite_floor_fails_open(self):
        for cost in (None, math.inf, math.nan, -1):
            with self.subTest(cost=cost):
                d = evaluate_planting(
                    PlantingProposal("CARROT", cost, 4, 10, verified_floor=True)
                )
                self.assertTrue(d.admit)
                self.assertEqual(d.reason, "invalid_or_missing_floor_fail_open")

    def test_verified_loss_rejects_only_that_proposal(self):
        bad = evaluate_planting(
            PlantingProposal(
                "CARROT",
                incremental_cost=120,
                conservative_units=4,
                harvest_price_floor=20,
                risk_buffer=10,
                verified_floor=True,
            )
        )
        good = evaluate_planting(
            PlantingProposal(
                "CARROT",
                incremental_cost=80,
                conservative_units=4,
                harvest_price_floor=25,
                risk_buffer=10,
                verified_floor=True,
            )
        )
        self.assertFalse(bad.admit)
        self.assertEqual(bad.margin_floor, -50)
        self.assertTrue(good.admit)
        self.assertEqual(good.margin_floor, 10)

    def test_break_even_is_admitted(self):
        d = evaluate_planting(
            PlantingProposal(
                "STRAWBERRY",
                incremental_cost=100,
                conservative_units=5,
                harvest_price_floor=22,
                risk_buffer=10,
                verified_floor=True,
            )
        )
        self.assertTrue(d.admit)
        self.assertEqual(d.margin_floor, 0)

    def test_collateral_floor_can_rescue_commitment(self):
        d = evaluate_planting(
            PlantingProposal(
                "WHEAT",
                incremental_cost=100,
                conservative_units=2,
                harvest_price_floor=20,
                collateral_value_floor=70,
                risk_buffer=5,
                verified_floor=True,
            )
        )
        self.assertTrue(d.admit)
        self.assertEqual(d.value_floor, 110)
        self.assertEqual(d.hurdle, 105)

    def test_no_global_crop_ban(self):
        rejected = evaluate_planting(
            PlantingProposal("MELON", 100, 1, 20, verified_floor=True)
        )
        admitted = evaluate_planting(
            PlantingProposal("MELON", 100, 5, 25, verified_floor=True)
        )
        self.assertFalse(rejected.admit)
        self.assertTrue(admitted.admit)


if __name__ == "__main__":
    unittest.main()
