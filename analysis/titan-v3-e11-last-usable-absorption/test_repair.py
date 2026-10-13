# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import copy
import importlib.util
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"
ENGINE_PY = Path(os.environ.get("TITAN_ENGINE_PY", FIXTURES / "kaggriculture.py"))
ENGINE_JSON = Path(os.environ.get("TITAN_ENGINE_JSON", FIXTURES / "kaggriculture.json"))
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import repair  # noqa: E402


def load_python(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_engine():
    package = types.ModuleType("kaggle_environments")
    utils = types.ModuleType("kaggle_environments.utils")
    utils.resolve_episode_seed = lambda *_args, **_kwargs: 0
    package.utils = utils
    sys.modules.setdefault("kaggle_environments", package)
    sys.modules.setdefault("kaggle_environments.utils", utils)
    return load_python("e11_exact_official_engine", ENGINE_PY)


def e11_observation(step: int = 717):
    return {
        "step": step,
        "player": 0,
        "market": {"prices": {"WHEAT": 10}},
        "town": {"unlocked_shops": []},
    }


def e11_config():
    return {
        "episodeSteps": 720,
        "rival_dump_price_drop": 15,
        "rival_dump_lookback_steps": 8,
        "e11_min_future_absorption": 2,
    }


def final_only_absorption(_item, step, _shops, _config):
    return 2 if step == 718 else 0


def current_only_absorption(_item, step, _shops, _config):
    return 2 if step == 717 else 0


class RepairCarrierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (FIXTURES / "e11_rival_sell.py").read_bytes()
        cls.engine_source = ENGINE_PY.read_bytes()
        cls.engine_config = ENGINE_JSON.read_bytes()
        cls.repaired = repair.repair_source(cls.source)
        cls.temp = tempfile.TemporaryDirectory()
        repaired_path = Path(cls.temp.name) / "e11_repaired.py"
        repaired_path.write_bytes(cls.repaired)
        cls.predecessor = load_python("e11_predecessor", FIXTURES / "e11_rival_sell.py")
        cls.candidate = load_python("e11_candidate", repaired_path)
        cls.engine = load_engine()

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_authenticated_inputs_and_one_factor_output(self):
        self.assertEqual(repair.sha256(self.source), repair.SOURCE_SHA256)
        self.assertEqual(repair.sha256(self.engine_source), repair.ENGINE_SHA256)
        self.assertEqual(repair.sha256(self.engine_config), repair.ENGINE_CONFIG_SHA256)
        self.assertEqual(self.source.count(repair.PREIMAGE), 1)
        self.assertEqual(self.source.count(repair.POSTIMAGE), 0)
        self.assertEqual(self.repaired.count(repair.PREIMAGE), 0)
        self.assertEqual(self.repaired.count(repair.POSTIMAGE), 1)
        before = self.source.splitlines()
        after = self.repaired.splitlines()
        changed = [(a, b) for a, b in zip(before, after) if a != b]
        self.assertEqual(
            changed,
            [(b"        " + repair.PREIMAGE, b"        " + repair.POSTIMAGE)],
        )

    def test_predecessor_defers_on_unusable_final_tick_candidate_does_not(self):
        action = {"market": [["SELL", "WHEAT", 5]], "farmer": ["PASS"]}
        original = copy.deepcopy(action)
        history = [(716, {"WHEAT": 30})]
        old, old_report = self.predecessor.apply_e11(
            e11_observation(), action, history, e11_config(), final_only_absorption, enabled=True
        )
        new, new_report = self.candidate.apply_e11(
            e11_observation(), action, history, e11_config(), final_only_absorption, enabled=True
        )
        self.assertEqual(action, original)
        self.assertEqual(old["market"], [[]])
        self.assertTrue(old_report["changed"])
        self.assertEqual(old_report["future_absorption"]["WHEAT"], 2)
        self.assertIs(new, action)
        self.assertFalse(new_report["changed"])
        self.assertEqual(new_report["future_absorption"]["WHEAT"], 0)
        self.assertEqual(new_report["reason"], "NO_OP_INSUFFICIENT_FUTURE_ABSORPTION")

    def test_current_step_post_market_tick_remains_usable(self):
        action = {"market": [["SELL", "WHEAT", 5]]}
        out, report = self.candidate.apply_e11(
            e11_observation(), action, [(716, {"WHEAT": 30})], e11_config(), current_only_absorption, enabled=True
        )
        self.assertEqual(out["market"], [[]])
        self.assertTrue(report["changed"])
        self.assertEqual(report["future_absorption"]["WHEAT"], 2)

    def test_only_terminal_tick_is_removed_from_longer_horizon(self):
        def ticks(_item, step, _shops, _config):
            return {716: 1, 717: 2, 718: 100}.get(step, 0)

        obs = e11_observation(step=716)
        cfg = e11_config()
        cfg["e11_min_future_absorption"] = 3
        out, report = self.candidate.apply_e11(
            obs, {"market": [["SELL", "WHEAT", 1]]}, [(715, {"WHEAT": 30})], cfg, ticks, enabled=True
        )
        self.assertEqual(out["market"], [[]])
        self.assertEqual(report["future_absorption"]["WHEAT"], 3)

    def test_terminal_step_identity_is_preserved(self):
        action = {"market": [["SELL", "WHEAT", 1]]}
        out, report = self.candidate.apply_e11(
            e11_observation(step=718), action, [(717, {"WHEAT": 30})], e11_config(), final_only_absorption, enabled=True
        )
        self.assertIs(out, action)
        self.assertEqual(report["reason"], "NO_OP_TERMINAL_STEP")

    def test_disabled_identity_is_preserved(self):
        action = {"market": [["SELL", "WHEAT", 1]]}
        out, report = self.candidate.apply_e11(
            e11_observation(), action, [(716, {"WHEAT": 30})], e11_config(), final_only_absorption, enabled=False
        )
        self.assertIs(out, action)
        self.assertEqual(report["reason"], "OFF")

    def test_engine_source_binds_market_then_town_then_terminal_cash(self):
        receipt = repair.audit_engine(self.engine_source, self.engine_config)
        self.assertTrue(receipt["market_before_town"])
        self.assertTrue(receipt["town_before_terminal_cash"])
        self.assertFalse(receipt["final_town_tick_has_later_market"])

    def _market_state(self, action):
        e = self.engine
        board_size = 10
        farms = [e._new_farm(board_size, 0), e._new_farm(board_size, 0)]
        privates = [e._new_private(), e._new_private()]
        privates[0]["shed"]["WHEAT"] = 1
        market = e._new_market()
        town = {"unlocked_shops": []}
        observations = [
            types.SimpleNamespace(market=market, farms=farms, private=privates[i], town=town, player=i, step=717)
            for i in range(2)
        ]
        states = [
            types.SimpleNamespace(observation=observations[0], action=copy.deepcopy(action), status="ACTIVE", reward=0.0),
            types.SimpleNamespace(observation=observations[1], action={"market": []}, status="ACTIVE", reward=0.0),
        ]
        config = types.SimpleNamespace(
            boardSize=board_size,
            maxMarketOrdersPerTurn=10,
            farmHandCostMult=1,
            shedCapacity=100,
            townShopSellInterval=719,
            townCenterSellInterval=718,
        )
        env = types.SimpleNamespace(configuration=config, info={"seed": 1})
        return states, env

    def _two_step_cash(self, first_action):
        states, env = self._market_state(first_action)
        self.engine._process_market(states, env)
        self.engine._town_consume(env, states, 717)
        states[0].action = {"market": []}
        states[1].action = {"market": []}
        self.engine._process_market(states, env)
        before_final_tick = states[0].observation.farms[0]["money"]
        self.engine._town_consume(env, states, 718)
        after_final_tick = states[0].observation.farms[0]["money"]
        return before_final_tick, after_final_tick, states[0].observation.private["shed"]["WHEAT"]

    def test_exact_engine_two_step_counterexample(self):
        sold_before, sold_after, sold_stock = self._two_step_cash({"market": [["SELL", "WHEAT", 1]]})
        deferred_before, deferred_after, deferred_stock = self._two_step_cash({"market": [[]]})
        self.assertGreater(sold_before, 0)
        self.assertEqual(sold_before, sold_after)
        self.assertEqual(deferred_before, 0)
        self.assertEqual(deferred_after, 0)
        self.assertEqual(sold_stock, 0)
        self.assertEqual(deferred_stock, 1)
        self.assertGreater(sold_after, deferred_after)

    def test_repair_is_fail_closed_on_source_or_engine_drift(self):
        with self.assertRaisesRegex(ValueError, "source SHA-256 drift"):
            repair.repair_source(self.source + b"\n")
        with self.assertRaisesRegex(ValueError, "engine SHA-256 drift"):
            repair.audit_engine(self.engine_source + b"\n", self.engine_config)
        with self.assertRaisesRegex(ValueError, "engine config SHA-256 drift"):
            repair.audit_engine(self.engine_source, self.engine_config + b"\n")

    def test_receipt_is_deterministic_and_non_authoritative(self):
        first = repair.build_receipt(self.source, self.repaired, self.engine_source, self.engine_config)
        second = repair.build_receipt(self.source, self.repaired, self.engine_source, self.engine_config)
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))
        self.assertFalse(first["authority"]["canonical_mutation"])
        self.assertFalse(first["authority"]["feature_enablement"])
        self.assertFalse(first["authority"]["gameplay_strength_claim"])


if __name__ == "__main__":
    unittest.main()
