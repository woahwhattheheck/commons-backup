# SPDX-License-Identifier: Apache-2.0
"""Executable raw-prefix contracts for the existing H3c rescue.

Run in a materialized package (or with its overlay on PYTHONPATH):
    python -m unittest discover -s checks -p test_v4_h3c_market_prefix.py
The assertions remain active under python -O.
"""
from __future__ import annotations

import copy
import unittest
from types import SimpleNamespace

import h3c_goose_eod_cap_rescue as h3c


def fixture(*, player=0, hand=False, shed_units=0):
    tiles = [[{"kind": "EMPTY"} for _ in range(10)] for _ in range(10)]
    tiles[1][1] = {
        "kind": "COOP", "animal": "GOOSE", "placed_day": 0,
        "yield_units": 4, "consecutive_unfed": 0, "fed_today": True,
        "cared_today": True, "fertilizer_available": True,
        "pending_care_bonus": 1,
    }
    farm = {"farmer": [0, 0] if hand else [1, 1],
            "hands": [[1, 1]] if hand else [], "tiles": tiles}
    farms = [copy.deepcopy(farm), copy.deepcopy(farm)]
    observation = {
        "step": 239, "player": player, "farms": farms,
        "private": {"inventories": [{}, {}] if hand else [{}],
                    "shed": {"WHEAT": shed_units}},
    }
    action = {"farmer": ["PASS"] if hand else ["COLLECT_FERTILIZER"],
              "hands": [["COLLECT_FERTILIZER"]] if hand else [],
              "market": []}
    configuration = dict(h3c.STANDARD_CONFIG, episodeSteps=720)
    return action, observation, configuration


