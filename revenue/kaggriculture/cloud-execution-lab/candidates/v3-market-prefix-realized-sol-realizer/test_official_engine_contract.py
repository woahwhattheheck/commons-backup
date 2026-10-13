# SPDX-License-Identifier: Apache-2.0
"""Predecessor-killing tests against the exact pinned repository engine."""
from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
import unittest

from market_prefix_rescue import rescue_market_prefix
from realized_execution import action_digest, world_digest

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[1]
EVALUATOR_PATH = LAB / "reference/evaluator/evaluate.py"
LOADER_PATH = LAB / "reference/evaluator/loader.py"
ENGINE_DIR = LAB / "reference/engine"


def import_file(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


try:
    import kaggle_environments  # noqa: F401
except ImportError:
    kaggle_environments = None


@unittest.skipIf(kaggle_environments is None, "kaggle-environments not installed")
class OfficialEngineRealizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evaluator = import_file(EVALUATOR_PATH, "sol_realizer_contract_evaluator")
        cls.engine, _ = cls.evaluator.get_engine(ENGINE_DIR, LOADER_PATH)

    def _after_one_step(self, market, *, starting_money=3000):
        cfg = self.evaluator.Struct(
            {
                key: value.get("default") if isinstance(value, dict) else value
                for key, value in self.engine.specification["configuration"].items()
            }
        )
        cfg.maxMarketOrdersPerTurn = 1
        cfg.episodeSteps = 4
        cfg.startingMoney = starting_money
        cfg.seed = 20260910
        env = self.evaluator.Struct(configuration=cfg, done=False, info={})
        state = [
            self.evaluator.Struct(
                observation=self.evaluator.Struct(),
                action={},
                status="ACTIVE",
                reward=0,
            )
            for _ in range(2)
        ]
        self.engine.interpreter(state, env)
        for seat in range(2):
            state[seat].observation.step = 0
            state[seat].observation.remainingOverageTime = 0
        pre = world_digest(state, env)
        state[0].action = {"farmer": ["PASS"], "hands": [], "market": deepcopy(market)}
        state[1].action = {"farmer": ["PASS"], "hands": [], "market": []}
        self.engine.interpreter(state, env)
        post = world_digest(state, env)
        snapshot = {
            "money": float(state[0].observation.farms[0]["money"]),
            "seeds": dict(state[0].observation.private["seeds"]),
            "shed": dict(state[0].observation.private["shed"]),
        }
        return pre, post, snapshot

    def test_world_digest_excludes_submitted_action_bytes(self):
        evaluator = self.evaluator
        env = evaluator.Struct(done=False)
        left = [evaluator.Struct(observation={"x": 1}, action={"a": 1}, status="ACTIVE", reward=0)]
        right = [evaluator.Struct(observation={"x": 1}, action={"a": 2}, status="ACTIVE", reward=0)]
        self.assertEqual(world_digest(left, env), world_digest(right, env))

    def test_funded_buy_crossing_is_realized(self):
        stranded = [[], ["BUY_SEED", "WHEAT", 1]]
        transformed, report = rescue_market_prefix(
            {"market": stranded}, {"maxMarketOrdersPerTurn": 1}
        )
        self.assertTrue(report["syntactic_changed"])
        before_pre, before_post, before = self._after_one_step(stranded)
        after_pre, after_post, after = self._after_one_step(transformed["market"])
        self.assertEqual(before_pre, after_pre)
        self.assertNotEqual(action_digest(stranded), action_digest(transformed["market"]))
        self.assertNotEqual(before_post, after_post)
        self.assertEqual(before["seeds"].get("WHEAT", 0), 0)
        self.assertEqual(before["money"], 3000.0)
        self.assertEqual(after["seeds"].get("WHEAT", 0), 1)
        self.assertEqual(after["money"], 2990.0)

    def test_zero_stock_sell_crossing_is_syntactic_but_inert(self):
        stranded = [[], ["SELL", "WHEAT", 1]]
        transformed, report = rescue_market_prefix(
            {"market": stranded}, {"maxMarketOrdersPerTurn": 1}
        )
        self.assertTrue(report["syntactic_changed"])
        before_pre, before_post, before = self._after_one_step(stranded)
        after_pre, after_post, after = self._after_one_step(transformed["market"])
        self.assertEqual(before_pre, after_pre)
        self.assertNotEqual(action_digest(stranded), action_digest(transformed["market"]))
        self.assertEqual(before_post, after_post)
        self.assertEqual(before, after)

    def test_unaffordable_buy_crossing_is_syntactic_but_inert(self):
        stranded = [[], ["BUY_SEED", "WHEAT", 1]]
        transformed, report = rescue_market_prefix(
            {"market": stranded}, {"maxMarketOrdersPerTurn": 1}
        )
        self.assertTrue(report["syntactic_changed"])
        before_pre, before_post, before = self._after_one_step(
            stranded, starting_money=0
        )
        after_pre, after_post, after = self._after_one_step(
            transformed["market"], starting_money=0
        )
        self.assertEqual(before_pre, after_pre)
        self.assertNotEqual(action_digest(stranded), action_digest(transformed["market"]))
        self.assertEqual(before_post, after_post)
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
