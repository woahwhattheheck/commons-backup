#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import route_exposure


def repository_root() -> Path:
    for candidate in (HERE, *HERE.parents):
        if (candidate / route_exposure.ARLENE_REL).is_file():
            return candidate
    raise RuntimeError("repository root not found")


REPO = repository_root()


class FrozenRouteExposureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = route_exposure.scan(REPO)

    def test_exact_arlene_source_is_bound(self):
        self.assertEqual(
            self.record["source"]["git_blob"],
            route_exposure.EXPECTED_ARLENE_GIT_BLOB,
        )
        self.assertEqual(
            self.record["source"]["output_cap_anchor"],
            route_exposure.OUTPUT_CAP_ANCHOR,
        )

    def test_scan_is_deterministic_and_json_roundtrippable(self):
        again = route_exposure.scan(REPO)
        self.assertEqual(self.record, again)
        self.assertEqual(json.loads(json.dumps(self.record, sort_keys=True)), self.record)

    def test_cap_series_is_complete_and_monotone(self):
        default_cap = self.record["arlene_output_cap"]
        self.assertGreaterEqual(default_cap, 1)
        self.assertEqual(
            list(self.record["caps"]),
            [str(cap) for cap in range(1, default_cap + 1)],
        )
        metrics = (
            "route_cells_over_cap",
            "unique_cells_over_cap",
            "route_cells_with_suffix_spend",
            "unique_cells_with_suffix_spend",
            "route_cells_with_active_sell_and_suffix_spend",
            "unique_cells_with_active_sell_and_suffix_spend",
            "suffix_spend_rows",
        )
        for metric in metrics:
            series = [self.record["caps"][str(cap)][metric] for cap in range(1, default_cap + 1)]
            self.assertEqual(series, sorted(series, reverse=True), metric)

    def test_alias_deduplication_never_inflates_counts(self):
        for cap, record in self.record["caps"].items():
            with self.subTest(cap=cap):
                self.assertLessEqual(record["unique_cells_over_cap"], record["route_cells_over_cap"])
                self.assertLessEqual(
                    record["unique_cells_with_suffix_spend"],
                    record["route_cells_with_suffix_spend"],
                )
                self.assertLessEqual(
                    record["unique_cells_with_active_sell_and_suffix_spend"],
                    record["route_cells_with_active_sell_and_suffix_spend"],
                )
                self.assertEqual(
                    sum(record["suffix_spend_by_op"].values()),
                    record["suffix_spend_rows"],
                )

    def test_receipt_refuses_a_scoreboard_causality_claim(self):
        self.assertFalse(self.record["scoreboard_causality_claim"])
        status = self.record["default_cap_status"]
        self.assertIn(status, {"EXPOSED", "DORMANT_AT_DEFAULT_CAP"})
        exposed = self.record["caps"][str(self.record["arlene_output_cap"])][
            "unique_cells_with_suffix_spend"
        ] > 0
        self.assertEqual(status == "EXPOSED", exposed)
        self.assertEqual(self.record["default_cap_future_route_exposure_only"], exposed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
