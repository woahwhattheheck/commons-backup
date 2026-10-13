# SPDX-License-Identifier: Apache-2.0
import unittest

from placement_service_score import (
    ServiceCalendar, calendar_from_service_counts, compare_existing_site,
    rank_empty_sites, score_site, site_available,
)
from placement_service_score_test_support import M, farm


class PlacementServiceScoreTests(unittest.TestCase):
    def test_service_count_translation_is_explicit(self):
        c = calendar_from_service_counts(
            water=4, care=2, feed=3, harvest=2, collect_fertilizer=1,
            explicit_home_returns=5,
        )
        self.assertEqual(c, ServiceCalendar(
            home_to_site=9, shed_to_site=3, site_to_shed=3, site_to_home=5
        ))

    def test_no_planned_service_is_not_a_placement_signal(self):
        f = farm()
        score, report = score_site(M, f, (3, 4), ServiceCalendar())
        self.assertIsNone(score)
        self.assertEqual(report["reason"], "no_planned_service_legs")

    def test_locked_tile_is_not_placeable_but_not_a_travel_obstacle(self):
        f = farm()
        ok, reason = site_available(f, (5, 4), board=10)
        self.assertFalse(ok)
        self.assertEqual(reason, "locked_not_productively_usable")
        # Same coordinate becomes placeable after the observed NE unlock.
        f = farm(unlocked=["NW", "NE"])
        score, report = score_site(M, f, (5, 4), ServiceCalendar(home_to_site=1))
        self.assertTrue(report["scored"])
        self.assertEqual(score.home_distance, 1)
        self.assertFalse(report["movement_locked_tiles_are_obstacles"])

    def test_occupied_crop_is_never_candidate(self):
        f = farm()
        f["tiles"][4][3] = {"kind": "PLANT", "crop": "WHEAT"}
        score, report = score_site(M, f, (3, 4), ServiceCalendar(home_to_site=3))
        self.assertIsNone(score)
        self.assertEqual(report["reason"], "occupied_no_eviction")

    def test_placed_animal_is_never_candidate(self):
        f = farm()
        f["tiles"][3][4] = {"kind": "PASTURE", "animal": "COW"}
        score, report = score_site(M, f, (4, 3), ServiceCalendar(shed_to_site=4))
        self.assertIsNone(score)
        self.assertEqual(report["reason"], "occupied_no_eviction")

    def test_reserved_empty_tile_is_excluded(self):
        f = farm()
        score, report = score_site(
            M, f, (3, 4), ServiceCalendar(home_to_site=1), reserved={(3, 4)}
        )
        self.assertIsNone(score)
        self.assertEqual(report["reason"], "reserved")

    def test_reserved_generator_is_not_consumed_across_rank(self):
        f = farm()
        reserved = (site for site in ((4, 4), (3, 4)))
        ranked, report = rank_empty_sites(
            M, f, ServiceCalendar(home_to_site=1), reserved=reserved
        )
        sites = {score.site for score in ranked}
        self.assertNotIn((4, 4), sites)
        self.assertNotIn((3, 4), sites)
        self.assertGreaterEqual(report["rejected"].get("reserved", 0), 2)

    def test_noninteger_coordinates_do_not_alias_real_tiles(self):
        f = farm()
        calendar = ServiceCalendar(home_to_site=1)
        for site in ((3.9, 4), ("3", 4), (True, 4)):
            with self.subTest(site=site):
                with self.assertRaises(ValueError):
                    score_site(M, f, site, calendar)
        with self.assertRaises(ValueError):
            rank_empty_sites(M, f, calendar, reserved=((4.5, 4),))

    def test_home_weight_prefers_near_home(self):
        f = farm()
        calendar = ServiceCalendar(home_to_site=10)
        a, _ = score_site(M, f, (3, 4), calendar)
        b, _ = score_site(M, f, (0, 0), calendar)
        self.assertLess(a.total_travel, b.total_travel)

    def test_shed_heavy_calendar_can_prefer_nonhome_shed_corner(self):
        f = farm(unlocked=["NW", "NE", "SW", "SE"])
        calendar = ServiceCalendar(shed_to_site=20, site_to_shed=20, home_to_site=1)
        # (5,5) is a shed-access tile, distance 0 to shed, 2 from home.
        a, _ = score_site(M, f, (5, 5), calendar)
        # (3,4) is 1 from home and 1 from nearest shed.
        b, _ = score_site(M, f, (3, 4), calendar)
        self.assertLess(a.total_travel, b.total_travel)

    def test_annual_low_service_does_not_get_extra_frequency_credit(self):
        f = farm(unlocked=["NW", "NE", "SW", "SE"])
        annual = ServiceCalendar(home_to_site=1, site_to_shed=1)
        recurring = ServiceCalendar(home_to_site=20, shed_to_site=20, site_to_shed=10)
        near_home, _ = score_site(M, f, (3, 4), annual)
        far = score_site(M, f, (0, 0), annual)[0]
        self.assertLess(near_home.total_travel, far.total_travel)
        # Counts scale the same geometry rather than inventing asset value.
        self.assertGreater(
            score_site(M, f, (0, 0), recurring)[0].total_travel,
            far.total_travel,
        )

    def test_rank_is_deterministic_and_current_state_only(self):
        f = farm()
        ranked1, report1 = rank_empty_sites(M, f, ServiceCalendar(home_to_site=1))
        ranked2, report2 = rank_empty_sites(M, f, ServiceCalendar(home_to_site=1))
        self.assertEqual([s.site for s in ranked1], [s.site for s in ranked2])
        self.assertEqual(report1["best"], report2["best"])
        self.assertEqual(ranked1[0].site, (4, 4))

    def test_unlocking_more_land_adds_candidates_without_changing_existing_scores(self):
        c = ServiceCalendar(home_to_site=2, site_to_shed=1)
        f1 = farm()
        f2 = farm(unlocked=["NW", "NE"])
        r1, _ = rank_empty_sites(M, f1, c)
        r2, _ = rank_empty_sites(M, f2, c)
        d1 = {s.site: s.total_travel for s in r1}
        d2 = {s.site: s.total_travel for s in r2}
        self.assertTrue(set(d1).issubset(d2))
        self.assertTrue(all(d1[k] == d2[k] for k in d1))

    def test_existing_asset_comparison_is_diagnostic_only(self):
        f = farm()
        f["tiles"][0][0] = {"kind": "PLANT", "crop": "WHEAT"}
        result, report = compare_existing_site(
            M, f, (0, 0), ServiceCalendar(home_to_site=10, site_to_shed=2)
        )
        self.assertTrue(report["compared"])
        self.assertEqual(result["action"], "diagnostic_only_no_eviction")
        self.assertGreaterEqual(result["potential_travel_saving"], 0)
        self.assertIsInstance(f["tiles"][0][0], dict)

    def test_out_of_bounds_fails_closed(self):
        f = farm()
        score, report = score_site(M, f, (10, 0), ServiceCalendar(home_to_site=1))
        self.assertIsNone(score)
        self.assertEqual(report["reason"], "out_of_bounds")

    def test_bad_counts_fail_closed(self):
        with self.assertRaises(ValueError):
            ServiceCalendar(home_to_site=-1)


if __name__ == "__main__":
    unittest.main()
