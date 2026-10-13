"""Official engine SELL grammar shared by sell-priority and pressure-priority."""
import copy
import unittest

from pressure_priority import transform as pressure_transform
from sell_priority import transform as sell_transform


PRICES = {"WHEAT": 25, "MILK": 160, "WOOL": 200}
BASE = {"WHEAT": 25, "MILK": 160, "WOOL": 200}
SLOPE = {"WHEAT": 1, "MILK": 2, "WOOL": 0}


def observation():
    return {
        "step": 10,
        "market": {
            "inventory": {"WHEAT": 0, "MILK": 0, "WOOL": 0},
            "prices": dict(PRICES),
        },
    }


def curve(item, stock, params=None):
    return max(1, BASE[item] - SLOPE[item] * stock)


class MarketPressureGrammarExactnessTests(unittest.TestCase):
    def test_engine_accepted_quantity_coercions_remain_eligible_and_byte_exact(self):
        for quantity in (True, 2.0, 2.9, "2"):
            with self.subTest(quantity=quantity):
                milk = ["SELL", "MILK", quantity]
                sell_action = {
                    "market": [
                        ["SELL", "WHEAT", 1],
                        list(milk),
                        ["SELL", "WOOL", 1],
                    ]
                }
                sell_before = copy.deepcopy(sell_action)
                self.assertEqual(
                    sell_transform(sell_action, observation())["market"],
                    [["SELL", "WOOL", 1], milk, ["SELL", "WHEAT", 1]],
                )
                self.assertEqual(sell_action, sell_before)

                pressure_action = {
                    "market": [
                        ["SELL", "WOOL", 1],
                        list(milk),
                        ["SELL", "WHEAT", 1],
                    ]
                }
                pressure_before = copy.deepcopy(pressure_action)
                self.assertEqual(
                    pressure_transform(
                        pressure_action, observation(), {}, quote=curve
                    )["market"],
                    [milk, ["SELL", "WHEAT", 1], ["SELL", "WOOL", 1]],
                )
                self.assertEqual(pressure_action, pressure_before)

    def test_engine_accepted_trailing_fields_remain_eligible_and_byte_exact(self):
        milk = ["SELL", "MILK", 2, "ignored-by-engine", {"metadata": True}]
        sell_action = {
            "market": [
                ["SELL", "WHEAT", 1],
                copy.deepcopy(milk),
                ["SELL", "WOOL", 1],
            ]
        }
        sell_before = copy.deepcopy(sell_action)
        self.assertEqual(
            sell_transform(sell_action, observation())["market"],
            [["SELL", "WOOL", 1], milk, ["SELL", "WHEAT", 1]],
        )
        self.assertEqual(sell_action, sell_before)

        pressure_action = {
            "market": [
                ["SELL", "WOOL", 1],
                copy.deepcopy(milk),
                ["SELL", "WHEAT", 1],
            ]
        }
        pressure_before = copy.deepcopy(pressure_action)
        self.assertEqual(
            pressure_transform(pressure_action, observation(), {}, quote=curve)["market"],
            [milk, ["SELL", "WHEAT", 1], ["SELL", "WOOL", 1]],
        )
        self.assertEqual(pressure_action, pressure_before)

    def test_engine_rejected_nonpositive_or_uncoercible_quantities_are_barriers(self):
        for quantity in (False, 0, -1, 0.5, "0", "2.5", None, []):
            with self.subTest(quantity=quantity):
                sell_action = {
                    "market": [
                        ["SELL", "WHEAT", 1],
                        ["SELL", "MILK", quantity],
                        ["SELL", "WOOL", 1],
                    ]
                }
                self.assertEqual(sell_transform(sell_action, observation()), sell_action)

                pressure_action = {
                    "market": [
                        ["SELL", "WOOL", 1],
                        ["SELL", "MILK", quantity],
                        ["SELL", "WHEAT", 1],
                    ]
                }
                self.assertEqual(
                    pressure_transform(
                        pressure_action, observation(), {}, quote=curve
                    ),
                    pressure_action,
                )

    def test_engine_inert_nonlist_market_container_is_transform_noop(self):
        for market in (17, "SELL", ("SELL", "MILK", 2), {"row": "SELL"}):
            with self.subTest(transform="sell", market=market):
                action = {"farmer": ["PASS"], "hands": [], "market": market}
                before = copy.deepcopy(action)
                result = sell_transform(action, observation())
                self.assertEqual(result, action)
                self.assertIsNot(result, action)
                self.assertEqual(action, before)
            with self.subTest(transform="pressure", market=market):
                action = {"farmer": ["PASS"], "hands": [], "market": market}
                before = copy.deepcopy(action)
                result = pressure_transform(action, observation(), {}, quote=curve)
                self.assertEqual(result, action)
                self.assertIsNot(result, action)
                self.assertEqual(action, before)

    def test_valid_plain_integer_rows_keep_existing_behavior(self):
        sell_action = {
            "market": [
                ["SELL", "WHEAT", 1],
                ["SELL", "WOOL", 1],
            ]
        }
        self.assertEqual(
            sell_transform(sell_action, observation())["market"],
            [["SELL", "WOOL", 1], ["SELL", "WHEAT", 1]],
        )

        pressure_action = {
            "market": [
                ["SELL", "WOOL", 1],
                ["SELL", "MILK", 2],
                ["SELL", "WHEAT", 1],
            ]
        }
        self.assertEqual(
            pressure_transform(pressure_action, observation(), {}, quote=curve)["market"],
            [["SELL", "MILK", 2], ["SELL", "WHEAT", 1], ["SELL", "WOOL", 1]],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
