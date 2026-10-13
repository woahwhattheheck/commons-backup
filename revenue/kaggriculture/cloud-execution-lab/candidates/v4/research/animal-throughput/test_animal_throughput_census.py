#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import unittest

MODULE_PATH = Path(__file__).with_name("animal_throughput_census.py")
SPEC = importlib.util.spec_from_file_location("herdscale", MODULE_PATH)
assert SPEC and SPEC.loader
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def blank_action():
    return {"farmer": ["PASS"], "hands": [], "market": []}


def synthetic_tapes():
    tapes = []
    for plan in range(m.TAPE_COUNT):
        tape = [blank_action() for _ in range(m.TAPE_STEPS)]
        tape[10] = {"farmer": [f"OPEN_{plan}"], "hands": [], "market": []}
        tape[200] = {"farmer": [f"MID_{plan}"], "hands": [], "market": []}
        tape[700] = {"farmer": [f"END_{plan}"], "hands": [], "market": []}
        tapes.append(tape)
    return tapes


class RouteSpliceTests(unittest.TestCase):
    def test_router_splice_boundaries(self):
        tapes = synthetic_tapes()
        route = m.effective_route(tapes, 9)
        self.assertEqual(route[10]["farmer"][0], "OPEN_0")
        self.assertEqual(route[200]["farmer"][0], "MID_9")
        self.assertEqual(route[700]["farmer"][0], "END_2")

    def test_route_length_stays_719(self):
        self.assertEqual(len(m.effective_route(synthetic_tapes(), 0)), 719)

    def test_bad_plan_fails_closed(self):
        with self.assertRaises(m.CensusError):
            m.effective_route(synthetic_tapes(), 13)


class CensusTests(unittest.TestCase):
    def test_collection_slots_are_literal_upper_bound(self):
        route = [blank_action() for _ in range(m.TAPE_STEPS)]
        route[24]["farmer"] = ["COLLECT_FERTILIZER"]
        route[25]["hands"] = [["COLLECT_FERTILIZER"], ["PASS"]]
        out = m.census_route(route, 4)
        self.assertEqual(out["collection_action_slots"], 2)
        self.assertEqual(out["fertilizer_units_upper_bound_from_scheduled_collects"], 2)
        self.assertEqual(out["daily_collect_slots"], {"1": 2})

    def test_market_quantities_and_animal_targets(self):
        route = [blank_action() for _ in range(m.TAPE_STEPS)]
        route[100]["market"] = [
            ["BUY_ANIMAL", "GOOSE", 3],
            ["BUY_ANIMAL", "SHEEP", 2],
            ["BUY_PRODUCT", "WHEAT", 6],
        ]
        route[101]["farmer"] = ["PLACE", "GOOSE"]
        out = m.census_route(route, 0)
        self.assertEqual(out["animal_buy_units"]["GOOSE"], 3)
        self.assertEqual(out["animal_buy_units"]["SHEEP"], 2)
        self.assertEqual(out["animal_place_rows"]["GOOSE"], 1)
        self.assertEqual(out["market_targets"]["BUY_PRODUCT:WHEAT"], 1)

    def test_quantity_defaults_to_one(self):
        self.assertEqual(m._quantity(["BUY_ANIMAL", "GOOSE"]), 1)

    def test_build_census_has_all_routes(self):
        out = m.build_census(synthetic_tapes(), {"test": "receipt"})
        self.assertEqual(out["schema"], "titan-v4-herdscale-throughput-census-v1")
        self.assertTrue(out["policy_inert"])
        self.assertEqual(len(out["routes"]), 13)

    def test_worker_pass_fallback_is_stable(self):
        rows = m._worker_rows({"farmer": None, "hands": [None, []]})
        self.assertEqual(rows, [["PASS"], ["PASS"], ["PASS"]])


if __name__ == "__main__":
    unittest.main()
