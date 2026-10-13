# SPDX-License-Identifier: Apache-2.0
"""Engine-parity regressions for the deadline terminal fallback."""
import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "reference/titan-current/deadline_adapter.py"
SPEC = importlib.util.spec_from_file_location("deadline_adapter_under_test", SOURCE)
DEADLINE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DEADLINE)


def observation(*, shed, inventory=None):
    tiles = [[None for _ in range(10)] for _ in range(10)]
    return {
        "player": 0,
        "farms": [{"farmer": [4, 4], "hands": [], "tiles": tiles}],
        "private": {
            "shed": dict(shed),
            "inventories": [dict(inventory or {})],
        },
    }


class DeadlineTerminalMarketParityTests(unittest.TestCase):
    def test_engine_effective_market_cap_clamps_zero_and_negative_to_one(self):
        obs = observation(shed={"GOOSE": 4, "WHEAT": 2, "CARROT": 3})
        expected = [["SELL", "WHEAT", 2]]
        for limit in (0, -3):
            with self.subTest(limit=limit):
                action = DEADLINE.terminal_liquidation_fallback(
                    obs, {"maxMarketOrdersPerTurn": limit}
                )
                self.assertEqual(action["market"], expected)

    def test_unsaleable_animals_are_not_emitted_as_sell_rows(self):
        obs = observation(
            shed={"GOOSE": 2, "WHEAT": 3, "COW": 1, "MILK": 4, "SHEEP": 5}
        )
        action = DEADLINE.terminal_liquidation_fallback(obs, {})
        self.assertEqual(
            action["market"],
            [["SELL", "WHEAT", 3], ["SELL", "MILK", 4]],
        )

    def test_animal_stock_still_consumes_shed_capacity_for_terminal_drop(self):
        obs = observation(shed={"GOOSE": 99}, inventory={"WHEAT": 2})
        action = DEADLINE.terminal_liquidation_fallback(
            obs, {"shedCapacity": 100, "maxMarketOrdersPerTurn": 10}
        )
        self.assertEqual(action["farmer"], ["DROP"])
        self.assertEqual(action["market"], [["SELL", "WHEAT", 1]])


if __name__ == "__main__":
    unittest.main(verbosity=2)
