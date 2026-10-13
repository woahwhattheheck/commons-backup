# SPDX-License-Identifier: Apache-2.0
import copy
import importlib.util
from pathlib import Path
import unittest
import time

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("economic_runner", HERE / "runner.py")
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)

adapter_spec = importlib.util.spec_from_file_location("deadline_adapter", HERE / "deadline_adapter.py")
D = importlib.util.module_from_spec(adapter_spec)
adapter_spec.loader.exec_module(D)


class RunnerTests(unittest.TestCase):
    def test_known_order_cost_keeps_sequence(self):
        obs = {"player": 0, "farms": [{"money": 170, "hires_today": 0,
                "unlocked_quadrants": ["NW"]}], "market": {"prices": {"WHEAT": 25}}}
        cfg = {"farmHandCostMult": 1}
        action = {"market": [["BUY_SEED", "WHEAT", 17], ["HIRE"]]}
        self.assertEqual(R.action_cost(action, obs, cfg), 171)

    def test_summary_counts_cash_and_timeouts(self):
        games = [
            {"arm": "x", "margin": 1, "own_cash": 4, "rival_cash": 3,
             "timeouts": 1, "errors": [], "max_call_s": 1.0, "p99_call_s": .1},
            {"arm": "x", "margin": -2, "own_cash": 2, "rival_cash": 4,
             "timeouts": 0, "errors": [], "max_call_s": .2, "p99_call_s": .05},
        ]
        got = R.summarize(copy.deepcopy(games))["x"]
        self.assertEqual((got["wins"], got["ties"], got["losses"]), (1, 0, 1))
        self.assertEqual(got["timeouts"], 1)
        self.assertEqual(got["mean_own_cash"], 3)

    def test_transform_timeout_returns_exact_selected_action(self):
        selected = {"farmer": ["WEST"], "hands": [["CARE"]],
                    "market": [["SELL", "MILK", 12]]}
        class Production:
            def act(self, _obs):
                return copy.deepcopy(selected)
        class Integrated:
            production = Production()
            diagnostics = {}
            def transform(self, *_args, **_kwargs):
                raise AssertionError("controlled delay should interrupt before transform")
        def delay(*_args):
            time.sleep(.03)
        guarded = D.DeadlineFallbackAgent(Integrated(), budget_seconds=.02,
                                           reserve_seconds=.001,
                                           before_transform=delay)
        obs = {"player": 0, "step": 100, "farms": [{"hands": [[0, 0]]}]}
        self.assertEqual(guarded(obs, {}), selected)
        self.assertEqual(guarded.diagnostics["fallback_stage"], "transform")

    def test_production_timeout_returns_legal_pass_for_all_workers(self):
        class Production:
            def act(self, _obs):
                time.sleep(.03)
        class Integrated:
            production = Production()
            diagnostics = {}
        guarded = D.DeadlineFallbackAgent(Integrated(), budget_seconds=.02,
                                           reserve_seconds=.001)
        obs = {"player": 0, "step": 100,
               "farms": [{"hands": [[1, 1], [2, 2]]}]}
        self.assertEqual(guarded(obs, {}), {"farmer": ["PASS"],
            "hands": [["PASS"], ["PASS"]], "market": []})
        self.assertEqual(guarded.diagnostics["fallback_stage"], "production")

    def test_terminal_fallback_places_visible_cargo_then_sells_post_unit_shed(self):
        tiles = [[None for _ in range(10)] for _ in range(10)]
        obs = {"player": 0, "step": 718,
               "farms": [{"tiles": tiles, "farmer": [4, 4], "hands": [[0, 0]]}],
               "private": {"shed": {"MILK": 90, "WOOL": 5},
                           "inventories": [{"MILK": 10}, {"WOOL": 9}]},
               "market": {"prices": {"MILK": 160, "WOOL": 200}}}
        got = D.terminal_liquidation_fallback(obs, {"shedCapacity": 100,
                                                    "maxMarketOrdersPerTurn": 10})
        self.assertEqual(got["farmer"], ["DROP"])
        self.assertEqual(got["hands"], [["PASS"]])
        self.assertEqual(got["market"], [["SELL", "MILK", 95], ["SELL", "WOOL", 5]])


if __name__ == "__main__":
    unittest.main()
