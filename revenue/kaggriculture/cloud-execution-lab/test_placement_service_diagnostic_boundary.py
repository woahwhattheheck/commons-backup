# SPDX-License-Identifier: Apache-2.0
import unittest

from placement_service_score import ServiceCalendar, compare_existing_site
from placement_service_score_test_support import M, farm


class PlacementServiceDiagnosticBoundaryTests(unittest.TestCase):
    def test_truncated_tile_row_fails_closed(self):
        f = farm()
        f["tiles"][0] = []
        result, report = compare_existing_site(
            M,
            f,
            (0, 0),
            ServiceCalendar(home_to_site=1),
        )
        self.assertIsNone(result)
        self.assertEqual(report["reason"], "current_site_tile_map_unobserved")

    def test_nonlist_or_missing_tile_map_fails_closed(self):
        for tiles in (None, {}, "tiles"):
            with self.subTest(tiles=tiles):
                f = farm()
                f["tiles"] = tiles
                result, report = compare_existing_site(
                    M,
                    f,
                    (0, 0),
                    ServiceCalendar(home_to_site=1),
                    {"boardSize": 10},
                )
                self.assertIsNone(result)
                self.assertEqual(report["reason"], "current_site_tile_map_unobserved")

        f = farm()
        del f["tiles"]
        result, report = compare_existing_site(
            M,
            f,
            (0, 0),
            ServiceCalendar(home_to_site=1),
        )
        self.assertIsNone(result)
        self.assertEqual(report["reason"], "current_site_tile_map_unobserved")

    def test_calendar_type_matches_score_site_contract(self):
        with self.assertRaises(TypeError):
            compare_existing_site(M, farm(), (0, 0), object())

    def test_valid_established_asset_comparison_is_unchanged(self):
        f = farm()
        f["tiles"][0][0] = {"kind": "PLANT", "crop": "WHEAT"}
        result, report = compare_existing_site(
            M,
            f,
            (0, 0),
            ServiceCalendar(home_to_site=10, site_to_shed=2),
        )
        self.assertTrue(report["compared"])
        self.assertEqual(report["reason"], "existing_asset_preserved")
        self.assertEqual(result["current_site"], [0, 0])
        self.assertEqual(result["action"], "diagnostic_only_no_eviction")


if __name__ == "__main__":
    unittest.main()
