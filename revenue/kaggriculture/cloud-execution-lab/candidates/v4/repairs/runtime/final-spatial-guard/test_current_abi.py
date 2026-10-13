# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import copy
import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path

import apply_repair as carrier

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[7]
MAIN = ROOT / carrier.TARGET
SPATIAL = ROOT / carrier.SPATIAL_TARGET


def load_path(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class Features:
    def __init__(self, **values):
        self.consumer = values.get("consumer", "frozen")
        self.terminal_route = values.get("terminal_route", False)
        self.overflow_safe_drop = values.get("overflow_safe_drop", False)
        self.fourth_quadrant = values.get("fourth_quadrant", False)
        self.budget_seconds = values.get("budget_seconds", 0.1)


class RuntimeBase:
    pressure_mode = "reorder"

    def __init__(self, features=None, *, fourth_quadrant_admission=None):
        self.features = features
        self.spatial = None
        self.history = None
        self.diagnostics = {"status": "completed"}

    def _early_capital_selected(self, _obs, _cfg, selected):
        return selected

    def _market_pressure_selected(self, _obs, _cfg, selected):
        if self.pressure_mode == "identity":
            return selected
        result = copy.deepcopy(selected)
        if self.pressure_mode == "duplicate":
            result["market"] = [
                ["SELL", "FERTILIZER", 1],
                ["SELL", "FERTILIZER", 1],
            ]
        else:
            result["market"] = [
                ["SELL", "FERTILIZER", 1],
                ["SELL", "CARROT", 1],
            ]
        return result


def load_main(source: bytes):
    fake = types.ModuleType("titan_runtime")
    fake.TitanAgent = RuntimeBase
    fake.Features = Features
    fake.load = lambda *_args, **_kwargs: None
    previous = sys.modules.get("titan_runtime")
    sys.modules["titan_runtime"] = fake
    try:
        module = types.ModuleType("_titan_v4_12019_main_under_test")
        module.__file__ = str(MAIN)
        exec(compile(source, str(MAIN), "exec"), module.__dict__)
        agent = module._new_instance(Path(tempfile.gettempdir()), {})
    finally:
        if previous is None:
            sys.modules.pop("titan_runtime", None)
        else:
            sys.modules["titan_runtime"] = previous
    return agent


class DummyMechanics:
    pass


class FinalSpatialGuardCurrentAbiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_bytes()
        cls.spatial_source = SPATIAL.read_bytes()
        cls.patched = carrier.patch_bytes(cls.source)
        cls.spatial_module = load_path("_titan_v4_12019_spatial", SPATIAL)

    def observation(self):
        return {
            "player": 0,
            "step": 715,
            "farms": [{"hands": []}, {"hands": []}],
            "private": {"inventories": [{}], "shed": {}},
        }

    def action(self):
        return {
            "farmer": ["DROP"],
            "hands": [],
            "market": [
                ["SELL", "CARROT", 1],
                ["SELL", "FERTILIZER", 1],
            ],
        }

    def spatial(self, slot=1):
        spatial = self.spatial_module.SpatialTempo(DummyMechanics(), idle_fertilizer=True)
        spatial._sale_proposal = {
            "step": 715,
            "slot": slot,
            "worker": 0,
            "quantity": 1,
            "target": 0,
        }
        return spatial

    def test_exact_current_sources_and_patch_closure(self):
        self.assertEqual(carrier.git_blob_sha1(self.source),
                         carrier.EXPECTED_MAIN_GIT_BLOB_SHA1)
        self.assertEqual(carrier.git_blob_sha1(self.spatial_source),
                         carrier.EXPECTED_SPATIAL_GIT_BLOB_SHA1)
        self.assertNotEqual(self.source, self.patched)
        self.assertEqual(self.patched.decode("utf-8").count(carrier.NEW), 1)
        compile(self.patched, str(MAIN), "exec")

    def test_current_predecessor_keeps_stale_slot_after_late_reorder(self):
        RuntimeBase.pressure_mode = "reorder"
        agent = load_main(self.source)
        spatial = self.spatial(slot=1)
        agent.spatial = spatial
        returned = agent._early_capital_selected(self.observation(), {}, self.action())
        self.assertEqual(returned["market"][0], ["SELL", "FERTILIZER", 1])
        self.assertEqual(spatial._sale_proposal["slot"], 1)
        self.assertNotEqual(returned["market"][spatial._sale_proposal["slot"]],
                            ["SELL", "FERTILIZER", 1])

    def test_repair_rebinds_against_final_returned_bytes(self):
        RuntimeBase.pressure_mode = "reorder"
        agent = load_main(self.patched)
        spatial = self.spatial(slot=1)
        agent.spatial = spatial
        returned = agent._early_capital_selected(self.observation(), {}, self.action())
        self.assertEqual(returned["market"][0], ["SELL", "FERTILIZER", 1])
        self.assertEqual(spatial._sale_proposal["slot"], 0)
        self.assertEqual(returned["farmer"], ["DROP"])
        self.assertEqual(agent._finalizer_checkpoint["stage"], "spatial_final_guard")
        self.assertEqual(agent._finalizer_checkpoint["action"], returned)

    def test_final_guard_fails_closed_duplicate_sale_and_paired_drop(self):
        RuntimeBase.pressure_mode = "duplicate"
        agent = load_main(self.patched)
        spatial = self.spatial(slot=1)
        agent.spatial = spatial
        returned = agent._early_capital_selected(self.observation(), {}, self.action())
        self.assertEqual(returned["farmer"], ["PASS"])
        self.assertEqual(returned["market"], [[], []])
        self.assertEqual(agent._finalizer_checkpoint["stage"], "spatial_final_guard")

    def test_no_proposal_is_identity_after_late_boundary(self):
        RuntimeBase.pressure_mode = "identity"
        agent = load_main(self.patched)
        spatial = self.spatial_module.SpatialTempo(DummyMechanics(), idle_fertilizer=True)
        agent.spatial = spatial
        action = self.action()
        returned = agent._early_capital_selected(self.observation(), {}, action)
        self.assertIs(returned, action)
        self.assertEqual(agent._finalizer_checkpoint["stage"], "spatial_final_guard")

    def test_deadline_fallback_does_not_start_final_spatial_guard(self):
        RuntimeBase.pressure_mode = "reorder"
        agent = load_main(self.patched)
        spatial = self.spatial(slot=1)
        agent.spatial = spatial
        agent.diagnostics = {"status": "deadline_fallback"}
        action = self.action()
        returned = agent._early_capital_selected(self.observation(), {}, action)
        self.assertIs(returned, action)
        self.assertEqual(spatial._sale_proposal["slot"], 1)
        self.assertEqual(agent._finalizer_checkpoint["stage"], "early_capital")


if __name__ == "__main__":
    unittest.main()
