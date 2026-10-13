# SPDX-License-Identifier: Apache-2.0
"""Focused current-V4 contracts for funding-trace plant decay chronology."""
from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
FUNDING = HERE.parent
V4 = HERE.parents[3]
LAB = HERE.parents[5]
SOURCE = LAB / "frozen_selected.py"
SCHEDULER = LAB / "scheduler.py"
MECHANICS = LAB / "mechanics.py"
ENGINE = LAB / "reference" / "engine" / "kaggriculture.py"

PINS = {
    SOURCE: "fc7baf5c179818a55037f6a61d92984d81d1a21c",
    SCHEDULER: "a483b24dd72b580d7d8811636b54d2d44f391575",
    MECHANICS: "044a4f9c0a4a44dde10ada57563238bcaf82075d",
    ENGINE: "3c202c7ee921da239356789e266b694635103fc4",
}

sys.path.insert(0, str(HERE))
from apply_plant_decay import (  # noqa: E402
    CAPTRACE_AFTER,
    DECAY_LINE,
    EOD_GUARD,
    REQUIRED_MARKERS,
    _digest,
    _target,
    apply,
)


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def load_tool(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load tool from " + str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def function_ast_digest(text: str, name: str) -> str:
    nodes = [
        node for node in ast.parse(text).body
        if isinstance(node, ast.FunctionDef) and node.name == name
    ]
    if len(nodes) != 1:
        raise AssertionError("expected one function " + name)
    payload = ast.dump(nodes[0], annotate_fields=True, include_attributes=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class FundingPlantDecay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw_bytes = {path: path.read_bytes() for path in PINS}
        for path, expected in PINS.items():
            if git_blob(cls.raw_bytes[path]) != expected:
                raise ValueError(f"canonical input drifted: {path}")

        cls.town = load_tool("_v4_decay_town", FUNDING / "apply_town_funding.py")
        cls.joint = load_tool(
            "_v4_decay_joint",
            V4 / "repairs" / "runtime" / "joint-unit-projection" / "compose.py",
        )
        cls.perf = load_tool("_v4_decay_perf", FUNDING / "apply_funding_replay.py")
        cls.cap = load_tool("_v4_decay_cap", FUNDING / "compose_funding_capacity.py")

        source = cls.raw_bytes[SOURCE].decode("utf-8")
        scheduler = cls.raw_bytes[SCHEDULER].decode("utf-8")
        source = cls.town.apply(source)
        scheduler, source = cls.joint.compose_sources(scheduler, source)
        source = cls.perf.apply(source)
        source = cls.cap.apply(source)
        cls.composed_scheduler = scheduler
        cls.predecessor_source = source
        cls.candidate_source = apply(source)

        cls.temp = tempfile.TemporaryDirectory(prefix="v4-funding-decay-")
        root = Path(cls.temp.name)
        (root / "scheduler.py").write_text(cls.composed_scheduler, encoding="utf-8")
        cls.predecessor_path = root / "funding_predecessor.py"
        cls.candidate_path = root / "funding_candidate.py"
        cls.predecessor_path.write_text(cls.predecessor_source, encoding="utf-8")
        cls.candidate_path.write_text(cls.candidate_source, encoding="utf-8")

        cls.old_scheduler = sys.modules.pop("scheduler", None)
        sys.path.insert(0, str(LAB))
        sys.path.insert(0, str(root))
        cls.predecessor = load_tool("_v4_decay_predecessor", cls.predecessor_path)
        cls.candidate = load_tool("_v4_decay_candidate", cls.candidate_path)

    @classmethod
    def tearDownClass(cls):
        root = str(Path(cls.temp.name))
        while root in sys.path:
            sys.path.remove(root)
        while str(LAB) in sys.path:
            sys.path.remove(str(LAB))
        sys.modules.pop("scheduler", None)
        if cls.old_scheduler is not None:
            sys.modules["scheduler"] = cls.old_scheduler
        cls.temp.cleanup()

    @staticmethod
    def farm(yield_units=2):
        tiles = [[None if x < 5 and y < 5 else "LOCKED" for x in range(10)] for y in range(10)]
        tiles[4][4] = {
            "kind": "PLANT",
            "crop": "WHEAT",
            "planted_day": 0,
            "watered_today": False,
            "consecutive_unwatered": 0,
            "yield_units": yield_units,
            "max_lifespan_step": 120,
            "fertilized_until_day": -1,
        }
        return {
            "money": 300,
            "tiles": tiles,
            "farmer": [4, 4],
            "hands": [],
            "unlocked_quadrants": ["NW"],
            "hires_today": 0,
        }

    @staticmethod
    def private(module):
        shed = {name: 0 for name in [*module.m.PRODUCTS, *module.m.ANIMALS]}
        shed["MILK"] = 1
        return {
            "shed": shed,
            "seeds": {name: 0 for name in module.m.CROPS},
            "inventories": [{}],
        }

    def fixture(self, module):
        inventory = {name: 10000 for name in module.m.PRODUCTS}
        obs = {
            "step": 120,
            "player": 0,
            "market": {"inventory": inventory, "prices": {}},
            "town": {"unlocked_shops": []},
        }
        route = [{"farmer": ["PASS"], "hands": [], "market": []} for _ in range(124)]
        route[121] = {"farmer": ["HARVEST"], "hands": [], "market": []}
        route[122] = {"farmer": ["DROP"], "hands": [], "market": []}
        route[123] = {
            "farmer": ["PASS"],
            "hands": [],
            "market": [["BUY_ANIMAL", "GOOSE", 1]],
        }
        config = {
            "shedCapacity": 2,
            "maxMarketOrdersPerTurn": 10,
            "turnsPerDay": 24,
            "episodeSteps": 720,
            "townShopSellInterval": 1000,
            "townCenterSellInterval": 1000,
        }
        base = {"farmer": ["PASS"], "hands": [], "market": [["SELL", "MILK", 1]]}
        return (
            obs,
            config,
            base,
            self.farm(),
            self.private(module),
            route,
            {"MILK": 1},
            {"MILK": 1},
        )

    def minimum(self, module):
        obs, config, base, farm, private, route, current, targets = self.fixture(module)
        return module.funded_minimum_now(
            obs,
            config,
            base,
            farm,
            private,
            route,
            123,
            current,
            targets,
            "MILK",
            stress_units=32,
        )

    def test_canonical_inputs_and_decay_semantics_are_exact(self):
        runtime = self.raw_bytes[MECHANICS].decode("utf-8")
        official = self.raw_bytes[ENGINE].decode("utf-8")
        self.assertEqual(
            function_ast_digest(runtime, "_decay_plants"),
            function_ast_digest(official, "_decay_plants"),
        )

    def test_current_four_stage_v4_chain_is_the_authenticated_preimage(self):
        _fn, _start, _end, part = _target(self.predecessor_source)
        self.assertIn(_digest(part), CAPTRACE_AFTER)
        for marker in REQUIRED_MARKERS:
            self.assertIn(marker, part)
        self.assertNotIn("_funding_turns_per_day", part)
        self.assertNotIn("m._decay_plants(f, t)", part)

    def test_adapter_adds_exact_same_day_guard_and_final_decay_stage_and_is_idempotent(self):
        predecessor = (
            self.candidate_source
            .replace(EOD_GUARD, "", 1)
            .replace(DECAY_LINE, "", 1)
        )
        self.assertEqual(predecessor, self.predecessor_source)
        self.assertEqual(self.candidate_source.count(EOD_GUARD), 1)
        self.assertEqual(self.candidate_source.count(DECAY_LINE), 1)
        self.assertEqual(apply(self.candidate_source), self.candidate_source)
        compile(self.candidate_source, "v4_funding_decay_candidate", "exec")

    def test_raw_or_town_only_funding_trace_is_refused(self):
        raw = self.raw_bytes[SOURCE].decode("utf-8")
        with self.assertRaisesRegex(ValueError, "CAPTRACE"):
            apply(raw)
        town_only = self.town.apply(raw)
        with self.assertRaisesRegex(ValueError, "CAPTRACE"):
            apply(town_only)

    def test_target_trace_drift_fails_closed(self):
        tampered = self.predecessor_source.replace(
            "sale_receipts = []",
            "sale_receipts = list()",
            1,
        )
        with self.assertRaisesRegex(ValueError, "CAPTRACE"):
            apply(tampered)

    def test_nonstandard_turn_clock_fails_closed_before_replay(self):
        obs, config, _base, farm, private, route, _current, _targets = self.fixture(
            self.candidate
        )
        config["turnsPerDay"] = 25
        with self.assertRaisesRegex(ValueError, "exact 24-turn day"):
            self.candidate._funding_trace(
                obs,
                config,
                farm,
                private,
                route,
                120,
                123,
                [],
                stress_units=0,
            )

    def test_cross_eod_stale_hand_route_is_blocked_before_unit_replay(self):
        obs, config, _base, farm, private, route, _current, _targets = self.fixture(
            self.predecessor
        )
        obs["step"] = 119
        farm["hands"] = [[4, 4]]
        private["inventories"] = [{}, {}]
        route[120] = {
            "farmer": ["PASS"],
            "hands": [["HARVEST"]],
            "market": [],
        }

        seen = []
        original = self.predecessor.m._apply_unit_action

        def recording_apply(farm_state, private_state, actor_index, action, *args, **kwargs):
            seen.append((actor_index, copy.deepcopy(action)))
            return original(
                farm_state,
                private_state,
                actor_index,
                action,
                *args,
                **kwargs,
            )

        self.predecessor.m._apply_unit_action = recording_apply
        try:
            self.predecessor._funding_trace(
                obs,
                config,
                farm,
                private,
                route,
                119,
                120,
                [],
                stress_units=0,
            )
        finally:
            self.predecessor.m._apply_unit_action = original

        self.assertIn((1, ["HARVEST"]), seen)

        obs2, config2, _base2, farm2, private2, route2, _current2, _targets2 = self.fixture(
            self.candidate
        )
        obs2["step"] = 119
        farm2["hands"] = [[4, 4]]
        private2["inventories"] = [{}, {}]
        route2[120] = {
            "farmer": ["PASS"],
            "hands": [["HARVEST"]],
            "market": [],
        }
        with self.assertRaisesRegex(ValueError, "cannot cross end-of-day lifecycle"):
            self.candidate._funding_trace(
                obs2,
                config2,
                farm2,
                private2,
                route2,
                119,
                120,
                [],
                stress_units=0,
            )

    def test_runtime_decay_reduces_expiring_wheat_before_future_harvest(self):
        farm = self.farm(yield_units=2)
        self.candidate.m._decay_plants(farm, 120)
        self.assertEqual(farm["tiles"][4][4]["yield_units"], 1)

    def test_season_reachable_capacity_killer_changes_minimum_zero_to_one(self):
        predecessor_minimum, predecessor_receipt = self.minimum(self.predecessor)
        candidate_minimum, candidate_receipt = self.minimum(self.candidate)
        self.assertEqual(predecessor_minimum, 0)
        self.assertEqual(candidate_minimum, 1)
        self.assertEqual(predecessor_receipt["reference_acquisitions"], 0)
        self.assertEqual(candidate_receipt["reference_acquisitions"], 1)
        self.assertFalse(candidate_receipt["fallback"])


if __name__ == "__main__":
    unittest.main()
