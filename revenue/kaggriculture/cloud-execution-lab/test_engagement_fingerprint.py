# SPDX-License-Identifier: Apache-2.0
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import engagement_fingerprint as ef


CONTROL_ID = "v5c:" + "1" * 64
CANDIDATE_ID = "v5c:" + "2" * 64
OTHER_ID = "v5c:" + "3" * 64


class EngagementFingerprintTests(unittest.TestCase):
    def test_mapping_order_is_canonical(self):
        left = {"b": [1, True], "a": {"x": -0.0}}
        right = {"a": {"x": -0.0}, "b": [1, True]}
        self.assertEqual(ef.fingerprint(left), ef.fingerprint(right))

    def test_typed_scalars_do_not_collapse(self):
        self.assertNotEqual(ef.fingerprint(True), ef.fingerprint(1))
        self.assertNotEqual(ef.fingerprint(-0.0), ef.fingerprint(0.0))
        self.assertNotEqual(ef.fingerprint(["1"]), ef.fingerprint([1]))

    def test_non_finite_values_fail_closed(self):
        with self.assertRaises(ef.FingerprintError):
            ef.fingerprint(float("nan"))
        with self.assertRaises(ef.FingerprintError):
            ef.fingerprint(float("inf"))

    def test_noop_requires_threshold(self):
        tracker = ef.EngagementTracker(noop_threshold=3)
        for step in range(2):
            tracker.observe(
                {"seed": 5, "seat": 0, "step": step, "phase": "unit"},
                [["MOVE", 1]],
                [["MOVE", 1]],
            )
        self.assertEqual("INSUFFICIENT", tracker.summary()["classification"])
        self.assertFalse(tracker.observed_noop)

        tracker.observe(
            {"seed": 5, "seat": 0, "step": 2, "phase": "unit"},
            [["MOVE", 1]],
            [["MOVE", 1]],
        )
        self.assertEqual("NO_OP_OBSERVED", tracker.summary()["classification"])
        self.assertTrue(tracker.observed_noop)

    def test_first_divergence_and_sequence_fingerprints(self):
        tracker = ef.EngagementTracker(noop_threshold=2)
        tracker.observe(
            {"seed": 7, "seat": 1, "step": 10, "phase": "market"},
            [["SELL", "MILK", 1]],
            [["SELL", "MILK", 1]],
        )
        tracker.observe(
            {"seed": 7, "seat": 1, "step": 11, "phase": "market"},
            [["SELL", "MILK", 1]],
            [["SELL", "MILK", 2]],
        )
        summary = tracker.summary()
        self.assertEqual("ENGAGED", summary["classification"])
        self.assertEqual(1, summary["divergence_count"])
        self.assertEqual(0.5, summary["engagement_rate"])
        self.assertEqual(2, summary["first_divergence"]["observation"])
        self.assertEqual(11, summary["first_divergence"]["key"]["step"])
        self.assertNotEqual(
            summary["control_sequence_fingerprint"],
            summary["candidate_sequence_fingerprint"],
        )

    def test_duplicate_alignment_key_fails_closed(self):
        tracker = ef.EngagementTracker()
        row = {"seed": 1, "seat": 0, "step": 4, "phase": "unit"}
        tracker.observe(row, [], [])
        with self.assertRaises(ef.AlignmentError):
            tracker.observe(row, [], [])

    def test_missing_alignment_field_fails_closed(self):
        with self.assertRaises(ef.AlignmentError):
            ef.compare_rows(
                [{"seed": 1, "seat": 0, "step": 0, "control": [], "candidate": []}]
            )

    def test_custom_payload_fields(self):
        report = ef.compare_rows(
            [
                {
                    "seed": 1,
                    "seat": 0,
                    "step": 0,
                    "phase": "unit",
                    "baseline_action": ["WAIT"],
                    "variant_action": ["MOVE", 2],
                }
            ],
            control_field="baseline_action",
            candidate_field="variant_action",
            noop_threshold=1,
        )
        self.assertEqual("ENGAGED", report["classification"])

    def test_self_comparison_payload_alias_fails_closed(self):
        row = {
            "seed": 3,
            "seat": 0,
            "step": 7,
            "phase": "market",
            "control": [["SELL", "MILK", 1]],
            "candidate": [["SELL", "MILK", 2]],
        }
        with self.assertRaisesRegex(ef.AlignmentError, "must be distinct"):
            ef.compare_rows(
                [row],
                control_field="control",
                candidate_field="control",
                noop_threshold=1,
            )

    def test_payload_field_cannot_be_part_of_alignment_key(self):
        row = {
            "seed": 3,
            "seat": 0,
            "step": 7,
            "control": [["WAIT"]],
            "candidate": [["MOVE", 1]],
        }
        with self.assertRaisesRegex(ef.AlignmentError, "cannot be alignment key fields"):
            ef.compare_rows(
                [row],
                key_fields=("seed", "seat", "step", "candidate"),
                noop_threshold=1,
            )

    def test_alignment_field_names_must_be_unique_nonempty_strings(self):
        with self.assertRaisesRegex(ef.AlignmentError, "must be unique"):
            ef.EngagementTracker(key_fields=("seed", "seed"))
        with self.assertRaisesRegex(ef.AlignmentError, "non-empty strings"):
            ef.EngagementTracker(key_fields=("seed", ""))
        with self.assertRaisesRegex(ef.AlignmentError, "at least one"):
            ef.EngagementTracker(key_fields="seed")

    def test_legacy_report_shape_has_no_identity_keys(self):
        report = ef.compare_rows(
            [{
                "seed": 1, "seat": 0, "step": 0, "phase": "unit",
                "control": ["WAIT"], "candidate": ["WAIT"],
            }],
            noop_threshold=1,
        )
        self.assertNotIn("control_id", report)
        self.assertNotIn("candidate_id", report)

    def test_consistent_identities_bind_and_report(self):
        rows = [
            {
                "seed": 1, "seat": 0, "step": step, "phase": "unit",
                "control": ["WAIT"], "candidate": ["WAIT"],
                "control_id": CONTROL_ID, "candidate_id": CANDIDATE_ID,
            }
            for step in range(2)
        ]
        report = ef.compare_rows(rows, noop_threshold=2)
        self.assertEqual(CONTROL_ID, report["control_id"])
        self.assertEqual(CANDIDATE_ID, report["candidate_id"])
        self.assertEqual("NO_OP_OBSERVED", report["classification"])

    def test_mixed_identity_fails_closed(self):
        rows = [
            {
                "seed": 1, "seat": 0, "step": 0, "phase": "unit",
                "control": [], "candidate": [],
                "candidate_id": CANDIDATE_ID,
            },
            {
                "seed": 1, "seat": 0, "step": 1, "phase": "unit",
                "control": [], "candidate": [],
                "candidate_id": OTHER_ID,
            },
        ]
        with self.assertRaisesRegex(ef.AlignmentError, "mixed identity"):
            ef.compare_rows(rows)

    def test_missing_identity_after_binding_fails_closed(self):
        rows = [
            {
                "seed": 1, "seat": 0, "step": 0, "phase": "unit",
                "control": [], "candidate": [], "candidate_id": CANDIDATE_ID,
            },
            {
                "seed": 1, "seat": 0, "step": 1, "phase": "unit",
                "control": [], "candidate": [],
            },
        ]
        with self.assertRaisesRegex(ef.AlignmentError, "missing bound identity"):
            ef.compare_rows(rows)

    def test_late_identity_after_unbound_evidence_fails_closed(self):
        rows = [
            {
                "seed": 1, "seat": 0, "step": 0, "phase": "unit",
                "control": [], "candidate": [],
            },
            {
                "seed": 1, "seat": 0, "step": 1, "phase": "unit",
                "control": [], "candidate": [], "candidate_id": CANDIDATE_ID,
            },
        ]
        with self.assertRaisesRegex(ef.AlignmentError, "appears after unbound evidence"):
            ef.compare_rows(rows)

    def test_expected_identity_requires_exact_row_stamp(self):
        row = {
            "seed": 1, "seat": 0, "step": 0, "phase": "unit",
            "control": [], "candidate": [], "candidate_id": CANDIDATE_ID,
        }
        report = ef.compare_rows([row], candidate_id=CANDIDATE_ID)
        self.assertEqual(CANDIDATE_ID, report["candidate_id"])
        with self.assertRaisesRegex(ef.AlignmentError, "mixed identity"):
            ef.compare_rows([row], candidate_id=OTHER_ID)
        no_stamp = dict(row)
        no_stamp.pop("candidate_id")
        with self.assertRaisesRegex(ef.AlignmentError, "missing bound identity"):
            ef.compare_rows([no_stamp], candidate_id=CANDIDATE_ID)

    def test_malformed_identity_fails_closed(self):
        row = {
            "seed": 1, "seat": 0, "step": 0, "phase": "unit",
            "control": [], "candidate": [], "candidate_id": "v5c:NOT-A-DIGEST",
        }
        with self.assertRaisesRegex(ef.AlignmentError, "64 lowercase hex"):
            ef.compare_rows([row])

    def test_identity_field_names_cannot_alias_payload_or_alignment(self):
        row = {
            "seed": 1, "seat": 0, "step": 0, "phase": "unit",
            "control": [], "candidate": [],
        }
        with self.assertRaisesRegex(ef.AlignmentError, "cannot be payload"):
            ef.compare_rows([row], candidate_id_field="candidate")
        with self.assertRaisesRegex(ef.AlignmentError, "cannot be payload"):
            ef.compare_rows([row], control_id_field="seed")
        with self.assertRaisesRegex(ef.AlignmentError, "must be distinct"):
            ef.compare_rows(
                [row], control_id_field="build_id", candidate_id_field="build_id"
            )

    def test_cli_emits_machine_readable_report(self):
        rows = [
            {
                "seed": 9,
                "seat": 0,
                "step": step,
                "phase": "unit",
                "control": ["WAIT"],
                "candidate": ["WAIT"],
            }
            for step in range(3)
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "paired.jsonl"
            path.write_text(
                "".join(json.dumps(row) + "\n" for row in rows),
                encoding="utf-8",
            )
            proc = subprocess.run(
                [
                    sys.executable,
                    str(Path(ef.__file__)),
                    str(path),
                    "--noop-threshold",
                    "3",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        report = json.loads(proc.stdout)
        self.assertEqual("NO_OP_OBSERVED", report["classification"])
        self.assertEqual(3, report["observations"])

    def test_cli_rejects_duplicate_key(self):
        row = {
            "seed": 9,
            "seat": 0,
            "step": 0,
            "phase": "unit",
            "control": ["WAIT"],
            "candidate": ["WAIT"],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "paired.jsonl"
            path.write_text(json.dumps(row) + "\n" + json.dumps(row) + "\n", encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(Path(ef.__file__)), str(path)],
                capture_output=True,
                text=True,
            )
        self.assertEqual(2, proc.returncode)
        self.assertIn("duplicate matched key", proc.stderr)

    def test_cli_rejects_payload_self_comparison(self):
        row = {
            "seed": 9,
            "seat": 0,
            "step": 0,
            "phase": "unit",
            "control": ["WAIT"],
            "candidate": ["MOVE", 1],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "paired.jsonl"
            path.write_text(json.dumps(row) + "\n", encoding="utf-8")
            proc = subprocess.run(
                [
                    sys.executable,
                    str(Path(ef.__file__)),
                    str(path),
                    "--control-field",
                    "control",
                    "--candidate-field",
                    "control",
                    "--noop-threshold",
                    "1",
                ],
                capture_output=True,
                text=True,
            )
        self.assertEqual(2, proc.returncode)
        self.assertIn("must be distinct", proc.stderr)

    def test_cli_expected_identity_rejects_unstamped_trace(self):
        row = {
            "seed": 9, "seat": 0, "step": 0, "phase": "unit",
            "control": ["WAIT"], "candidate": ["WAIT"],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "paired.jsonl"
            path.write_text(json.dumps(row) + "\n", encoding="utf-8")
            proc = subprocess.run(
                [
                    sys.executable, str(Path(ef.__file__)), str(path),
                    "--candidate-id", CANDIDATE_ID,
                ],
                capture_output=True,
                text=True,
            )
        self.assertEqual(2, proc.returncode)
        self.assertIn("missing bound identity", proc.stderr)


if __name__ == "__main__":
    unittest.main()
