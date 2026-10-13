# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
import types
import unittest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("f3_rebase", HERE / "rebase_current_router.py")
repair = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(repair)

CONFIG = {
    "episodeSteps": 720,
    "turnsPerDay": 24,
    "boardSize": 10,
    "shedCapacity": 100,
    "maxMarketOrdersPerTurn": 10,
}


def donor_router() -> Path:
    rel = Path("revenue/kaggriculture/cloud-execution-lab/candidates/v4/donor/overlay/r04_full_router.py")
    for parent in HERE.parents:
        candidate = parent / rel
        if candidate.is_file():
            return candidate
    raise AssertionError("canonical donor router not found")


class _StructConfig:
    def __init__(self, values):
        for key, value in values.items():
            setattr(self, key, value)


class _View:
    def __init__(self, target=(7, 4), extra_targets=()):
        self.positions = [(4, 4)]
        self.inventories = [{"WHEAT": 1}]
        self.shed = {"WHEAT": 8}
        self.tiles = [[None for _ in range(10)] for _ in range(10)]
        x, y = target
        self.tiles[y][x] = {
            "kind": "PASTURE",
            "animal": "SHEEP",
            "fed_today": False,
            "consecutive_unfed": 1,
        }
        for ex, ey in extra_targets:
            self.tiles[ey][ex] = {
                "kind": "PASTURE",
                "animal": "SHEEP",
                "fed_today": False,
                "consecutive_unfed": 1,
            }

    def inventory(self, worker):
        return self.inventories[worker]

    def beside_shed(self, position):
        return tuple(position) in {(4, 4), (5, 4), (4, 5), (5, 5)}


def _plan_namespace(postimage: str, tape):
    tree = ast.parse(postimage)
    wanted = {"_v217_farmer", "_v217_standard_configuration", "_v217_plan"}
    body = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in wanted]
    if {n.name for n in body} != wanted:
        raise AssertionError("transformed V217 functions not found")
    ns = {
        "_V217_MOVES": {"EAST": (1, 0), "WEST": (-1, 0), "NORTH": (0, -1), "SOUTH": (0, 1)},
        "projected_shed": lambda action, view: dict(view.shed),
        "_POLICY": types.SimpleNamespace(tapes=[tape]),
    }
    exec(compile(ast.Module(body=body, type_ignores=[]), "<v217-rebased-functions>", "exec"), ns)
    return ns


def _tape():
    return [{"farmer": ["PASS"], "hands": [], "market": []} for _ in range(719)]


class CurrentRouterRebaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = donor_router()
        cls.source = cls.path.read_bytes()
        cls.post = repair.materialize(cls.source).decode("utf-8")

    def plan(self, *, target=(7, 4), step=500, enabled=True, config=CONFIG,
             extra_targets=(), tape=None):
        tape = tape or _tape()
        ns = _plan_namespace(self.post, tape)
        return ns["_v217_plan"](
            _View(target=target, extra_targets=extra_targets),
            {"plan": 0, "v217_used": 0},
            step,
            {"farmer": ["PASS"], "hands": [], "market": []},
            [],
            config,
            enabled,
        )

    def test_current_router_is_exactly_pinned(self):
        self.assertEqual(repair.git_blob_sha(self.source), repair.SOURCE_GIT_BLOB)

    def test_postimage_compiles_and_live_caller_remains_hard_off(self):
        compile(self.post, "<v217-eod-tail-current-router>", "exec")
        self.assertEqual(
            self.post.count("_v217_plan(view,st,step,action,pending,configuration,False)"), 1
        )
        self.assertNotIn("configuration,True)", self.post)

    def test_disabled_far_route_matches_incumbent_unreachable_result(self):
        self.assertIsNone(self.plan(enabled=False, target=(7, 4)))

    def test_exact_final_callback_tail_is_reachable_when_explicitly_enabled(self):
        plan = self.plan(enabled=True, target=(7, 4))
        self.assertIsNotNone(plan)
        self.assertIs(plan["eod_tail"], True)
        self.assertEqual(plan["commands"], [["EAST"], ["EAST"], ["EAST"], ["FEED"]])

    def test_early_finish_cannot_take_reset_credit(self):
        self.assertIsNone(self.plan(enabled=True, target=(6, 4)))

    def test_incumbent_roundtrip_is_not_shortened(self):
        plan = self.plan(enabled=True, target=(5, 4))
        self.assertIsNotNone(plan)
        self.assertIs(plan["eod_tail"], False)
        self.assertEqual(plan["commands"], [["EAST"], ["FEED"], ["WEST"]])

    def test_multiple_targets_disable_tail_but_keep_near_incumbent(self):
        plan = self.plan(enabled=True, target=(7, 4), extra_targets=((5, 4),))
        self.assertIsNotNone(plan)
        self.assertIs(plan["eod_tail"], False)
        self.assertEqual(plan["target"], (5, 4))

    def test_future_native_farmer_work_blocks_tail(self):
        tape = _tape()
        tape[503]["farmer"] = ["WATER"]
        self.assertIsNone(self.plan(enabled=True, target=(7, 4), tape=tape))

    def test_nonstandard_and_bool_configurations_fail_closed(self):
        bad = dict(CONFIG)
        bad["episodeSteps"] = 696
        self.assertIsNone(self.plan(enabled=True, target=(7, 4), config=bad))
        poison = dict(CONFIG)
        poison["turnsPerDay"] = True
        self.assertIsNone(self.plan(enabled=True, target=(7, 4), config=poison))

    def test_struct_standard_configuration_remains_eligible(self):
        plan = self.plan(enabled=True, target=(7, 4), config=_StructConfig(CONFIG))
        self.assertIsNotNone(plan)
        self.assertIs(plan["eod_tail"], True)

    def test_final_day_has_no_reset_credit(self):
        self.assertIsNone(self.plan(enabled=True, target=(6, 4), step=716))

    def test_double_apply_fails_closed(self):
        with self.assertRaises(repair.RebaseError):
            repair.transform(self.post)


if __name__ == "__main__":
    unittest.main()
