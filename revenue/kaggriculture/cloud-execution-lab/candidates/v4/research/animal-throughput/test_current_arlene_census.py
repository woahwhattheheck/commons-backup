#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "current_arlene_census", HERE / "current_arlene_census.py"
)
assert SPEC and SPEC.loader
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def action(farmer=None, hands=None, market=None):
    return {
        "farmer": farmer if farmer is not None else ["PASS"],
        "hands": hands if hands is not None else [],
        "market": market if market is not None else [],
    }


class CurrentArleneCensusTests(unittest.TestCase):
    def test_counts_pipeline_and_ratios(self):
        route = [
            action(market=[["BUY_ANIMAL", "GOOSE", 2], ["BUY_ANIMAL", "COW", 1]]),
            action(["PLACE", "GOOSE"], [["PLACE", "COW"]]),
            action(["FEED"], [["CARE"]]),
            action(
                ["HARVEST"],
                [["COLLECT_FERTILIZER"]],
                [["SELL", "EGG", 3]],
            ),
        ]
        out = m.census_current_route(route, "r")
        self.assertEqual(
            out["animal_buy_units"], {"GOOSE": 2, "COW": 1, "SHEEP": 0}
        )
        self.assertEqual(
            out["animal_place_rows"], {"GOOSE": 1, "COW": 1, "SHEEP": 0}
        )
        self.assertEqual(out["collection_action_slots"], 1)
        self.assertEqual(
            out["fertilizer_units_upper_bound_from_scheduled_collects"], 1
        )
        self.assertEqual(out["animal_product_sell_units"]["EGG"], 3)
        self.assertEqual(
            out["service_ratios_per_animal_bought"]["feed_rows"],
            round(1 / 3, 6),
        )

    def test_market_prefix_is_executable_prefix_only(self):
        market = [["SELL", "EGG", 1] for _ in range(10)]
        market.append(["BUY_ANIMAL", "SHEEP", 9])
        out = m.census_current_route([action(market=market)], "r", max_orders=10)
        self.assertEqual(out["animal_buy_units"]["SHEEP"], 0)
        self.assertEqual(out["animal_product_sell_units"]["EGG"], 10)

    def test_nonpositive_and_malformed_quantities_do_not_inflate(self):
        route = [
            action(
                market=[
                    ["BUY_ANIMAL", "GOOSE", -3],
                    ["BUY_ANIMAL", "COW", "x"],
                ]
            )
        ]
        out = m.census_current_route(route, "r")
        self.assertEqual(sum(out["animal_buy_units"].values()), 0)

    def test_build_summary_ranges(self):
        routes = {
            "a": [
                action(market=[["BUY_ANIMAL", "GOOSE", 1]]),
                action(["COLLECT_FERTILIZER"]),
            ],
            "b": [
                action(market=[["BUY_ANIMAL", "GOOSE", 3]]),
                action(
                    ["COLLECT_FERTILIZER"],
                    [["COLLECT_FERTILIZER"]],
                ),
            ],
        }
        out = m.build_current_census(routes, max_orders=10)
        self.assertEqual(out["summary"]["min_scheduled_collect_ceiling"], 1)
        self.assertEqual(out["summary"]["max_scheduled_collect_ceiling"], 2)
        self.assertEqual(out["summary"]["min_animal_buy_units"], 1)
        self.assertEqual(out["summary"]["max_animal_buy_units"], 3)
        self.assertFalse(out["decision_authority"])

    def test_bad_route_action_rejected(self):
        with self.assertRaises(m.CurrentArleneCensusError):
            m.census_current_route([None], "r")

    def test_nonpositive_market_cap_rejected(self):
        with self.assertRaises(ValueError):
            m.census_current_route([], "r", max_orders=0)

    def test_blob_hash_matches_git_object_format(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "x.py"
            p.write_text("pass\n", encoding="utf-8")
            self.assertEqual(
                m.git_blob_sha(p),
                "2ae28399f5fda2dfb1b04405f4a3b4895f5fac1e",
            )

    def test_current_checkout_arlene_source_and_decoder(self):
        if not m.ARLENE_PATH.is_file():
            self.skipTest("checkout-only current Arlene source test")
        routes, max_orders, receipt = m.load_current_routes()
        self.assertEqual(receipt["arlene_blob"], m.EXPECTED_ARLENE_BLOB)
        self.assertEqual(receipt["turns"], 720)
        self.assertEqual(max_orders, 10)
        self.assertEqual(set(receipt["route_ids"]), set(receipt["declared_route_ids"]))
        self.assertEqual(len(routes), 4)
        self.assertTrue(all(len(route) == 720 for route in routes.values()))


if __name__ == "__main__":
    unittest.main()
