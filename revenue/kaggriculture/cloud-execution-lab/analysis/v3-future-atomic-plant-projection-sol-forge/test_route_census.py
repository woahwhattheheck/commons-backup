#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("sol_forge_route_census", HERE / "route_census.py")
route_census = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(route_census)

PASS = {"farmer": ["PASS"], "hands": [], "market": []}


class RouteCensusContracts(unittest.TestCase):
    def test_repeated_same_crop_packet_is_route_risk(self):
        row = {
            "farmer": ["PLANT", "WHEAT"],
            "hands": [["PLANT", "WHEAT"]],
            "market": [],
        }
        report = route_census.census_routes({"main": [PASS, row]})
        self.assertEqual(report["disposition"], "ROUTE_RISK")
        self.assertEqual(report["repeated_row_count"], 1)
        self.assertEqual(
            report["repeated_same_crop_plant_rows"][0],
            {
                "route_id": "main",
                "step": 1,
                "crop": "WHEAT",
                "demand": 2,
                "actors": [0, 1],
                "row_sha256": route_census.sha256(route_census.canonical_json(row)),
            },
        )

    def test_single_requests_are_dormant(self):
        report = route_census.census_routes(
            {
                "a": [
                    {"farmer": ["PLANT", "WHEAT"], "hands": [["PASS"]]},
                    {"farmer": ["PASS"], "hands": [["PLANT", "WHEAT"]]},
                ]
            }
        )
        self.assertEqual(report["disposition"], "DORMANT")
        self.assertEqual(report["repeated_row_count"], 0)

    def test_crops_are_counted_independently(self):
        report = route_census.census_routes(
            {
                "mixed": [
                    {
                        "farmer": ["PLANT", "WHEAT"],
                        "hands": [
                            ["PLANT", "CARROT"],
                            ["PLANT", "WHEAT"],
                            ["PLANT", "CARROT"],
                            ["PLANT", "CARROT"],
                        ],
                    }
                ]
            }
        )
        rows = report["repeated_same_crop_plant_rows"]
        self.assertEqual([(r["crop"], r["demand"]) for r in rows], [("CARROT", 3), ("WHEAT", 2)])
        self.assertEqual(report["rows_by_crop"], {"CARROT": 1, "WHEAT": 1})
        self.assertEqual(report["rows_by_packet_demand"], {"2": 1, "3": 1})

    def test_non_list_hands_matches_official_empty_packet_rule(self):
        report = route_census.census_routes(
            {"main": [{"farmer": ["PLANT", "WHEAT"], "hands": "bad"}]}
        )
        self.assertEqual(report["repeated_row_count"], 0)

    def test_input_is_not_mutated_and_output_is_deterministic(self):
        routes = {
            "z": [
                {
                    "farmer": ["PLANT", "MELON"],
                    "hands": [["PLANT", "MELON"]],
                }
            ],
            "a": [copy.deepcopy(PASS)],
        }
        before = copy.deepcopy(routes)
        first = route_census.census_routes(routes)
        second = route_census.census_routes(routes)
        self.assertEqual(first, second)
        self.assertEqual(routes, before)
        self.assertEqual(list(first["route_lengths"]), ["a", "z"])

    def test_malformed_route_row_fails_closed(self):
        with self.assertRaisesRegex(route_census.CensusError, "not a mapping"):
            route_census.census_routes({"main": [None]})


if __name__ == "__main__":
    unittest.main(verbosity=2)
