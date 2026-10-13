"""Report-consumer tests; records are telemetry fixtures, not game results."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import observe
import report

HERE = Path(__file__).resolve().parent


def row(step, gate=None, **changes):
    result = {"schema": observe.SCHEMA, "source_sha256": observe.SOURCE_SHA256,
              "match_id": "fixture", "seat": 0, "observed_step": step,
              "controller_step": step, "gate_before": gate, "gate_after": gate,
              "gate_changed": False, "gate_evaluated_this_call": False,
              "expert_before": None, "expert_after": None,
              "telemetry_error": None, "cached_retry": False, "route": "v5/low"}
    result.update(changes)
    return result


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source, self.output = self.root / "input.jsonl", self.root / "output.json"

    def write(self, rows):
        self.source.write_text("".join(json.dumps(value) + "\n" for value in rows), encoding="utf-8")

    def cli(self):
        return subprocess.run([sys.executable, str(HERE / "report.py"), "--input", str(self.source),
                               "--output", str(self.output)], capture_output=True, text=True)

    def test_matches_existing_aggregator_without_controller(self):
        rows = [row(71), row(72, True, gate_before=None, gate_changed=True,
                            gate_evaluated_this_call=True), row(72, True, cached_retry=True),
                row(168, True, expert_after="high", route="v5/high"),
                row(169, False, match_id="other", seat=1, route="v7/current/8c6s_3q")]
        self.write(rows)
        original = self.source.read_bytes()
        with patch.object(observe, "CokObserver", side_effect=AssertionError("No policy loading")):
            actual = report.build_report(self.source, self.output)
        self.assertEqual(actual, observe.summarize(copy.deepcopy(rows)))
        self.assertEqual(json.loads(self.output.read_text()), actual)
        self.assertEqual(self.source.read_bytes(), original)
        self.assertEqual(self.cli().returncode, 0)
        self.assertEqual(len(actual["actors"]), 2)
        self.assertEqual(actual["actors"][0]["cached_retries"], 1)

    def test_invalid_source_or_schema_preserves_previous_report(self):
        self.output.write_bytes(b"previous-report\n")
        for changed in ({"source_sha256": "wrong"}, {"schema": "other"}):
            self.write([row(0), row(72, **changed)])
            self.assertEqual(self.cli().returncode, 2)
            self.assertEqual(self.output.read_bytes(), b"previous-report\n")
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["input.jsonl", "output.json"])

    def test_errors_are_reported_without_inventing_game_results(self):
        self.write([row(0, telemetry_error="ValueError"), row(72, False, expected_action_matches=False)])
        self.assertEqual(self.cli().returncode, 1)
        actor = json.loads(self.output.read_text())["actors"][0]
        self.assertEqual(actor["telemetry_errors"], 1)
        self.assertEqual(actor["expected_action_mismatches"], 1)
        self.assertNotIn("wins", actor)
        self.assertFalse(actor["has_every_step_0_through_718"])

    def test_invalid_json_and_nonobject_are_line_labeled(self):
        for value in ('{}\n{"unfinished":\n', '{}\n[]\n'):
            self.source.write_text(value)
            with self.assertRaisesRegex(ValueError, "line 2"):
                list(report.records(self.source))
        self.assertFalse(self.output.exists())

    def test_input_aliases_and_failed_replace_preserve_inputs(self):
        self.write([row(0)])
        before = self.source.read_bytes()
        with self.assertRaises(ValueError):
            report.build_report(self.source, self.source)
        alias = self.root / "alias.jsonl"
        os.link(self.source, alias)
        with self.assertRaises(ValueError):
            report.build_report(self.source, alias)
        self.output.write_bytes(b"old\n")
        with patch.object(report.os, "replace", side_effect=OSError("unavailable")):
            with self.assertRaises(OSError):
                report.build_report(self.source, self.output)
        self.assertEqual(self.source.read_bytes(), before)
        self.assertEqual(self.output.read_bytes(), b"old\n")
        self.assertFalse(list(self.root.glob(".output.json.*")))

    def test_streaming_iterator_and_empty_input(self):
        self.source.write_text("\n" + json.dumps(row(0)) + "\nnot-json\n")
        iterator = report.records(self.source)
        self.assertEqual(next(iterator)["observed_step"], 0)
        with self.assertRaises(ValueError):
            next(iterator)
        self.source.write_text("\n\n")
        result = report.build_report(self.source, self.output)
        self.assertEqual(result["actors"], [])
        self.assertEqual(self.cli().returncode, 0)


if __name__ == "__main__":
    unittest.main()