class TestH3cExecutableMarketPrefix(unittest.TestCase):
    def setUp(self):
        h3c.telemetry.clear()

    def rescue(self, action, observation, configuration):
        return h3c.apply_goose_eod_cap_rescue(
            action, observation, configuration, enabled=True)

    def check_harvest(self, result, parent, *, hand=False):
        self.assertIsNot(result, parent)
        self.assertEqual(result["hands"][0] if hand else result["farmer"],
                         ["HARVEST"])
        self.assertEqual(result["market"], parent["market"])

    def test_incumbent_empty_market_positive_control(self):
        action, observation, configuration = fixture()
        self.check_harvest(self.rescue(action, observation, configuration), action)

    def test_buy_product_at_raw_index_nine_still_blocks(self):
        action, observation, configuration = fixture()
        action["market"] = [[] for _ in range(9)] + [["BUY_PRODUCT", "WHEAT", 1]]
        self.assertIs(self.rescue(action, observation, configuration), action)
        self.assertEqual(h3c.telemetry["market_inflow_block"], 1)

    def test_buy_product_at_raw_index_ten_is_inert(self):
        action, observation, configuration = fixture()
        action["market"] = [[] for _ in range(10)] + [["BUY_PRODUCT", "WHEAT", 1]]
        self.check_harvest(self.rescue(action, observation, configuration), action)
        self.assertEqual(h3c.telemetry["market_inflow_block"], 0)

    def test_buy_animal_boundary(self):
        for index in (9, 10, 11):
            with self.subTest(index=index):
                action, observation, configuration = fixture()
                action["market"] = [[] for _ in range(index)] + [["BUY_ANIMAL", "GOOSE", 1]]
                result = self.rescue(action, observation, configuration)
                if index < 10:
                    self.assertIs(result, action)
                else:
                    self.check_harvest(result, action)

    def test_malformed_executable_rows_still_block(self):
        for bad in (None, 0, False, "BUY_PRODUCT", {}, ("SELL", "EGG", 1), [1]):
            with self.subTest(bad=bad):
                action, observation, configuration = fixture()
                action["market"] = [[] for _ in range(9)] + [bad]
                self.assertIs(self.rescue(action, observation, configuration), action)

    def test_malformed_dead_suffix_is_not_execution_evidence(self):
        for bad in (None, 0, False, "BUY_PRODUCT", {}, ("SELL", "EGG", 1), [1]):
            with self.subTest(bad=bad):
                action, observation, configuration = fixture()
                action["market"] = [[] for _ in range(10)] + [bad]
                self.check_harvest(self.rescue(action, observation, configuration), action)

    def test_raw_placeholders_count_before_any_row_inspection(self):
        action, observation, configuration = fixture()
        action["market"] = [[], ["SELL", "EGG", 1]] + [[] for _ in range(8)]
        action["market"] += [["BUY_PRODUCT", "FERTILIZER", 100]]
        self.check_harvest(self.rescue(action, observation, configuration), action)

    def test_all_raw_market_rows_and_inputs_are_preserved(self):
        action, observation, configuration = fixture()
        action["market"] = [[] for _ in range(10)] + [
            ["BUY_PRODUCT", "WHEAT", 1], None, ["BUY_ANIMAL", "COW", 1],
            {"inert": [1, 2, 3]}, ["SELL", "EGG", 7],
        ]
        before = copy.deepcopy((action, observation, configuration))
        result = self.rescue(action, observation, configuration)
        self.check_harvest(result, action)
        self.assertEqual((action, observation, configuration), before)
        self.assertEqual(len(result["market"]), 15)
        result["market"][13]["inert"].append(4)
        self.assertEqual((action, observation, configuration), before)

    def test_suffix_cannot_hide_executable_inflow(self):
        action, observation, configuration = fixture()
        action["market"] = [["BUY_PRODUCT", "WHEAT", 1]] + [[] for _ in range(9)]
        action["market"] += [None, ["SELL", "WHEAT", 100]]
        self.assertIs(self.rescue(action, observation, configuration), action)

    def test_whole_farm_capacity_guard_is_unchanged(self):
        for shed_units in (96, 97, 100):
            with self.subTest(shed_units=shed_units):
                action, observation, configuration = fixture(shed_units=shed_units)
                action["market"] = [[] for _ in range(10)] + [["BUY_PRODUCT", "WHEAT", 1]]
                result = self.rescue(action, observation, configuration)
                if shed_units == 96:
                    self.check_harvest(result, action)
                else:
                    self.assertIs(result, action)

    def test_config_gate_is_not_widened(self):
        for cap in (0, 1, 9, 11, True, 10.0, "10", None):
            with self.subTest(cap=cap):
                action, observation, configuration = fixture()
                configuration["maxMarketOrdersPerTurn"] = cap
                action["market"] = [[] for _ in range(10)] + [["BUY_PRODUCT", "WHEAT", 1]]
                self.assertIs(self.rescue(action, observation, configuration), action)

    def test_attribute_configuration_surface(self):
        action, observation, configuration = fixture()
        action["market"] = [[] for _ in range(10)] + [["BUY_ANIMAL", "GOOSE", 1]]
        result = self.rescue(action, observation, SimpleNamespace(**configuration))
        self.check_harvest(result, action)

    def test_both_seats_and_farmer_hand_surfaces(self):
        for player in (0, 1):
            for hand in (False, True):
                with self.subTest(player=player, hand=hand):
                    action, observation, configuration = fixture(player=player, hand=hand)
                    action["market"] = [[] for _ in range(10)] + [["BUY_PRODUCT", "WHEAT", 1]]
                    self.check_harvest(self.rescue(action, observation, configuration), action, hand=hand)

    def test_disabled_and_default_install_preserve_parent_identity(self):
        action, observation, configuration = fixture()
        action["market"] = [None] * 11
        self.assertIs(h3c.apply_goose_eod_cap_rescue(action, observation, configuration), action)
        self.assertIs(h3c.apply_goose_eod_cap_rescue(action, observation, configuration, enabled=False), action)
        self.assertIs(h3c.install(lambda *_: action)(observation, configuration), action)
        self.assertEqual(dict(h3c.telemetry), {})

    def test_prefix_equivalence_matrix(self):
        # Appending any inert suffix must preserve the decision and telemetry
        # of the exact executable prefix, without trimming the returned market.
        prefixes = [
            [[] for _ in range(10)],
            [["SELL", "EGG", 1]] + [[] for _ in range(9)],
            [[] for _ in range(9)] + [["BUY_PRODUCT", "WHEAT", 1]],
            [[] for _ in range(9)] + [["BUY_ANIMAL", "GOOSE", 1]],
            [[] for _ in range(9)] + [None],
        ]
        suffixes = [
            [], [["BUY_PRODUCT", "WHEAT", 100]], [["BUY_ANIMAL", "COW", 1]],
            [None, {}, False, "bad", [1]], [[] for _ in range(25)],
        ]
        for prefix in prefixes:
            for suffix in suffixes:
                with self.subTest(prefix=prefix, suffix=suffix):
                    action, observation, configuration = fixture()
                    action["market"] = copy.deepcopy(prefix)
                    h3c.telemetry.clear()
                    baseline = self.rescue(action, observation, configuration)
                    expected_telemetry = dict(h3c.telemetry)
                    extended = copy.deepcopy(action)
                    extended["market"] += copy.deepcopy(suffix)
                    h3c.telemetry.clear()
                    actual = self.rescue(extended, observation, configuration)
                    self.assertEqual(actual["farmer"], baseline["farmer"])
                    self.assertEqual(actual["hands"], baseline["hands"])
                    self.assertEqual(actual is extended, baseline is action)
                    self.assertEqual(actual["market"], extended["market"])
                    self.assertEqual(dict(h3c.telemetry), expected_telemetry)


if __name__ == "__main__":
    unittest.main()
