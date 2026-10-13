import unittest

import opening_expansion_economics as m


class OpeningExpansionEconomicsTests(unittest.TestCase):
    def test_authority(self):
        facts = m.assert_authority()
        self.assertEqual(facts["weedSpawnChance"], 0.005)
        self.assertEqual(facts["turnsPerDay"], 24)
        self.assertEqual(facts["startingMoney"], 3000)

    def test_weed_expectation_linear_in_empty_tiles(self):
        self.assertEqual(m.expected_spawn_events(25), 3.75)
        self.assertEqual(m.expected_spawn_events(100), 15.0)
        self.assertEqual(m.expected_spawn_events(100) / m.expected_spawn_events(25), 4.0)

    def test_uncleared_expectation(self):
        got25 = m.expected_distinct_uncleared(25)
        got100 = m.expected_distinct_uncleared(100)
        self.assertAlmostEqual(got25, 25 * (1 - 0.995**30), places=12)
        self.assertAlmostEqual(got100, 100 * (1 - 0.995**30), places=12)

    def test_seed_panel_reproducible(self):
        self.assertEqual(m.simulate_kernel(17, 25), m.simulate_kernel(17, 25))
        self.assertNotEqual(m.simulate_kernel(17, 25), m.simulate_kernel(18, 25))

    def test_blanket_structure_action_banking_is_not_expected_action_saving(self):
        r = m.action_banking_tile_cost()
        self.assertAlmostEqual(r["weed_probability_if_left_empty"], 1 - .995**30, places=12)
        self.assertLess(r["expected_busy_day_digs_empty_tile"], 1.0)
        self.assertEqual(r["guaranteed_busy_day_digs_prebuilt_structure"], 1.0)
        self.assertGreater(r["structure_to_empty_expected_dig_ratio"], 7.0)

    def test_ten_goose_no_hire_falsified(self):
        r = m.goose_one_farmer_lower_bound(10)
        self.assertEqual(r["minimum_unit_actions"], 30)
        self.assertFalse(r["feasible_one_farmer_day0"])
        self.assertEqual(r["post_purchase_actions_required_after_callback0_build"], 29)
        self.assertGreater(r["post_purchase_actions_required_after_callback0_build"],
                           r["post_purchase_callbacks_available"])

    def test_eight_is_ideal_lower_bound_ceiling(self):
        self.assertTrue(m.goose_one_farmer_lower_bound(8)["feasible_one_farmer_day0"])
        self.assertFalse(m.goose_one_farmer_lower_bound(9)["feasible_one_farmer_day0"])


if __name__ == "__main__":
    unittest.main()
