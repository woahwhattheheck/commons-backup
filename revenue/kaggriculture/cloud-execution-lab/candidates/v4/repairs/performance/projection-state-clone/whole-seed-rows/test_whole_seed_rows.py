# SPDX-License-Identifier: Apache-2.0
"""Focused source and behavior contracts for V4 whole-row seed chronology."""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import sys
import tempfile
import types
import unittest

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[5]
SOURCE = LAB / "early_capital.py"
SOURCE_BLOB = "1161859ac5af617eca65aec3f732b5c1396cad37"

sys.path.insert(0, str(HERE))
from apply_whole_seed_rows import POST, _sha, _spans, apply  # noqa: E402


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load module from " + str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def configure(module, plant_demand):
    module._project_post_unit_private = lambda *_args, **_kwargs: {"seeds": {}, "shed": {}}
    module._certified_funding = lambda *_args, **_kwargs: (set(), {})
    module._active_order_supported = lambda *_args, **_kwargs: True
    module._plant_demand = plant_demand
    return module


def run_order(module, market):
    mechanics = types.SimpleNamespace(CROPS={"WHEAT": {}}, ANIMALS={})
    selected = {"market": market}
    result, report = module.order_early_capital(
        mechanics,
        {"step": 0},
        {"episodeSteps": 720, "turnsPerDay": 24, "maxMarketOrdersPerTurn": 10},
        selected,
        [],
    )
    return result["market"], report


class WholeSeedRows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = SOURCE.read_bytes()
        if git_blob(cls.raw) != SOURCE_BLOB:
            raise ValueError("current early_capital.py blob drifted; rebase the V4 source admission")
        cls.source = cls.raw.decode("utf-8")
        cls.predecessor = load_module("_v4_seed_rows_predecessor", SOURCE)
        cls.repaired_source = apply(cls.source)
        cls.temp = tempfile.TemporaryDirectory(prefix="v4-whole-seed-rows-")
        cls.candidate_path = Path(cls.temp.name) / "early_capital.py"
        cls.candidate_path.write_text(cls.repaired_source, encoding="utf-8")
        cls.candidate = load_module("_v4_seed_rows_candidate", cls.candidate_path)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_exact_current_source_materializes_expected_post_spans(self):
        spans = _spans(self.repaired_source)
        self.assertEqual({name: _sha(spans[name][2]) for name in POST}, POST)
        self.assertEqual(apply(self.repaired_source), self.repaired_source)
        compile(self.repaired_source, "v4_whole_seed_rows", "exec")

    def test_duplicate_seed_rows_do_not_each_claim_same_deficit(self):
        demand = lambda selected, _route, _now, _horizon: {"WHEAT": 1}
        predecessor = configure(self.predecessor, demand)
        candidate = configure(self.candidate, demand)
        market = [["BUY_LAND"], ["BUY_SEED", "WHEAT", 1], ["BUY_SEED", "WHEAT", 1]]
        before, _ = run_order(predecessor, market)
        after, report = run_order(candidate, market)
        self.assertEqual(before, [market[1], market[2], market[0]])
        self.assertEqual(after, [market[1], market[0], market[2]])
        self.assertEqual(report["operating_seed_rows"], [1])
        self.assertEqual(report["unmet_seed_demand"], {})

    def test_oversized_seed_row_is_indivisible_not_partially_certified(self):
        demand = lambda selected, _route, _now, _horizon: {"WHEAT": 1}
        predecessor = configure(self.predecessor, demand)
        candidate = configure(self.candidate, demand)
        market = [["BUY_LAND"], ["BUY_SEED", "WHEAT", 2]]
        before, _ = run_order(predecessor, market)
        after, report = run_order(candidate, market)
        self.assertEqual(before, [market[1], market[0]])
        self.assertEqual(after, market)
        self.assertEqual(report["operating_seed_rows"], [])
        self.assertEqual(report["unmet_seed_demand"], {"WHEAT": 1})

    def test_current_unit_stage_is_not_counted_again_as_future_seed_demand(self):
        def demand(selected, _route, _now, _horizon):
            return {"WHEAT": 1} if selected is not None else {}

        predecessor = configure(self.predecessor, demand)
        candidate = configure(self.candidate, demand)
        market = [["BUY_LAND"], ["BUY_SEED", "WHEAT", 1]]
        before, _ = run_order(predecessor, market)
        after, report = run_order(candidate, market)
        self.assertEqual(before, [market[1], market[0]])
        self.assertEqual(after, market)
        self.assertEqual(report["operating_seed_rows"], [])

    def test_subset_maximizes_whole_units_then_earliest_authored_indices(self):
        mechanics = types.SimpleNamespace(CROPS={"WHEAT": {}})
        active = [
            ["BUY_SEED", "WHEAT", 2],
            ["BUY_SEED", "WHEAT", 1],
            ["BUY_SEED", "WHEAT", 3],
        ]
        operating, allocations, remaining = self.candidate._operating_seed_rows(
            active, mechanics, {"WHEAT": 3}, {}
        )
        self.assertEqual(operating, {0, 1})
        self.assertEqual([row["index"] for row in allocations], [0, 1])
        self.assertEqual(remaining, {"WHEAT": 0})

    def test_disjoint_projection_composition_does_not_break_admission(self):
        changed_elsewhere = self.source.replace(
            "def _project_post_unit_private(",
            "# projection-state-clone owns this disjoint span\ndef _project_post_unit_private(",
            1,
        )
        repaired = apply(changed_elsewhere)
        spans = _spans(repaired)
        self.assertEqual({name: _sha(spans[name][2]) for name in POST}, POST)

    def test_target_span_drift_fails_closed(self):
        tampered = self.source.replace(
            "return OPERATING if need > 0 else REST",
            "return OPERATING if need >= 0 else REST",
            1,
        )
        with self.assertRaisesRegex(ValueError, "source changed"):
            apply(tampered)


if __name__ == "__main__":
    unittest.main()
