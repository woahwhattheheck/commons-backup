# SPDX-License-Identifier: Apache-2.0
"""Focused current-ABI contracts for TITAN #12096's economic floor rebind."""
from __future__ import annotations

import ast
import copy
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[4]

sys.path.insert(0, str(HERE))
import apply_forced_feasibility_floor as floor  # noqa: E402


def _exec_function(source: str, name: str, namespace: dict):
    tree = ast.parse(source)
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name]
    if len(nodes) != 1:
        raise AssertionError(f"expected one {name}, found {len(nodes)}")
    module = ast.Module(body=[copy.deepcopy(nodes[0])], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, f"<{name}>", "exec"), namespace)
    return namespace[name]


class FakePath:
    def __init__(self, candidate_score):
        self.candidate_score = candidate_score

    def score(self, plan, quantity, rival, alignment, terminal=False):
        if tuple(plan) == ((0, 0),):
            return (10.0, 10.0, 0.0, 0)
        return self.candidate_score


def _run_selected_optimize(source: str, candidate_score, *, reference_feasible=False):
    ns = {
        "shared_market_path": lambda *args, **kwargs: FakePath(candidate_score),
        "_acceptance_rule": lambda config: "strict",
        "_scenario_weights": lambda names, config: {name: 1.0 / len(names) for name in names},
        "_weighted_gain": lambda deltas, names, weights: sum(
            float(delta) * float(weights[name]) for name, delta in zip(names, deltas)
        ),
        "_e18_nonnegative_finite": lambda value: max(0.0, float(value)),
    }
    optimize = _exec_function(source, "optimize_lot", ns)
    capacity = (lambda plan: True) if reference_feasible else (lambda plan: tuple(plan) != ((0, 0),))
    return optimize(
        item="CARROT",
        quantity=1,
        inventory=100,
        params={},
        shops=[],
        config={},
        now=0,
        dates=[0],
        reference=((0, 0),),
        rival_quantity=0,
        minimum_now=0,
        capacity_ok=capacity,
        last=718,
    )


