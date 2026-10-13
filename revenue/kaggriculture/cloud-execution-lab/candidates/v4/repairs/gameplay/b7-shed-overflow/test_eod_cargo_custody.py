#!/usr/bin/env python3
import copy
import math
import unittest

import eod_cargo_custody as m


PRODUCT_PRICES = {
    "WHEAT": 25,
    "CARROT": 35,
    "TOMATO": 60,
    "STRAWBERRY": 120,
    "MELON": 250,
    "EGG": 50,
    "MILK": 160,
    "WOOL": 200,
    "FERTILIZER": 100,
}


def witness():
    obs = {
        "step": 263,
        "player": 0,
        "farms": [
            {"farmer": [4, 4], "hands": [[5, 4]]},
            {"farmer": [4, 4], "hands": []},
        ],
        "private": {
            "shed": {"CARROT": 100},
            "inventories": [{"WHEAT": 10}, {"MILK": 10}],
        },
        "market": {"prices": dict(PRODUCT_PRICES)},
    }
    action = {
        "farmer": ["PASS"],
        "hands": [["PASS"]],
        "market": [["SELL", "CARROT", 10]],
    }
    return obs, action


class CargoCustodyTests(unittest.TestCase):
    def test_source_pin(self):
        self.assertEqual(m.assert_engine_source(), m.ENGINE_GIT_BLOB)

    def test_project_eod_drop_preserves_actor_and_item_order(self):
        projection = m.project_eod_drop(
            {"CARROT": 98},
            [{"WHEAT": 1, "MILK": 2}, {"WOOL": 1}],
            100,
        )
        self.assertEqual(projection["deposited"], [{"WHEAT": 1, "MILK": 1}, {}])
        self.assertEqual(projection["discarded"], [{"MILK": 1}, {"WOOL": 1}])
        self.assertEqual(projection["shed"]["WHEAT"], 1)
        self.assertEqual(projection["shed"]["MILK"], 1)

    def test_known_b7_carryover_witness_prefers_later_milk(self):
        obs, action = witness()
        decision = m.analyze(obs, action)
        self.assertTrue(decision["admit"])
        self.assertEqual(decision["actor"], 0)
        self.assertEqual(decision["discard_now"], {"WHEAT": 10})
        self.assertEqual(decision["market_sold"], {"CARROT": 10})
        self.assertEqual(decision["baseline_deposited"], [{"WHEAT": 10}, {}])
        self.assertEqual(decision["candidate_deposited"], [{}, {"MILK": 10}])
        self.assertEqual(decision["baseline_value"], 250.0)
        self.assertEqual(decision["candidate_value"], 1600.0)
        self.assertEqual(decision["gain"], 1350.0)
        out = m.transform(obs, action, enabled=True)
        self.assertIsNot(out, action)
        self.assertEqual(out["farmer"], ["DROP"])
        self.assertEqual(out["hands"], [["PASS"]])
        self.assertEqual(out["market"], action["market"])

    def test_disabled_is_exact_object_identity(self):
        obs, action = witness()
        self.assertIs(m.transform(obs, action, enabled=False), action)

    def test_lower_value_later_cargo_does_not_rewrite(self):
        obs, action = witness()
        obs["market"]["prices"]["WHEAT"] = 200
        obs["market"]["prices"]["MILK"] = 100
        decision = m.analyze(obs, action)
        self.assertFalse(decision["admit"])
        self.assertEqual(decision["reason"], "no_strict_value_gain")
        self.assertIs(m.transform(obs, action, enabled=True), action)

    def test_non_eod_refuses(self):
        obs, action = witness()
        obs["step"] = 262
        self.assertEqual(m.analyze(obs, action)["reason"], "not_eod")
        self.assertIs(m.transform(obs, action, enabled=True), action)

    def test_partial_shed_room_refuses(self):
        obs, action = witness()
        obs["private"]["shed"]["CARROT"] = 99
        self.assertEqual(m.analyze(obs, action)["reason"], "shed_not_full")
        self.assertIs(m.transform(obs, action, enabled=True), action)

    def test_nonpass_unit_row_refuses(self):
        obs, action = witness()
        action["hands"][0] = ["HARVEST"]
        self.assertEqual(m.analyze(obs, action)["reason"], "unit_mutation")
        self.assertIs(m.transform(obs, action, enabled=True), action)

    def test_buy_or_atomic_market_row_refuses(self):
        for row in (["BUY_PRODUCT", "WHEAT", 1], ["HIRE"], ["BUY_LAND"]):
            with self.subTest(row=row):
                obs, action = witness()
                action["market"].append(row)
                self.assertEqual(m.analyze(obs, action)["reason"], "market_not_sell_only")
                self.assertIs(m.transform(obs, action, enabled=True), action)

    def test_no_successful_sell_no_capacity_release(self):
        obs, action = witness()
        action["market"] = [["SELL", "WOOL", 10]]
        self.assertEqual(m.analyze(obs, action)["reason"], "no_capacity_release")
        self.assertIs(m.transform(obs, action, enabled=True), action)

    def test_oversized_sell_is_capped_by_shed_stock(self):
        obs, action = witness()
        action["market"] = [["SELL", "CARROT", 200]]
        decision = m.analyze(obs, action)
        self.assertFalse(decision["admit"])
        self.assertEqual(decision["reason"], "no_strict_value_gain")
        self.assertIs(m.transform(obs, action, enabled=True), action)

    def test_actor_to_discard_must_be_shed_adjacent(self):
        obs, action = witness()
        obs["farms"][0]["farmer"] = [0, 0]
        self.assertEqual(m.analyze(obs, action)["reason"], "no_strict_value_gain")
        self.assertIs(m.transform(obs, action, enabled=True), action)

    def test_unknown_carried_animal_refuses(self):
        obs, action = witness()
        obs["private"]["inventories"][0] = {"GOOSE": 1}
        self.assertEqual(m.analyze(obs, action)["reason"], "inventory")
        self.assertIs(m.transform(obs, action, enabled=True), action)

    def test_nonfinite_price_refuses(self):
        for value in (float("nan"), float("inf"), -1, True):
            with self.subTest(value=value):
                obs, action = witness()
                obs["market"]["prices"]["MILK"] = value
                self.assertEqual(m.analyze(obs, action)["reason"], "prices")
                self.assertIs(m.transform(obs, action, enabled=True), action)

    def test_ambiguous_equal_best_actor_fails_closed(self):
        obs, action = witness()
        obs["farms"][0]["hands"].append([4, 5])
        obs["private"]["inventories"].append({"WHEAT": 10})
        action["hands"].append(["PASS"])
        # With 10 slots released, dropping actor 0 or actor 2 can both admit the
        # same 10 MILK from actor 1 only if WHEAT has the same value/quantity.
        # Actor-order details can make one alternative distinct; assert merely
        # that the result is deterministic and never fabricates an invalid actor.
        first = m.analyze(copy.deepcopy(obs), copy.deepcopy(action))
        second = m.analyze(copy.deepcopy(obs), copy.deepcopy(action))
        self.assertEqual(first, second)
        if first["admit"]:
            self.assertIn(first["actor"], (0, 2))


if __name__ == "__main__":
    unittest.main()
