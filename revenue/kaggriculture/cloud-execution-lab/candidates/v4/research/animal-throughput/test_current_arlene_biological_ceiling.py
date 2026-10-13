#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
SPEC = importlib.util.spec_from_file_location(
    "current_arlene_biological_ceiling",
    HERE / "current_arlene_biological_ceiling.py",
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


class BiologicalCeilingUnitTests(unittest.TestCase):
    def test_eod_schedule(self):
        self.assertEqual(m._eod_steps(0, 24), [])
        self.assertEqual(m._eod_steps(24, 24), [23])
        self.assertEqual(m._eod_steps(48, 24), [23, 47])

    def test_same_step_buy_cannot_fund_place(self):
        route = [action(["PLACE", "COW"], market=[["BUY_ANIMAL", "COW", 1]])]
        out = m.optimistic_biological_ceiling(route, horizon=1)
        self.assertEqual(out["optimistic_matched_placements"]["COW"], 0)
        self.assertEqual(out["optimistic_unmatched_place_rows"]["COW"], 1)
        self.assertEqual(out["optimistic_unused_bought_animals"]["COW"], 1)

    def test_prior_buy_then_eod_place_generates_one_refresh(self):
        route = [action(market=[["BUY_ANIMAL", "COW", 1]])]
        route.extend(action() for _ in range(22))
        route.append(action(["PLACE", "COW"], hands=[["COLLECT_FERTILIZER"]]))
        out = m.optimistic_biological_ceiling(route, horizon=24)
        self.assertEqual(out["optimistic_matched_placements"]["COW"], 1)
        self.assertEqual(out["optimistic_animal_eod_refreshes"], 1)
        self.assertEqual(out["scheduled_collect_slots"], 1)
        self.assertEqual(out["fertilizer_units_optimistic_joint_upper_bound"], 1)

    def test_biological_supply_can_be_tighter_than_collect_rows(self):
        route = [action(market=[["BUY_ANIMAL", "SHEEP", 1]])]
        route.append(action(["PLACE", "SHEEP"]))
        route.extend(action(["COLLECT_FERTILIZER"]) for _ in range(22))
        out = m.optimistic_biological_ceiling(route, horizon=24)
        self.assertEqual(out["optimistic_animal_eod_refreshes"], 1)
        self.assertEqual(out["scheduled_collect_slots"], 22)
        self.assertEqual(out["fertilizer_units_optimistic_joint_upper_bound"], 1)
        self.assertEqual(out["scheduled_collect_headroom_above_joint_bound"], 21)

    def test_quantity_buys_fund_distinct_later_places(self):
        route = [action(market=[["BUY_ANIMAL", "GOOSE", 2]])]
        route.append(action(["PLACE", "GOOSE"], [["PLACE", "GOOSE"], ["PLACE", "GOOSE"]]))
        out = m.optimistic_biological_ceiling(route, horizon=2)
        self.assertEqual(out["optimistic_matched_placements"]["GOOSE"], 2)
        self.assertEqual(out["optimistic_unmatched_place_rows"]["GOOSE"], 1)
        self.assertEqual(out["optimistic_unused_bought_animals"]["GOOSE"], 0)

    def test_market_prefix_caps_biological_supply(self):
        market = [["PASS"] for _ in range(10)] + [["BUY_ANIMAL", "COW", 9]]
        route = [action(market=market), action(["PLACE", "COW"])]
        out = m.optimistic_biological_ceiling(route, max_orders=10, horizon=2)
        self.assertEqual(out["animal_buy_units"]["COW"], 0)
        self.assertEqual(out["optimistic_matched_placements"]["COW"], 0)

    def test_build_report_summary(self):
        routes = {
            "one": [action(market=[["BUY_ANIMAL", "COW", 1]]), action(["PLACE", "COW"])],
            "two": [action(), action()],
        }
        out = m.build_report(routes, max_orders=10)
        self.assertTrue(out["policy_inert"])
        self.assertFalse(out["decision_authority"])
        self.assertEqual(out["summary"]["routes"], 2)


class CurrentCheckoutTests(unittest.TestCase):
    def test_exact_current_sources_and_four_routes(self):
        if not m.ENGINE_PATH.is_file() or not m.base.ARLENE_PATH.is_file():
            self.skipTest("checkout-only current source test")
        engine_receipt = m.verify_engine_source()
        routes, max_orders, arlene_receipt = m.base.load_current_routes()
        self.assertEqual(engine_receipt["engine_blob"], m.EXPECTED_ENGINE_BLOB)
        self.assertEqual(arlene_receipt["arlene_blob"], m.base.EXPECTED_ARLENE_BLOB)
        self.assertEqual(len(routes), 4)
        rows = [
            m.optimistic_biological_ceiling(route, max_orders=max_orders)
            for route in routes.values()
        ]
        self.assertEqual({row["optimistic_animal_eod_refreshes"] for row in rows}, {397})
        self.assertEqual(
            sorted(row["scheduled_collect_slots"] for row in rows),
            [368, 376, 379, 384],
        )
        self.assertEqual(
            sorted(row["fertilizer_units_optimistic_joint_upper_bound"] for row in rows),
            [368, 376, 379, 384],
        )
        for row in rows:
            self.assertEqual(sum(row["animal_buy_units"].values()), 17)
            self.assertEqual(sum(row["optimistic_matched_placements"].values()), 17)
            self.assertEqual(sum(row["optimistic_unmatched_place_rows"].values()), 1)
            self.assertEqual(sum(row["optimistic_unused_bought_animals"].values()), 0)


if __name__ == "__main__":
    unittest.main()
