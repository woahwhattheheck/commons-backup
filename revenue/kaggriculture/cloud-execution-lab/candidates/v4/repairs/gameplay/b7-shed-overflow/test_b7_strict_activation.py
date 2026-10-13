#!/usr/bin/env python3
import copy
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
    observation = {
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
    return observation, action


class StrictActivationTests(unittest.TestCase):
    def setUp(self):
        m.telemetry.clear()

    def test_only_literal_true_can_rewrite(self):
        poison_values = (
            False,
            None,
            0,
            1,
            0.0,
            1.0,
            "false",
            "",
            [],
            [True],
            {},
            {"enabled": True},
        )
        for enabled in poison_values:
            with self.subTest(enabled=repr(enabled)):
                observation, action = witness()
                before_observation = copy.deepcopy(observation)
                before_action = copy.deepcopy(action)
                out = m.transform(observation, action, enabled=enabled)
                self.assertIs(out, action)
                self.assertEqual(observation, before_observation)
                self.assertEqual(action, before_action)

        observation, action = witness()
        out = m.transform(observation, action, enabled=True)
        self.assertIsNot(out, action)
        self.assertEqual(out["farmer"], ["DROP"])
        self.assertEqual(action["farmer"], ["PASS"])

    def test_invalid_truthy_values_are_accounted_without_activation(self):
        observation, action = witness()
        self.assertIs(m.transform(observation, action, enabled="false"), action)
        self.assertEqual(m.telemetry["disabled"], 1)
        self.assertEqual(m.telemetry["invalid_enabled"], 1)
        self.assertEqual(m.telemetry["changed_actions"], 0)

    def test_install_marker_and_wrapper_use_same_literal_true_contract(self):
        for enabled, expected in (("false", False), (1, False), (1.0, False), (True, True)):
            with self.subTest(enabled=repr(enabled)):
                observation, action = witness()

                def parent(_observation, _configuration=None, *, _action=action):
                    return _action

                agent = m.install(parent, enabled=enabled)
                self.assertIs(agent.b7_custody_enabled, expected)
                out = agent(observation)
                if expected:
                    self.assertIsNot(out, action)
                    self.assertEqual(out["farmer"], ["DROP"])
                else:
                    self.assertIs(out, action)


if __name__ == "__main__":
    unittest.main()
