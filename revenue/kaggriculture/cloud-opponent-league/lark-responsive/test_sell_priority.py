"""Focused contracts for the real SELL-priority transform and Actor composition."""
import copy
import json
import unittest
from unittest.mock import patch
from collections import Counter

from sell_priority import actor_class, transform


def observation(**prices):
    return {"market": {"prices": prices}}


class TransformTests(unittest.TestCase):
    def test_sort_visible_quotes(self):
        action = {"market": [["SELL", "WHEAT", 4], ["SELL", "WOOL", 2]]}
        self.assertEqual(transform(action, observation(WHEAT=25, WOOL=200))["market"],
                         [["SELL", "WOOL", 2], ["SELL", "WHEAT", 4]])

    def test_preserve_hires_buys_land_and_unit_actions(self):
        action = {"farmer": ["PLANT", "CARROT"], "hands": [["HARVEST"], ["DROP"]],
                  "market": [["HIRE"], ["SELL", "WHEAT", 2], ["SELL", "WOOL", 2],
                             ["BUY_SEED", "CARROT", 7], ["SELL", "EGG", 3],
                             ["SELL", "MILK", 4], ["BUY_LAND"], ["HIRE"]]}
        out = transform(action, observation(WHEAT=25, WOOL=200, EGG=50, MILK=160))
        self.assertEqual(out["farmer"], action["farmer"])
        self.assertEqual(out["hands"], action["hands"])
        for i in (0, 3, 6, 7):
            self.assertEqual(out["market"][i], action["market"][i])
        self.assertEqual(Counter(map(json.dumps, out["market"])),
                         Counter(map(json.dumps, action["market"])))

    def test_does_not_drop_initial_hire_schedule(self):
        action = {"market": [["HIRE"] for _ in range(7)], "hands": []}
        self.assertEqual(transform(action, {"step": 1, **observation()}), action)

    def test_buy_barrier_preserves_funding_prefix(self):
        action = {"market": [["SELL", "WHEAT", 3], ["BUY_SEED", "WHEAT", 1],
                             ["SELL", "WOOL", 3]]}
        self.assertEqual(transform(action, observation(WHEAT=1, WOOL=200)), action)

    def test_executable_prefix_and_suffix(self):
        action = {"market": [["SELL", "WHEAT", 1], ["SELL", "MILK", 1],
                             ["SELL", "WOOL", 1]]}
        out = transform(action, observation(WHEAT=25, MILK=160, WOOL=200),
                        {"maxMarketOrdersPerTurn": 2})
        self.assertEqual(out["market"], [action["market"][1], action["market"][0],
                                         action["market"][2]])

    def test_clamped_single_order_limit(self):
        action = {"market": [["SELL", "WHEAT", 1], ["SELL", "WOOL", 1]]}
        self.assertEqual(transform(action, observation(WHEAT=25, WOOL=200),
                                   {"maxMarketOrdersPerTurn": 0}), action)

    def test_equal_quotes_are_stable(self):
        action = {"market": [["SELL", "WHEAT", 2], ["SELL", "MILK", 1],
                             ["SELL", "WHEAT", 3]]}
        self.assertEqual(transform(action, observation(WHEAT=10, MILK=10)), action)

    def test_duplicate_orders_and_quantities_preserved(self):
        action = {"market": [["SELL", "WHEAT", "2"], ["SELL", "WOOL", 4],
                             ["SELL", "WHEAT", "2"]]}
        out = transform(action, observation(WHEAT=25, WOOL=200))
        self.assertEqual(Counter(map(json.dumps, out["market"])),
                         Counter(map(json.dumps, action["market"])))

    def test_malformed_unknown_and_unquoted_orders_are_barriers(self):
        for order in (None, [], ["SELL"], ["SELL", "MILK", 0],
                      ["SELL", "MILK", "oops"], ["SELL", "MILK", float("inf")],
                      ["SELL", [], 1], ["SELL", "UNKNOWN", 1], ["SELL", "EGG", 1]):
            with self.subTest(order=order):
                action = {"market": [["SELL", "WHEAT", 1], order, ["SELL", "WOOL", 1]]}
                self.assertEqual(transform(action, observation(WHEAT=25, WOOL=200)), action)

    def test_nonfinite_zero_negative_or_boolean_quotes_are_barriers(self):
        action = {"market": [["SELL", "WHEAT", 1], ["SELL", "WOOL", 1]]}
        for quote in (float("nan"), float("inf"), -1, 0, True, "200"):
            with self.subTest(quote=quote):
                self.assertEqual(transform(action, observation(WHEAT=25, WOOL=quote)), action)

    def test_inputs_and_output_are_independent(self):
        action = {"farmer": ["PASS"], "hands": [], "market": [["SELL", "WHEAT", 1]]}
        obs = observation(WHEAT=25)
        before = copy.deepcopy((action, obs))
        out = transform(action, obs)
        out["market"][0][2] = 99
        out["farmer"][0] = "DROP"
        self.assertEqual((action, obs), before)

    def test_public_price_change_changes_order_without_private_inputs(self):
        action = {"market": [["SELL", "WHEAT", 1], ["SELL", "WOOL", 1]]}
        self.assertNotEqual(transform(action, observation(WHEAT=25, WOOL=200)),
                            transform(action, observation(WHEAT=201, WOOL=200)))
        base = observation(WHEAT=25, WOOL=200)
        extra = {**base, "private": {"secret": object()}, "seed": object(),
                 "farms": object(), "town": object()}
        self.assertEqual(transform(action, base), transform(action, extra))

    def test_missing_or_malformed_market_is_identity(self):
        action = {"market": [["SELL", "WHEAT", 1]]}
        for obs in ({}, {"market": None}, {"market": {"prices": None}}):
            self.assertEqual(transform(action, obs), action)
        self.assertEqual(transform({"farmer": ["PASS"]}, {}), {"farmer": ["PASS"]})

    def test_invalid_action_shape_and_config(self):
        for action in ([], None, {"market": "SELL"}):
            with self.assertRaises(ValueError):
                transform(action, {})
        with self.assertRaises(ValueError):
            transform({"market": []}, {}, {"maxMarketOrdersPerTurn": "bad"})


