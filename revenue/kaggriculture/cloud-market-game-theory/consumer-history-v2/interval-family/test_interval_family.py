# SPDX-License-Identifier: Apache-2.0
from collections import defaultdict
from dataclasses import dataclass
import unittest

from interval_family import build_interval_terminal_scenarios, enumerate_joint_vectors


@dataclass(frozen=True)
class Interval:
    step: int
    product: str
    lower: int
    upper: int
    admitted_lower: int
    admitted_upper: int
    reason: str


class History:
    def __init__(self, *, period=24, window=5, minimum=3):
        self.period, self.window, self.minimum = period, window, minimum
        self.records = defaultdict(dict)

    def add(self, interval):
        self.records[interval.product][interval.step] = interval


PRODUCTS = ("CARROT", "MILK", "WHEAT", "FERTILIZER")
TEMPLATE = [{"id": "catalog", "origin": "test catalog",
             "slots": ["CARROT", "MILK", "WHEAT", "FERTILIZER"]}]
QUIET = [{"id": "quiet", "origin": "test quiet operating stock",
          "stock": {"WHEAT": 0, "FERTILIZER": 0}}]


def history(bounds_by_lag, now=100):
    result = History()
    for lag, rows in bounds_by_lag.items():
        step = now - lag * result.period
        for product, lower, upper, reason in rows:
            admitted = lower if reason == "floor_censored" else upper
            result.add(Interval(step, product, lower, upper, lower, admitted, reason))
    return result


def build(rows, **kwargs):
    return build_interval_terminal_scenarios(
        history(rows), PRODUCTS, 100, slot_templates=TEMPLATE,
        unobserved_lots=QUIET, **kwargs)


class VectorTests(unittest.TestCase):
    def test_complete_joint_vectors_respect_capacity(self):
        vectors, count = enumerate_joint_vectors(
            [("CARROT", 1, 2), ("MILK", 1, 2)], 3, 32)
        self.assertEqual(count, 3)
        self.assertEqual(vectors, [(1, 1), (1, 2), (2, 1)])

    def test_limit_is_fail_closed_without_partial_vectors(self):
        vectors, count = enumerate_joint_vectors(
            [("CARROT", 0, 100), ("MILK", 0, 100)], 100, 32)
        self.assertIsNone(vectors)
        self.assertEqual(count, 33)

    def test_incompatible_lower_bounds_have_no_vector(self):
        vectors, count = enumerate_joint_vectors(
            [("CARROT", 2, 2), ("MILK", 2, 2)], 3, 32)
        self.assertEqual((vectors, count), ([], 0))


