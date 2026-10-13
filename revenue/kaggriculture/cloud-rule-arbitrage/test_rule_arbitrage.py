# SPDX-License-Identifier: MIT
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import unittest

from cycle import RuleCycleTransform, floor_quote, simultaneous_cycle_delta

HERE = Path(__file__).resolve().parent
ENGINE_DIR = HERE.parent / "cloud-execution-lab/reference/engine"
EVALUATOR = HERE.parent / "cloud-eval/evaluate.py"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RuleArbitrageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ev = _load("t11_evaluator", EVALUATOR)
        cls.engine, _ = cls.ev.get_engine(ENGINE_DIR)
        cls.params = cls.engine.MARKET_PARAMS

    def fixture(self, item="FERTILIZER", stock=(1, 0), inventory=11000, cash=0):
        e, S = self.engine, self.ev.Struct
        cfg = S({k: v.get("default") if isinstance(v, dict) else v
                 for k, v in e.specification["configuration"].items()})
        farms = [e._new_farm(10, cash), e._new_farm(10, cash)]
        market = e._new_market()
        market["inventory"][item] = inventory
        e._refresh_prices(market)
        state = []
        for seat in range(2):
            private = e._new_private()
            private["shed"][item] = stock[seat]
            obs = S(player=seat, step=1, day=0, hour=1, farms=farms,
                    private=private, market=market, town={"unlocked_shops": []})
            state.append(S(observation=obs, action={}, status="ACTIVE", reward=0))
        return state, S(configuration=cfg, done=False, info={"seed": 9830001})

    def market(self, state, env, left, right=()):
        state[0].action = {"farmer": ["PASS"], "hands": [], "market": list(left)}
        state[1].action = {"farmer": ["PASS"], "hands": [], "market": list(right)}
        self.engine._process_market(state, env)

    def test_solo_buy_sell_is_exactly_zero(self):
        state, env = self.fixture(item="WHEAT", stock=(0, 0), inventory=10000, cash=1000)
        self.market(state, env, [["BUY_PRODUCT", "WHEAT", 1], ["SELL", "WHEAT", 1]])
        self.assertEqual(state[0].observation.farms[0]["money"], 1000)
        self.assertEqual(state[0].observation.market["inventory"]["WHEAT"], 10000)

    def test_simultaneous_buy_is_positive_but_rival_sell_can_reverse_it(self):
        # 9503 straddles one of the official integer-rounding boundaries.
        buy = simultaneous_cycle_delta("FERTILIZER", 9503, self.params, "BUY_PRODUCT")
        sell = simultaneous_cycle_delta("FERTILIZER", 9503, self.params, "SELL")
        solo = simultaneous_cycle_delta("FERTILIZER", 9503, self.params, "PASS")
        self.assertGreaterEqual(buy, 0)
        self.assertLessEqual(sell, 0)
        self.assertEqual(solo, 0)
        self.assertTrue(buy > 0 or sell < 0)

    def test_floor_sell_buy_withdraws_inventory_for_zero_cash(self):
        state, env = self.fixture(inventory=11000, cash=0)
        before = copy.deepcopy(state[0].observation.private["shed"])
        self.assertEqual(floor_quote("FERTILIZER", 11000, self.params), 1)
        self.assertEqual(floor_quote("FERTILIZER", 10999, self.params), 1)
        self.market(state, env, [["SELL", "FERTILIZER", 1],
                                 ["BUY_PRODUCT", "FERTILIZER", 1]])
        self.assertEqual(state[0].observation.farms[0]["money"], 0)
        self.assertEqual(state[0].observation.private["shed"], before)
        self.assertEqual(state[0].observation.market["inventory"]["FERTILIZER"], 10999)

    def test_transform_appends_after_base_without_changing_it(self):
        state, env = self.fixture(inventory=11000, cash=0)
        obs, cfg = state[0].observation, env.configuration
        base = {"farmer": ["PASS"], "hands": [], "market": [["HIRE"]]}
        out = RuleCycleTransform().transform(obs, cfg, base)
        self.assertEqual(base["market"], [["HIRE"]])
        self.assertEqual(out["market"][0], ["HIRE"])
        self.assertGreater(len(out["market"]), 1)
        self.assertLessEqual(len(out["market"]), cfg.maxMarketOrdersPerTurn)

    def test_transform_declines_near_floor_boundary(self):
        state, env = self.fixture(inventory=10500, cash=0)
        base = {"farmer": ["PASS"], "hands": [], "market": []}
        transform = RuleCycleTransform()
        out = transform.transform(state[0].observation, env.configuration, base)
        self.assertEqual(out, base)
        self.assertEqual(transform.last["status"], "no-deep-floor")

    def test_requested_sell_stock_is_reserved(self):
        state, env = self.fixture(inventory=11000, cash=0)
        base = {"farmer": ["PASS"], "hands": [],
                "market": [["SELL", "FERTILIZER", 1]]}
        out = RuleCycleTransform().transform(state[0].observation, env.configuration, base)
        self.assertEqual(out, base)


if __name__ == "__main__":
    unittest.main()
