# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from pathlib import Path
import unittest

from weedbank_occupancy_lease import (
    BASELINE_CLEAR_AND_RENEW,
    BASELINE_LEAVE_FIRST_WEED,
    ENGINE_GIT_BLOB,
    WeedbankContractError,
    expected_baseline_weed_events,
    expected_empty_tile_rng_draws,
    git_blob_sha1,
    occupancy_lease_receipt,
    verify_engine_bytes,
    weed_spawn_probability,
)


class WeedbankOccupancyLeaseTests(unittest.TestCase):
    def test_exact_pinned_engine_and_semantic_anchors(self):
        lab = Path(__file__).resolve().parents[4]
        engine = lab / "reference" / "engine" / "kaggriculture.py"
        data = engine.read_bytes()
        self.assertEqual(git_blob_sha1(data), ENGINE_GIT_BLOB)
        self.assertTrue(verify_engine_bytes(data))

    def test_standard_leave_first_baseline_is_truncated_geometric(self):
        receipt = occupancy_lease_receipt(
            30,
            0.005,
            baseline_policy=BASELINE_LEAVE_FIRST_WEED,
            restore_with_dig=True,
        )
        self.assertEqual(receipt["schema"], "titan-v4/weedbank-occupancy-lease/v2")
        self.assertAlmostEqual(receipt["weed_spawn_probability"], 0.13961580808530394)
        self.assertAlmostEqual(receipt["expected_baseline_weed_cleanup_actions"], 0.13961580808530394)
        self.assertAlmostEqual(receipt["expected_baseline_rng_draws"], 27.92316161706079)
        self.assertAlmostEqual(receipt["direct_action_delta"], -1.860384191914696)
        self.assertFalse(receipt["direct_weed_labor_advantage"])

    def test_standard_clear_and_renew_baseline_reenters_rng_each_eod(self):
        receipt = occupancy_lease_receipt(
            30,
            0.005,
            baseline_policy=BASELINE_CLEAR_AND_RENEW,
            restore_with_dig=True,
        )
        self.assertAlmostEqual(receipt["weed_spawn_probability"], 0.13961580808530394)
        self.assertAlmostEqual(receipt["expected_baseline_weed_cleanup_actions"], 0.15)
        self.assertEqual(receipt["expected_baseline_rng_draws"], 30.0)
        self.assertAlmostEqual(receipt["direct_action_delta"], -1.85)
        self.assertFalse(receipt["direct_weed_labor_advantage"])

    def test_certain_weed_three_eods_separates_policy_signs(self):
        leave = occupancy_lease_receipt(
            3,
            1.0,
            baseline_policy=BASELINE_LEAVE_FIRST_WEED,
        )
        renew = occupancy_lease_receipt(
            3,
            1.0,
            baseline_policy=BASELINE_CLEAR_AND_RENEW,
        )
        self.assertEqual(leave["expected_baseline_weed_cleanup_actions"], 1.0)
        self.assertEqual(leave["expected_baseline_rng_draws"], 1.0)
        self.assertEqual(leave["direct_action_delta"], -1.0)
        self.assertFalse(leave["direct_weed_labor_advantage"])
        self.assertEqual(renew["expected_baseline_weed_cleanup_actions"], 3.0)
        self.assertEqual(renew["expected_baseline_rng_draws"], 3.0)
        self.assertEqual(renew["direct_action_delta"], 1.0)
        self.assertTrue(renew["direct_weed_labor_advantage"])
        self.assertFalse(renew["global_direct_labor_sign_authority"])

    def test_nonrestored_lease_keeps_policy_specific_delta(self):
        leave = occupancy_lease_receipt(
            30,
            0.005,
            baseline_policy=BASELINE_LEAVE_FIRST_WEED,
            restore_with_dig=False,
        )
        renew = occupancy_lease_receipt(
            30,
            0.005,
            baseline_policy=BASELINE_CLEAR_AND_RENEW,
            restore_with_dig=False,
        )
        self.assertAlmostEqual(leave["direct_action_delta"], -0.8603841919146961)
        self.assertAlmostEqual(renew["direct_action_delta"], -0.85)

    def test_zero_weed_chance_both_policies_still_move_rng_cursor(self):
        for policy in (BASELINE_LEAVE_FIRST_WEED, BASELINE_CLEAR_AND_RENEW):
            receipt = occupancy_lease_receipt(30, 0.0, baseline_policy=policy)
            self.assertEqual(receipt["weed_spawn_probability"], 0.0)
            self.assertEqual(receipt["expected_baseline_weed_cleanup_actions"], 0.0)
            self.assertEqual(receipt["expected_rng_draws_suppressed"], 30.0)
            self.assertEqual(receipt["direct_action_delta"], -2.0)

    def test_zero_horizon_both_policies(self):
        for policy in (BASELINE_LEAVE_FIRST_WEED, BASELINE_CLEAR_AND_RENEW):
            receipt = occupancy_lease_receipt(0, 0.005, baseline_policy=policy)
            self.assertEqual(receipt["weed_spawn_probability"], 0.0)
            self.assertEqual(receipt["expected_baseline_weed_cleanup_actions"], 0.0)
            self.assertEqual(receipt["expected_rng_draws_suppressed"], 0.0)
            self.assertEqual(receipt["direct_action_delta"], -2.0)

    def test_helpers_are_policy_explicit(self):
        self.assertEqual(expected_baseline_weed_events(3, 1.0, BASELINE_LEAVE_FIRST_WEED), 1.0)
        self.assertEqual(expected_baseline_weed_events(3, 1.0, BASELINE_CLEAR_AND_RENEW), 3.0)
        self.assertEqual(expected_empty_tile_rng_draws(3, 1.0, BASELINE_LEAVE_FIRST_WEED), 1.0)
        self.assertEqual(expected_empty_tile_rng_draws(3, 1.0, BASELINE_CLEAR_AND_RENEW), 3.0)

    def test_at_least_one_spawn_probability_is_not_cleanup_count(self):
        probability = weed_spawn_probability(30, 0.005)
        renewal_events = expected_baseline_weed_events(30, 0.005, BASELINE_CLEAR_AND_RENEW)
        self.assertAlmostEqual(probability, 0.13961580808530394)
        self.assertAlmostEqual(renewal_events, 0.15)
        self.assertGreater(renewal_events, probability)

    def test_no_runtime_hidden_seed_or_global_sign_authority(self):
        for policy in (BASELINE_LEAVE_FIRST_WEED, BASELINE_CLEAR_AND_RENEW):
            receipt = occupancy_lease_receipt(30, baseline_policy=policy)
            self.assertFalse(receipt["rng_decision_authority"])
            self.assertFalse(receipt["hidden_seed_targeting_authority"])
            self.assertFalse(receipt["runtime_policy_authority"])
            self.assertFalse(receipt["global_direct_labor_sign_authority"])

    def test_type_range_and_policy_poison_fail_closed(self):
        for value in (-1, True, 1.5, "30"):
            with self.assertRaises(WeedbankContractError):
                occupancy_lease_receipt(value, baseline_policy=BASELINE_LEAVE_FIRST_WEED)  # type: ignore[arg-type]
        for value in (-0.1, 1.1, True, float("nan"), float("inf"), "0.005"):
            with self.assertRaises(WeedbankContractError):
                occupancy_lease_receipt(30, value, baseline_policy=BASELINE_LEAVE_FIRST_WEED)  # type: ignore[arg-type]
        for value in (None, "", "leave-first", 1, True):
            with self.assertRaises(WeedbankContractError):
                occupancy_lease_receipt(30, baseline_policy=value)  # type: ignore[arg-type]
        with self.assertRaises(WeedbankContractError):
            occupancy_lease_receipt(
                30,
                baseline_policy=BASELINE_LEAVE_FIRST_WEED,
                restore_with_dig=1,  # type: ignore[arg-type]
            )

    def test_source_drift_rejected(self):
        with self.assertRaises(WeedbankContractError):
            verify_engine_bytes(b"not the engine")


if __name__ == "__main__":
    unittest.main()
