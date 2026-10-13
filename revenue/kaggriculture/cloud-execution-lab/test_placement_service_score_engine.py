# SPDX-License-Identifier: Apache-2.0
"""P06 checks against the repository's extracted Kaggriculture mechanics."""
import unittest

import mechanics as m
from placement_service_score import ServiceCalendar, rank_empty_sites, score_site
from placement_service_score_test_support import farm


class PlacementServiceScoreEngineTests(unittest.TestCase):
    def test_actual_home_and_shed_access_geometry(self):
        self.assertEqual(tuple(m._default_spawn(10)), (4, 4))
        self.assertEqual(
            {tuple(p) for p in m._shed_access_tiles(10)},
            {(4, 4), (5, 4), (4, 5), (5, 5)},
        )
        f = farm(unlocked=["NW", "NE", "SW", "SE"])
        score, report = score_site(
            m, f, (5, 5),
            ServiceCalendar(home_to_site=1, shed_to_site=4, site_to_shed=4),
        )
        self.assertTrue(report["scored"])
        self.assertEqual(score.home_distance, 2)
        self.assertEqual(score.shed_distance, 0)

    def test_actual_engine_movement_crosses_locked_but_plant_does_not(self):
        f = farm()
        private = {"shed": {}, "inventories": [{}], "seeds": {"WHEAT": 1}}
        # EAST from (4,4) enters locked NE and is legal movement.
        m._apply_unit_action(f, private, 0, ["EAST"], 10, 0, 24, 100)
        self.assertEqual(f["farmer"], [5, 4])
        self.assertEqual(f["tiles"][4][5], "LOCKED")
        m._apply_unit_action(f, private, 0, ["PLANT", "WHEAT"], 10, 0, 24, 100)
        self.assertEqual(f["tiles"][4][5], "LOCKED")
        self.assertEqual(private["seeds"]["WHEAT"], 1)

    def test_rank_never_selects_actual_locked_tiles(self):
        f = farm()
        ranked, report = rank_empty_sites(m, f, ServiceCalendar(home_to_site=1))
        self.assertTrue(ranked)
        self.assertTrue(all(x < 5 and y < 5 for x, y in (s.site for s in ranked)))
        self.assertGreater(report["rejected"].get("locked_not_productively_usable", 0), 0)


if __name__ == "__main__":
    unittest.main()