class ForcedFeasibilityEconomicFloor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.paths = {
            "selected_sell_core": LAB / "selected_sell_core.py",
            "frozen_selected": LAB / "frozen_selected.py",
            "exec_pace_runtime": LAB / "exec_pace_runtime.py",
        }
        cls.raw = {name: path.read_bytes() for name, path in cls.paths.items()}
        for name, raw in cls.raw.items():
            observed = floor.git_blob(raw)
            expected = floor.EXPECTED_BLOBS[name]
            if observed != expected:
                raise AssertionError(f"{name} source drift: {observed} != {expected}")
        cls.source = {name: raw.decode("utf-8") for name, raw in cls.raw.items()}
        cls.repaired = {
            "selected_sell_core": floor.transform_selected_sell_core(cls.source["selected_sell_core"]),
            "frozen_selected": floor.transform_frozen_selected(cls.source["frozen_selected"]),
            "exec_pace_runtime": floor.verify_exec_pace_runtime(cls.source["exec_pace_runtime"]),
        }

    def test_previous_carrier_custody_is_retained(self):
        self.assertEqual(floor.PREVIOUS_CARRIER["merge"], "02ae1236f1d4beee2b4b1eadd1f3ec814535cb2c")
        self.assertEqual(floor.PREVIOUS_CARRIER["materializer_blob"], "a06f504083bd9a4d64cdb225ce5101b8541591bc")
        self.assertEqual(floor.PREVIOUS_CARRIER["test_blob"], "07676d7f621fe8a146a60c7060e4abaa64aa8399")
        self.assertEqual(
            floor.RECONSTRUCTED_SCHEDULER_EDGE,
            {
                "funding_capacity_output": "eb289f87adebb7dc7e90046bfbec31a307cb5aaa",
                "scoped_construction_output": "b29d1e9887f517506c5b3d858baa9bda5848e73f",
            },
        )

    def test_current_sources_are_exact_source_only_inputs(self):
        self.assertNotEqual(self.repaired["selected_sell_core"], self.source["selected_sell_core"])
        self.assertNotEqual(self.repaired["frozen_selected"], self.source["frozen_selected"])
        self.assertEqual(self.repaired["exec_pace_runtime"], self.source["exec_pace_runtime"])
        for name, source in self.repaired.items():
            compile(source, name, "exec")
            self.assertEqual(self.paths[name].read_bytes(), self.raw[name])

    def test_active_frozen_call_path_keeps_exec_pace_before_rank(self):
        source = self.source["frozen_selected"]
        optimizer = source.index("plan,info=optimize_lot(")
        exec_pace = source.index("plan,info=exec_pace_apply(")
        rank = source.index("eligible,rank=seller_choice_rank(info)")
        self.assertLess(optimizer, exec_pace)
        self.assertLess(exec_pace, rank)

    def test_forced_negative_relative_candidate_is_rejected(self):
        _plan, info = _run_selected_optimize(
            self.repaired["selected_sell_core"], (9.0, 9.0, 0.0, 0)
        )
        self.assertFalse(info["feasible"])
        self.assertFalse(info["forced_feasibility"])
        self.assertTrue(info["physical_feasible_found"])
        self.assertGreater(info["economic_floor_rejections"], 0)

    def test_forced_negative_own_candidate_is_rejected_at_relative_zero(self):
        _plan, info = _run_selected_optimize(
            self.repaired["selected_sell_core"], (10.0, 9.0, 0.0, 0)
        )
        self.assertFalse(info["feasible"])
        self.assertFalse(info["forced_feasibility"])
        self.assertEqual(info["worst_relative_gain"], 0.0)
        self.assertGreater(info["economic_floor_rejections"], 0)

    def test_value_neutral_and_positive_forced_rescues_survive_the_floor(self):
        for score, expected_gain in (
            ((10.0, 10.0, 0.0, 0), 0.0),
            ((11.0, 11.0, 0.0, 0), 1.0),
        ):
            plan, info = _run_selected_optimize(self.repaired["selected_sell_core"], score)
            self.assertEqual(tuple(plan), ((0, 1),))
            self.assertTrue(info["feasible"])
            self.assertTrue(info["forced_feasibility"])
            self.assertEqual(info["worst_relative_gain"], expected_gain)
            self.assertEqual(info["worst_own_gain"], expected_gain)

    def test_feasible_reference_keeps_strict_positive_rule(self):
        plan, info = _run_selected_optimize(
            self.repaired["selected_sell_core"], (10.0, 10.0, 0.0, 0), reference_feasible=True
        )
        self.assertEqual(tuple(plan), ((0, 0),))
        self.assertFalse(info["accepted"])
        self.assertFalse(info["forced_feasibility"])
        plan, info = _run_selected_optimize(
            self.repaired["selected_sell_core"], (11.0, 11.0, 0.0, 0), reference_feasible=True
        )
        self.assertEqual(tuple(plan), ((0, 1),))
        self.assertTrue(info["accepted"])
        self.assertGreater(info["worst_relative_gain"], 0)

    def test_gain_first_rank_and_joint_tuple_shape(self):
        ranker = _exec_function(self.repaired["frozen_selected"], "seller_choice_rank", {})
        forced_zero = {
            "forced_feasibility": True,
            "worst_relative_gain": 0.0,
            "worst_own_gain": 0.0,
            "acceptance_score": 0.0,
        }
        ordinary_positive = {
            "forced_feasibility": False,
            "accepted": True,
            "worst_relative_gain": 0.25,
            "acceptance_score": 0.25,
        }
        forced_bad_relative = {
            "forced_feasibility": True,
            "worst_relative_gain": -0.01,
            "worst_own_gain": 1.0,
        }
        forced_bad_own = {
            "forced_feasibility": True,
            "worst_relative_gain": 0.0,
            "worst_own_gain": -0.01,
        }
        forced_equal = {
            "forced_feasibility": True,
            "worst_relative_gain": 0.25,
            "worst_own_gain": 0.0,
            "acceptance_score": 0.25,
        }
        self.assertTrue(ranker(forced_zero)[0])
        self.assertTrue(ranker(ordinary_positive)[0])
        self.assertGreater(ranker(ordinary_positive)[1], ranker(forced_zero)[1])
        self.assertGreater(ranker(forced_equal)[1], ranker(ordinary_positive)[1])
        self.assertFalse(ranker(forced_bad_relative)[0])
        self.assertFalse(ranker(forced_bad_own)[0])
        self.assertIn("rank=(independent,False)", self.repaired["frozen_selected"])
        self.assertNotIn("rank=(False,independent)", self.repaired["frozen_selected"])

    def test_exec_pace_preserves_floor_diagnostics_on_forced_bypass(self):
        apply_candidate = _exec_function(self.source["exec_pace_runtime"], "apply_candidate", {})
        info = {
            "forced_feasibility": True,
            "worst_relative_gain": 0.0,
            "worst_own_gain": 0.0,
            "economic_floor_rejections": 3,
        }
        candidate = ((0, 1),)
        selected, observed = apply_candidate(None, "CARROT", ((0, 0),), candidate, info)
        self.assertEqual(selected, candidate)
        self.assertEqual(observed["worst_relative_gain"], 0.0)
        self.assertEqual(observed["worst_own_gain"], 0.0)
        self.assertEqual(observed["economic_floor_rejections"], 3)
        self.assertEqual(observed["exec_pace"]["reason"], "forced-feasibility-bypass")
        self.assertNotIn("exec_pace", info)

    def test_materializer_rejects_source_drift_and_existing_output(self):
        with tempfile.TemporaryDirectory(prefix="v4-floor-test-") as tmp:
            root = Path(tmp)
            bad = root / "selected_sell_core.py"
            bad.write_bytes(self.raw["selected_sell_core"] + b"\n# drift\n")
            out = root / "out.py"
            with self.assertRaisesRegex(ValueError, "source Git blob drifted"):
                floor.materialize("selected_sell_core", bad, out)
            self.assertFalse(out.exists())

            good = root / "good.py"
            good.write_bytes(self.raw["selected_sell_core"])
            out.write_text("occupied", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                floor.materialize("selected_sell_core", good, out)


if __name__ == "__main__":
    unittest.main()
