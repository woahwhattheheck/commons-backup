# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
import unittest

import candidate
from market_prefix_rescue import is_engine_executable_order, market_limit, rescue_market_prefix


class ConfigObject:
    maxMarketOrdersPerTurn = 2


class MarketPrefixRescueTests(unittest.TestCase):
    def test_rescues_tail_order_across_exact_blank_suffix(self):
        action = {
            "farmer": ["PASS"],
            "market": [["HIRE"], [], ["BUY_LAND"], ["SELL", "WHEAT", 3]],
            "opaque": {"keep": True},
        }
        original = deepcopy(action)
        output, report = rescue_market_prefix(action, {"maxMarketOrdersPerTurn": 2})
        self.assertTrue(report["changed"])
        self.assertEqual(output["market"], [
            ["HIRE"], ["BUY_LAND"], ["SELL", "WHEAT", 3], []
        ])
        self.assertEqual(action, original)
        self.assertEqual(output["opaque"], action["opaque"])
        self.assertEqual(report["rescued_orders"][0]["from_index"], 2)
        self.assertEqual(report["rescued_orders"][0]["to_index"], 1)
        self.assertEqual(report["prefix_executable_before"], 1)
        self.assertEqual(report["prefix_executable_after"], 2)

    def test_preserves_all_nonempty_values_and_relative_order(self):
        rows = [["SELL", "EGG", 2], {"opaque": 1}, [], ["BUY_SEED", "WHEAT", 1], [], ["HIRE"]]
        output, report = rescue_market_prefix({"market": deepcopy(rows)}, {"maxMarketOrdersPerTurn": 3})
        self.assertTrue(report["changed"])
        self.assertEqual([row for row in output["market"] if row != []], [row for row in rows if row != []])
        self.assertEqual(len(output["market"]), len(rows))
        self.assertEqual(sum(row == [] for row in output["market"]), 2)
        # Already-live rows keep absolute indices under suffix-only activation.
        self.assertEqual(output["market"][0], rows[0])
        self.assertEqual(output["market"][1], rows[1])

    def test_interior_blank_refused_no_retiming(self):
        # Review witness shape: interior [] would retime already-live rows.
        original = [
            [],
            ["BUY_PRODUCT", "WHEAT", 1],
            ["HIRE"],
            ["BUY_SEED", "WHEAT", 1],
        ]
        action = {"market": deepcopy(original)}
        output, report = rescue_market_prefix(action, {"maxMarketOrdersPerTurn": 3})
        self.assertIs(output, action)
        self.assertFalse(report["changed"])
        self.assertEqual(report["reason"], "interior_blank_refused_to_avoid_retiming")
        self.assertEqual(report["blank_prefix_slots"], [0])

    def test_does_not_retime_blank_without_executable_tail(self):
        action = {"market": [["HIRE"], [], ["UNKNOWN", "X", 1], ["SELL", "WHEAT", 0]]}
        output, report = rescue_market_prefix(action, {"maxMarketOrdersPerTurn": 2})
        self.assertIs(output, action)
        self.assertFalse(report["changed"])
        self.assertEqual(report["reason"], "no_executable_tail_order_crosses_cap")

    def test_blank_outside_prefix_is_unchanged(self):
        action = {"market": [["HIRE"], ["BUY_LAND"], [], ["SELL", "WHEAT", 1]]}
        output, report = rescue_market_prefix(action, {"maxMarketOrdersPerTurn": 2})
        self.assertIs(output, action)
        self.assertEqual(report["reason"], "no_exact_blank_in_prefix")

    def test_idempotent(self):
        action = {"market": [["HIRE"], [], ["BUY_LAND"]]}
        first, first_report = rescue_market_prefix(action, ConfigObject())
        second, second_report = rescue_market_prefix(first, ConfigObject())
        self.assertTrue(first_report["changed"])
        self.assertIs(second, first)
        self.assertFalse(second_report["changed"])
        self.assertEqual(second_report["reason"], "no_exact_blank_in_prefix")

    def test_fail_closed_for_non_object_or_non_list(self):
        for action in (None, [], "bad"):
            output, report = rescue_market_prefix(action)
            self.assertIs(output, action)
            self.assertEqual(report["reason"], "action_not_object")
        action = {"market": "bad"}
        output, report = rescue_market_prefix(action)
        self.assertIs(output, action)
        self.assertEqual(report["reason"], "market_not_list")

    def test_engine_order_classifier(self):
        accepted = [
            ["HIRE"], ["BUY_LAND"], ["BUY_SEED", "WHEAT", 1],
            ["BUY_PRODUCT", "FERTILIZER", "2"], ["BUY_ANIMAL", "SHEEP", 1],
            ["SELL", "WOOL", 3],
        ]
        rejected = [
            [], None, ["PASS"], ["SELL", "WOOL", 0], ["SELL", "NOT_A_PRODUCT", 1],
            ["BUY_PRODUCT", "MILK", 1], ["BUY_SEED", "WHEAT"],
        ]
        self.assertTrue(all(is_engine_executable_order(row) for row in accepted))
        self.assertFalse(any(is_engine_executable_order(row) for row in rejected))

    def test_limit_mirrors_engine_floor_and_struct_access(self):
        self.assertEqual(market_limit({"maxMarketOrdersPerTurn": 0}), 1)
        self.assertEqual(market_limit(ConfigObject()), 2)
        self.assertEqual(market_limit({"maxMarketOrdersPerTurn": "4"}), 4)
        self.assertEqual(market_limit({"maxMarketOrdersPerTurn": "bad"}), 10)

    def test_candidate_production_entrypoint_never_emits_marker(self):
        base_action = {"farmer": ["PASS"], "market": [["HIRE"], [], ["BUY_LAND"]]}
        previous = candidate._BASE_MODULE
        candidate._BASE_MODULE = SimpleNamespace(agent=lambda observation, configuration=None: deepcopy(base_action))
        try:
            output = candidate.agent({"step": 7, "player": 0}, {"maxMarketOrdersPerTurn": 2})
            self.assertNotIn(candidate.DIAGNOSTIC_KEY, output)
            self.assertEqual(output["market"][:2], [["HIRE"], ["BUY_LAND"]])
        finally:
            candidate._BASE_MODULE = previous

    def test_instrumented_entrypoint_marks_only_real_edits(self):
        previous = candidate._BASE_MODULE
        actions = iter([
            {"market": [["HIRE"], [], ["BUY_LAND"]]},
            {"market": [["HIRE"], ["BUY_LAND"]]},
        ])
        candidate._BASE_MODULE = SimpleNamespace(agent=lambda observation, configuration=None: deepcopy(next(actions)))
        try:
            changed = candidate.instrumented_agent(
                {"step": 11, "player": 1}, {"maxMarketOrdersPerTurn": 2}
            )
            self.assertTrue(changed[candidate.DIAGNOSTIC_KEY]["changed"])
            self.assertEqual(changed[candidate.DIAGNOSTIC_KEY]["step"], 11)
            self.assertEqual(changed[candidate.DIAGNOSTIC_KEY]["player"], 1)
            unchanged = candidate.instrumented_agent(
                {"step": 12, "player": 1}, {"maxMarketOrdersPerTurn": 2}
            )
            self.assertNotIn(candidate.DIAGNOSTIC_KEY, unchanged)
        finally:
            candidate._BASE_MODULE = previous


if __name__ == "__main__":
    unittest.main()
