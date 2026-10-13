#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "engagement_census",
    HERE / "engagement_census.py",
)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


def digest(ch="a"):
    return ch * 64


class EngagementCensus(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "pkg").mkdir()
        self.source = self.root / "pkg" / "component.py"
        self.source.write_text("x = 1\n", encoding="utf-8")
        self.blob = mod.git_blob_sha1(self.source.read_bytes())

    def tearDown(self):
        self.tmp.cleanup()

    def record(
        self,
        panel_id,
        kind,
        counts,
        *,
        component="alpha",
        completed=True,
        errors=0,
    ):
        return {
            "component": component,
            "bindings": [{"path": "pkg/component.py", "git_blob": self.blob}],
            "panel": {
                "id": panel_id,
                "kind": kind,
                "sha256": digest("a" if kind == "positive_control" else "b"),
            },
            "counters": dict(zip(mod.COUNTER_KEYS, counts)),
            "completed": completed,
            "error_count": errors,
        }

    def analyze(self, records):
        return mod.analyze(
            {"schema": mod.EVIDENCE_SCHEMA, "records": records},
            self.root,
        )

    def test_engaged_requires_natural_output_change(self):
        report = self.analyze([
            self.record("control", "positive_control", [10, 5, 4, 3, 2]),
            self.record("natural", "natural", [100, 20, 8, 3, 1]),
        ])
        row = report["components"][0]
        self.assertEqual(row["state"], "ENGAGED")
        self.assertEqual(row["natural_state"], "NATURAL_OUTPUT_CHANGED")

    def test_natural_zero_is_not_kill_when_control_works(self):
        report = self.analyze([
            self.record("control", "positive_control", [10, 5, 4, 3, 1]),
            self.record("natural", "natural", [100, 20, 0, 0, 0]),
        ])
        row = report["components"][0]
        self.assertEqual(row["state"], "CONTROL_PROVEN_NATURAL_ZERO")
        self.assertEqual(row["natural_state"], "NATURAL_WIRED_ZERO_ELIGIBILITY")

    def test_positive_control_catches_unwired_component(self):
        report = self.analyze([
            self.record("control", "positive_control", [10, 0, 0, 0, 0])
        ])
        self.assertEqual(report["components"][0]["state"], "CONTROL_UNWIRED")

    def test_positive_control_catches_no_output_change(self):
        report = self.analyze([
            self.record("control", "positive_control", [10, 5, 4, 3, 0])
        ])
        self.assertEqual(
            report["components"][0]["state"],
            "CONTROL_NO_OUTPUT_CHANGE",
        )

    def test_each_positive_control_is_a_separate_proof_obligation(self):
        report = self.analyze([
            self.record("live", "positive_control", [10, 5, 4, 3, 1]),
            self.record("dead", "positive_control", [10, 0, 0, 0, 0]),
        ])
        self.assertEqual(report["components"][0]["state"], "CONTROL_UNWIRED")

    def test_missing_positive_control_is_insufficient(self):
        report = self.analyze([
            self.record("natural", "natural", [10, 2, 0, 0, 0])
        ])
        self.assertEqual(
            report["components"][0]["state"],
            "INSUFFICIENT_POSITIVE_CONTROL",
        )

    def test_natural_execution_failure_not_hidden_after_good_control(self):
        report = self.analyze([
            self.record("control", "positive_control", [10, 5, 4, 3, 1]),
            self.record(
                "natural",
                "natural",
                [5, 1, 0, 0, 0],
                completed=False,
                errors=1,
            ),
        ])
        self.assertEqual(
            report["components"][0]["state"],
            "NATURAL_EXECUTION_FAILED",
        )

    def test_counter_monotonicity_fails_closed(self):
        with self.assertRaises(mod.DataError):
            self.analyze([
                self.record("control", "positive_control", [10, 2, 3, 0, 0])
            ])

    def test_bool_count_fails_closed(self):
        row = self.record("control", "positive_control", [10, 5, 4, 3, 1])
        row["counters"]["entry_calls"] = True
        with self.assertRaises(mod.DataError):
            self.analyze([row])

    def test_blob_drift_fails_closed(self):
        row = self.record("control", "positive_control", [10, 5, 4, 3, 1])
        self.source.write_text("x = 2\n", encoding="utf-8")
        with self.assertRaises(mod.DataError):
            self.analyze([row])

    def test_path_escape_fails_closed(self):
        row = self.record("control", "positive_control", [10, 5, 4, 3, 1])
        row["bindings"][0]["path"] = "../component.py"
        with self.assertRaises(mod.DataError):
            self.analyze([row])

    def test_inconsistent_bindings_across_panels_fail(self):
        other = self.root / "pkg" / "other.py"
        other.write_text("y = 2\n", encoding="utf-8")
        row1 = self.record("control", "positive_control", [10, 5, 4, 3, 1])
        row2 = self.record("natural", "natural", [10, 5, 0, 0, 0])
        row2["bindings"] = [{
            "path": "pkg/other.py",
            "git_blob": mod.git_blob_sha1(other.read_bytes()),
        }]
        with self.assertRaises(mod.DataError):
            self.analyze([row1, row2])

    def test_duplicate_panel_ids_fail(self):
        with self.assertRaises(mod.DataError):
            self.analyze([
                self.record("same", "positive_control", [10, 5, 4, 3, 1]),
                self.record("same", "natural", [10, 5, 0, 0, 0]),
            ])

    def test_deterministic_component_order_and_counts(self):
        records = [
            self.record(
                "c2",
                "positive_control",
                [10, 5, 4, 3, 1],
                component="zeta",
            ),
            self.record(
                "c1",
                "positive_control",
                [10, 5, 4, 3, 1],
                component="alpha",
            ),
        ]
        report = self.analyze(records)
        self.assertEqual(
            [row["component"] for row in report["components"]],
            ["alpha", "zeta"],
        )
        self.assertEqual(
            report["state_counts"],
            {"CONTROL_PROVEN_NATURAL_ZERO": 2},
        )
        json.dumps(report, allow_nan=False, sort_keys=True)


if __name__ == "__main__":
    unittest.main()
