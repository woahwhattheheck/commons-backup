#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import unittest

import verify_animal_feed_cadence as probe


class AnimalFeedCadenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = probe.load_engine()

    def test_one_miss_recovers_but_two_consecutive_misses_escape(self):
        boundary = probe.survival_boundary(self.engine)
        self.assertTrue(boundary["one_miss_then_feed_alive"])
        self.assertEqual(boundary["one_miss_then_feed_consecutive_unfed"], 0)
        self.assertFalse(boundary["two_consecutive_misses_alive"])

    def test_alternating_no_care_preserves_base_output_and_saves_wheat(self):
        rows = probe.animal_cases(self.engine)
        self.assertEqual({row["animal"] for row in rows}, {"GOOSE", "COW", "SHEEP"})
        for row in rows:
            with self.subTest(animal=row["animal"]):
                self.assertTrue(row["daily"]["alive"])
                self.assertTrue(row["alternating_no_care"]["alive"])
                self.assertTrue(row["no_care_base_yield_preserved"])
                self.assertGreater(row["wheat_saved"], 0)

    def test_care_bonus_is_a_real_exclusion(self):
        for row in probe.animal_cases(self.engine):
            with self.subTest(animal=row["animal"]):
                self.assertTrue(row["care_bonus_changes_outcome"])
                self.assertGreater(
                    row["first_production_care_yield_daily"],
                    row["first_production_care_yield_sparse"],
                )

    def test_pinned_current_routes_have_expected_shape(self):
        census = probe.route_census(probe.load_routes())
        self.assertGreaterEqual(census["route_count"], 1)
        self.assertTrue(census["routes"])
        for name, row in census["routes"].items():
            with self.subTest(route=name):
                self.assertEqual(row["steps"], 720)
                self.assertGreaterEqual(row["feed_action_count"], 0)
                self.assertGreaterEqual(row["care_action_count"], 0)
                self.assertGreaterEqual(row["wheat_pickup_count"], 0)

    def test_full_probe_is_evidence_only(self):
        result = probe.run_probe()
        self.assertEqual(result["verdict"], "CONFIRMED_WITH_GUARDS")
        self.assertFalse(result["runtime_change"])
        self.assertFalse(result["policy_change"])
        self.assertTrue(all(result["checks"].values()))


if __name__ == "__main__":
    unittest.main()
