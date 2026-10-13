# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import gzip
import importlib.util
import json
import lzma
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("hire_occurrence", HERE / "hire_occurrence.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def action(*orders):
    return {"farmer": ["PASS"], "hands": [], "market": [list(x) for x in orders]}


class HireOccurrenceTest(unittest.TestCase):
    def test_poly_separates_terminal_from_earlier_final_day(self):
        record = {
            "seed": 1,
            "candidate_seat": 0,
            "steps": 719,
            "arm": "x",
            "opponent": "y",
            "final_day": [
                {"step": 696, "observation": {"day": 29, "hour": 0},
                 "actions": [action(), action(("HIRE",), ("SELL", "MILK", 2))]},
                {"step": 718, "observation": {"day": 29, "hour": 22},
                 "actions": [action(), action(("SELL", "MILK", 2))]},
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bank.json.xz"
            path.write_bytes(lzma.compress(json.dumps({"r.json": json.dumps(record)}).encode()))
            rows, binding = MODULE.read_poly_bank(path)
        result = MODULE.summarize(rows, [binding])
        self.assertEqual(result["records_with_terminal_hire"], 0)
        self.assertEqual(result["records_with_preterminal_final_day_hire"], 1)
        self.assertEqual(result["terminal_operation_counts"], {"SELL": 1})
        self.assertEqual(
            result["preterminal_final_day_operation_counts"],
            {"HIRE": 1, "SELL": 1},
        )

    def test_terminal_hire_is_counted(self):
        record = {
            "source": "synthetic",
            "record": "a",
            "seed": 2,
            "candidate_seat": 0,
            "opponent": "test",
            "arm": "test",
            "terminal_decision": 718,
            "frames": [
                {"decision": 718, "day": 29, "hour": 22,
                 "action": action(("SELL", "MILK", 1), ("HIRE",))}
            ],
        }
        result = MODULE.summarize([record], [])
        self.assertEqual(result["records_with_terminal_hire"], 1)
        self.assertEqual(result["terminal_operation_counts"], {"HIRE": 1, "SELL": 1})
        self.assertTrue(result["runtime_conclusion"]["reached_terminal_hire_support"])
        self.assertEqual(
            result["runtime_conclusion"]["canonical_feature_default"],
            "requires_separate_causal_evaluation",
        )

    def test_orbit_index_one_maps_to_decision_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "results" / "current").mkdir(parents=True)
            (root / "MANIFEST.json").write_text(json.dumps({
                "schema": "test", "unique_games": 1,
                "current_archive_sha256": "abc",
            }))
            trace = root / "results" / "current" / "case.jsonl.gz"
            summary = {
                "candidate_seat": 0, "steps": 2, "seed": 3,
                "opponent": "z", "candidate_label": "current",
            }
            (trace.with_suffix("").with_suffix(".json")).write_text(json.dumps(summary))
            frames = [
                {"index": 0, "kind": "initial", "actions": [{}, {}],
                 "before": [{"day": 0, "hour": 0}, {"day": 0, "hour": 0}]},
                {"index": 1, "kind": "transition", "actions": [action(), action(("HIRE",))],
                 "before": [{"day": 29, "hour": 0}, {"day": 29, "hour": 0}]},
                {"index": 2, "kind": "transition", "actions": [action(), action(("SELL", "EGG", 1))],
                 "before": [{"day": 29, "hour": 22}, {"day": 29, "hour": 22}]},
            ]
            with gzip.open(trace, "wt", encoding="utf-8") as handle:
                for frame in frames:
                    handle.write(json.dumps(frame) + "\n")
            rows, binding = MODULE.read_orbit_root(root)
        self.assertEqual([x["decision"] for x in rows[0]["frames"]], [0, 1])
        self.assertEqual(binding["current_archive_sha256"], "abc")

    def test_orbit_current_control_hire_sequence_comparison(self):
        common = {
            "seed": 1,
            "candidate_seat": 0,
            "opponent": "x",
            "arm": "x",
            "terminal_decision": 1,
            "frames": [
                {"decision": 0, "day": 29, "hour": 0, "action": action(("HIRE",))},
                {"decision": 1, "day": 29, "hour": 22, "action": action()},
            ],
        }
        result = MODULE.summarize([
            dict(common, source="orbit-current", record="results/current/case.jsonl.gz"),
            dict(common, source="orbit-control", record="results/control/case.jsonl.gz"),
        ], [])
        self.assertEqual(
            result["orbit_current_control_hire_sequence_comparison"],
            {"paired_records": 1, "identical_sequences": 1, "different_record_keys": []},
        )

    def test_source_bound_streams_do_not_cross_deduplicate(self):
        base = {
            "record": "same",
            "seed": 1,
            "candidate_seat": 0,
            "opponent": "x",
            "arm": "x",
            "terminal_decision": 0,
            "frames": [{"decision": 0, "day": 29, "hour": 22, "action": action()}],
        }
        first = dict(base, source="one")
        second = dict(base, source="two")
        result = MODULE.summarize([first, second], [])
        self.assertEqual(result["source_bound_unique_rival_action_streams"], 2)

    def test_same_source_identical_streams_deduplicate(self):
        base = {
            "source": "one",
            "seed": 1,
            "candidate_seat": 0,
            "opponent": "x",
            "arm": "x",
            "terminal_decision": 0,
            "frames": [{"decision": 0, "day": 29, "hour": 22, "action": action()}],
        }
        result = MODULE.summarize([
            dict(base, record="a"), dict(base, record="b")
        ], [])
        self.assertEqual(result["source_bound_unique_rival_action_streams"], 1)
        self.assertEqual(sorted(result["stream_multiplicity"].values()), [2])

    def test_poly_requires_terminal_frame(self):
        record = {
            "candidate_seat": 0, "steps": 719,
            "final_day": [{"step": 696, "observation": {"day": 29, "hour": 0},
                           "actions": [action(), action()]}],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.xz"
            path.write_bytes(lzma.compress(json.dumps({"bad": json.dumps(record)}).encode()))
            with self.assertRaisesRegex(ValueError, "terminal decision 718 is missing"):
                MODULE.read_poly_bank(path)

    def test_orbit_requires_contiguous_decisions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "results" / "current").mkdir(parents=True)
            (root / "MANIFEST.json").write_text(json.dumps({}))
            trace = root / "results" / "current" / "case.jsonl.gz"
            (trace.with_suffix("").with_suffix(".json")).write_text(json.dumps({
                "candidate_seat": 0, "steps": 2,
            }))
            with gzip.open(trace, "wt", encoding="utf-8") as handle:
                handle.write(json.dumps({
                    "index": 2, "kind": "transition",
                    "actions": [action(), action()],
                    "before": [{"day": 29, "hour": 22}, {"day": 29, "hour": 22}],
                }) + "\n")
            with self.assertRaisesRegex(ValueError, "noncontiguous decision sequence"):
                MODULE.read_orbit_root(root)

    def test_invalid_market_shape_fails(self):
        record = {
            "source": "x", "record": "x", "terminal_decision": 0,
            "frames": [{"decision": 0, "day": 29, "hour": 22,
                        "action": {"market": "not-a-list"}}],
        }
        with self.assertRaisesRegex(ValueError, "action.market must be a list"):
            MODULE.summarize([record], [])


if __name__ == "__main__":
    unittest.main()