class FamilyTests(unittest.TestCase):
    def test_exact_three_lags_deduplicate_to_one_scenario(self):
        rows = {lag: [("CARROT", 1, 1, "identified"),
                      ("MILK", 2, 2, "identified")] for lag in (1, 2, 3)}
        result = build(rows)
        self.assertTrue(result["ready"])
        self.assertEqual(result["status"], "ready_interval_enumeration")
        self.assertEqual(len(result["scenarios"]), 1)
        self.assertEqual(len(result["scenarios"][0]["origin"]["witnesses"]), 3)
        self.assertEqual(result["scenarios"][0]["shed"], {"CARROT": 1, "MILK": 2})

    def test_interval_values_are_complete_not_independent_endpoints(self):
        rows = {lag: [("CARROT", 1, 2, "floor_censored"),
                      ("MILK", 1, 2, "floor_censored")] for lag in (1, 2, 3)}
        result = build(rows, capacity=3)
        vectors = {(row["shed"].get("CARROT", 0), row["shed"].get("MILK", 0))
                   for row in result["scenarios"]}
        self.assertEqual(vectors, {(1, 1), (1, 2), (2, 1)})
        self.assertNotIn((2, 2), vectors)

    def test_interval_vector_limit_returns_no_partial_scenarios(self):
        rows = {lag: [("CARROT", 0, 100, "floor_censored"),
                      ("MILK", 0, 100, "floor_censored")] for lag in (1, 2, 3)}
        result = build(rows)
        self.assertFalse(result["ready"])
        self.assertEqual(result["status"], "interval_vector_limit")
        self.assertEqual(result["scenarios"], [])
        self.assertGreaterEqual(result["unique_vectors_at_least"], 33)

    def test_missing_product_keeps_insufficient_history(self):
        rows = {
            1: [("CARROT", 1, 1, "identified"), ("MILK", 1, 1, "identified")],
            2: [("CARROT", 1, 1, "identified")],
            3: [("CARROT", 1, 1, "identified"), ("MILK", 1, 1, "identified")],
        }
        result = build(rows)
        self.assertFalse(result["ready"])
        self.assertEqual(result["joint_support"], 2)
        self.assertEqual(result["status"], "insufficient_interval_history")

    def test_explicit_operating_stock_tightens_remaining_capacity(self):
        rows = {lag: [("CARROT", 1, 3, "floor_censored"),
                      ("MILK", 0, 0, "identified")] for lag in (1, 2, 3)}
        lots = [{"id": "operating", "origin": "explicit test stock",
                 "stock": {"WHEAT": 98, "FERTILIZER": 0}}]
        result = build_interval_terminal_scenarios(
            history(rows), PRODUCTS, 100, slot_templates=TEMPLATE,
            unobserved_lots=lots, capacity=100)
        self.assertTrue(result["ready"])
        self.assertEqual({scenario["shed"]["CARROT"] for scenario in result["scenarios"]}, {1, 2})
        self.assertTrue(all(scenario["shed"]["WHEAT"] == 98 for scenario in result["scenarios"]))

    def test_incompatible_explicit_stock_fails_closed(self):
        rows = {lag: [("CARROT", 3, 3, "identified"),
                      ("MILK", 0, 0, "identified")] for lag in (1, 2, 3)}
        lots = [{"id": "operating", "origin": "explicit test stock",
                 "stock": {"WHEAT": 98, "FERTILIZER": 0}}]
        result = build_interval_terminal_scenarios(
            history(rows), PRODUCTS, 100, slot_templates=TEMPLATE,
            unobserved_lots=lots, capacity=100)
        self.assertFalse(result["ready"])
        self.assertEqual(result["status"], "joint_capacity_exceeded")
        self.assertEqual(result["scenarios"], [])

    def test_scenario_limit_returns_no_partial_family(self):
        rows = {lag: [("CARROT", 1, 1, "identified"),
                      ("MILK", 0, 0, "identified")] for lag in (1, 2, 3)}
        templates = [
            {"id": "front", "origin": "front", "slots": ["CARROT", "MILK", "WHEAT", "FERTILIZER"]},
            {"id": "back", "origin": "back", "slots": ["MILK", "CARROT", "WHEAT", "FERTILIZER"]},
        ]
        result = build_interval_terminal_scenarios(
            history(rows), PRODUCTS, 100, slot_templates=templates,
            unobserved_lots=QUIET, max_scenarios=1)
        self.assertFalse(result["ready"])
        self.assertEqual(result["status"], "scenario_limit")
        self.assertEqual(result["scenarios"], [])

    def test_candidate_lags_are_explicit_and_bounded(self):
        rows = {lag: [("CARROT", lag, lag, "identified"),
                      ("MILK", 0, 0, "identified")] for lag in (1, 2, 3, 4)}
        result = build_interval_terminal_scenarios(
            history(rows), PRODUCTS, 100, slot_templates=TEMPLATE,
            unobserved_lots=QUIET, candidate_lags=[1, 2, 3])
        self.assertEqual(result["historical_lags"], [1, 2, 3])
        self.assertEqual({row["shed"]["CARROT"] for row in result["scenarios"]}, {1, 2, 3})

    def test_invalid_interval_is_rejected(self):
        rows = {lag: [("CARROT", 1, 1, "invented"),
                      ("MILK", 0, 0, "identified")] for lag in (1, 2, 3)}
        with self.assertRaisesRegex(ValueError, "incompatible"):
            build(rows)


if __name__ == "__main__":
    unittest.main(verbosity=2)
