# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import engagement_fingerprint as ef


class EngagementJsonlInputCustodyTests(unittest.TestCase):
    def _read(self, text: str):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "paired.jsonl"
            path.write_text(text + "\n", encoding="utf-8")
            return list(ef._read_jsonl(path))

    def test_valid_canonical_row_preserves_semantics(self):
        row = {
            "seed": 7,
            "seat": 0,
            "step": 12,
            "phase": "market",
            "control": [["SELL", "MILK", 1]],
            "candidate": [["SELL", "MILK", 2]],
        }
        parsed = self._read(json.dumps(row, separators=(",", ":")))
        self.assertEqual([row], parsed)
        report = ef.compare_rows(parsed, noop_threshold=1)
        self.assertEqual("ENGAGED", report["classification"])
        self.assertEqual(1, report["divergence_count"])

    def test_duplicate_top_level_members_fail_before_alignment(self):
        cases = {
            "identity": '{"seed":7,"seat":0,"step":12,"phase":"unit","control":[],"candidate":[],"candidate_id":"v5c:'
            + "1" * 64
            + '","candidate_id":"v5c:'
            + "2" * 64
            + '"}',
            "alignment": '{"seed":7,"seed":8,"seat":0,"step":12,"phase":"unit","control":[],"candidate":[]}',
            "decision": '{"seed":7,"seat":0,"step":12,"phase":"unit","control":["WAIT"],"control":["MOVE",1],"candidate":[]}',
        }
        for label, text in cases.items():
            with self.subTest(label=label):
                with self.assertRaisesRegex(ef.AlignmentError, "duplicate JSON object key"):
                    self._read(text)

    def test_nested_duplicate_decision_member_fails_closed(self):
        text = (
            '{"seed":7,"seat":0,"step":12,"phase":"unit",'
            '"control":{"worker":{"x":1,"x":2}},"candidate":{}}'
        )
        with self.assertRaisesRegex(ef.AlignmentError, "duplicate JSON object key: x"):
            self._read(text)

    def test_nonstandard_numeric_constants_fail_at_json_boundary(self):
        for token in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(token=token):
                text = (
                    '{"seed":7,"seat":0,"step":12,"phase":"unit",'
                    '"control":{"value":'
                    + token
                    + '},"candidate":{}}'
                )
                with self.assertRaisesRegex(ef.AlignmentError, "non-standard JSON number"):
                    self._read(text)

    def test_cli_returns_two_and_reports_line_for_ambiguous_row(self):
        text = '{"seed":7,"seed":8,"seat":0,"step":12,"phase":"unit","control":[],"candidate":[]}'
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "paired.jsonl"
            path.write_text(text + "\n", encoding="utf-8")
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                rc = ef.main([str(path), "--noop-threshold", "1"])
        self.assertEqual(2, rc)
        message = stderr.getvalue()
        self.assertIn(f"{path}:1: invalid JSON", message)
        self.assertIn("duplicate JSON object key: seed", message)


if __name__ == "__main__":
    unittest.main()