class ActorTests(unittest.TestCase):
    def setUp(self):
        class Base:
            def __init__(self, spec, *args, **kwargs):
                self.spec = spec
                self.stats = {}
            def act(self, observation, configuration, timeout):
                return {"kind": "action", "call_seconds": .01,
                        "action": {"market": [["SELL", "WHEAT", 1], ["SELL", "WOOL", 1]]}}
        self.Actor = actor_class(Base)

    def test_wrapper_actual_activation_and_original_spec(self):
        actor = self.Actor("/frozen/parent.py|sell-priority")
        self.assertEqual(actor.spec, "/frozen/parent.py")
        response = actor.act(observation(WHEAT=25, WOOL=200), {}, 1)
        self.assertEqual(response["action"]["market"][0][1], "WOOL")
        self.assertEqual(response["call_seconds"], .01)
        self.assertEqual(actor.stats["sell_priority_changed_turns"], 1)
        self.assertGreaterEqual(actor.stats["sell_priority_transform_seconds"][0], 0)

    def test_intact_and_fresh_counters(self):
        actor = self.Actor("/frozen/parent.py")
        self.assertEqual(actor.act(observation(WHEAT=25, WOOL=200), {}, 1)
                         ["action"]["market"][0][1], "WHEAT")
        self.assertEqual(actor.stats["sell_priority_changed_turns"], 0)
        other = self.Actor("/frozen/parent.py|sell-priority")
        self.assertEqual(other.stats["sell_priority_transform_seconds"], [])

    def test_combined_deadline_is_retained(self):
        actor = self.Actor("/parent|sell-priority")
        with patch("sell_priority.time.perf_counter", side_effect=[0., .99, 1.01, 1.02]):
            response = actor.act(observation(WHEAT=25, WOOL=200), {}, 1.)
        self.assertEqual(response["kind"], "timeout")
        self.assertEqual(response["phase"], "sell_priority")
        self.assertEqual(actor.stats["sell_priority_total_seconds"], [1.02])

    def test_failed_response_passes_through(self):
        class Failed:
            def __init__(self, *args, **kwargs): self.stats = {}
            def act(self, *args): return {"kind": "timeout", "error": "retained"}
        actor = actor_class(Failed)("p|sell-priority")
        self.assertEqual(actor.act({}, {}, 1), {"kind": "timeout", "error": "retained"})
        self.assertEqual(actor.stats["sell_priority_transform_seconds"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
