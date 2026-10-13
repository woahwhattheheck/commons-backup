"""E14 regressions for unit-deposit versus market-sale shed timing."""
from __future__ import annotations

import unittest

import scheduler as s
import test_engine_semantics as semantics
from test_scheduler import FixedController


class ShedTurnoverTimingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        semantics.EngineSemantics.setUpClass()
        cls.helper = semantics.EngineSemantics()

    def fixture(self, **kwargs):
        return self.helper.fixture(**kwargs)

    def scheduler(self, now, action):
        agent = s.SellScheduler()
        agent.controller = FixedController(now, action)
        return agent

    def test_current_market_sale_cannot_rescue_current_drop_overflow(self):
        state, env = self.fixture(stock=(0, 0), step=22, cash=10000)
        obs = state[0].observation
        obs.private["shed"]["WHEAT"] = 95
        obs.private["inventories"] = [{"MILK": 10}]
        base = {"farmer": ["DROP"], "hands": [],
                "market": [["SELL", "WHEAT", 10]]}

        farm, actual = s.post_units(obs, base, env.configuration)
        _, requested = s.post_units(obs, base, env.configuration,
                                    shed_capacity=10**6)
        self.assertEqual(sum(actual["shed"].values()), 100)
        self.assertEqual(actual["shed"]["MILK"], 5)
        self.assertEqual(sum(requested["shed"].values()), 105)
        self.assertEqual(requested["shed"]["MILK"], 10)

        feasible = self.scheduler(22, base).receipt_profile(
            obs, base, farm, actual, 22, "MILK", env.configuration)
        self.assertFalse(feasible(((22, 5),)),
                         "A same-turn market sale cannot rescue DROP units already discarded")

    def test_legal_full_drop_remains_feasible_when_current_sale_releases_room(self):
        state, env = self.fixture(stock=(0, 0), step=22, cash=10000)
        obs = state[0].observation
        obs.private["shed"]["WHEAT"] = 90
        obs.private["inventories"] = [{"MILK": 10}]
        base = {"farmer": ["DROP"], "hands": [],
                "market": [["SELL", "WHEAT", 10]]}

        farm, actual = s.post_units(obs, base, env.configuration)
        _, requested = s.post_units(obs, base, env.configuration,
                                    shed_capacity=10**6)
        self.assertEqual(actual["shed"], requested["shed"],
                         "The unbounded timing projection must match when no unit was discarded")
        self.assertEqual(sum(actual["shed"].values()), 100)

        feasible = self.scheduler(22, base).receipt_profile(
            obs, base, farm, actual, 22, "MILK", env.configuration)
        self.assertTrue(feasible(()),
                        "A legal full shed is not itself overflow; the current sale may free later room")


if __name__ == "__main__":
    unittest.main(verbosity=2)
