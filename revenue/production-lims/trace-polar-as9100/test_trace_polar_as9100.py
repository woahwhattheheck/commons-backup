import copy
import json
import tempfile
import unittest
from pathlib import Path

import trace_polar_as9100 as polar


class PolarAs9100Tests(unittest.TestCase):
    def setUp(self):
        self.steps, self.manifest = polar.load_fixture()

    def test_fixture_expands_to_three_wafers_and_36_steps(self):
        self.assertEqual(36, len(self.steps))
        self.assertEqual({"W1": 12, "W2": 12, "W3": 12}, {
            wafer: sum(step["wafer_id"] == wafer for step in self.steps)
            for wafer in ("W1", "W2", "W3")
        })

    def test_exact_statuses_three_exceptions_and_three_evidence_packs(self):
        shadow = polar.PolarAs9100Shadow()
        result = shadow.replay(self.steps, self.manifest)
        self.assertEqual(polar.EXPECTED_STATUSES, result.statuses)
        self.assertEqual(1, result.review_ready)
        self.assertEqual(2, result.held)
        self.assertEqual(3, result.exceptions_added)
        self.assertEqual(3, result.packs_added)
        self.assertEqual(3, len(shadow.evidence_packs))

    def test_w2_has_only_revision_exception(self):
        shadow = polar.PolarAs9100Shadow()
        shadow.replay(self.steps, self.manifest)
        rows = [row for row in shadow.exceptions if row["wafer_id"] == "W2"]
        self.assertEqual(1, len(rows))
        self.assertEqual("RECIPE_REVISION_MISMATCH", rows[0]["code"])
        self.assertEqual("R3", rows[0]["observed"])
        self.assertEqual("R4", rows[0]["expected"])

    def test_w3_has_expired_calibration_and_blank_signoff_as_two_rows(self):
        shadow = polar.PolarAs9100Shadow()
        shadow.replay(self.steps, self.manifest)
        rows = [row for row in shadow.exceptions if row["wafer_id"] == "W3"]
        self.assertEqual(2, len(rows))
        self.assertEqual({"CALIBRATION_EXPIRED", "OPERATOR_SIGNATURE_MISSING"}, {row["code"] for row in rows})
        self.assertEqual("HOLD_CAL_AND_SIGNATURE", shadow.evidence_packs["W3"]["status"])

    def test_evidence_packs_preserve_all_step_hashes(self):
        shadow = polar.PolarAs9100Shadow()
        shadow.replay(self.steps, self.manifest)
        for wafer in ("W1", "W2", "W3"):
            expected = [step["source_sha256"] for step in self.steps if step["wafer_id"] == wafer]
            self.assertEqual(expected, shadow.evidence_packs[wafer]["source_step_hashes"])
            self.assertEqual(12, shadow.evidence_packs[wafer]["step_count"])
            self.assertEqual("STAGED_HUMAN_DISPOSITION", shadow.evidence_packs[wafer]["disposition_state"])
            self.assertFalse(shadow.evidence_packs[wafer]["sent"])

    def test_full_replay_adds_zero_state_and_hashes_are_stable(self):
        shadow = polar.PolarAs9100Shadow()
        first = shadow.replay(self.steps, self.manifest)
        second = shadow.replay(self.steps, self.manifest)
        self.assertEqual(3, second.replayed)
        self.assertEqual((0, 0, 0), (second.exceptions_added, second.packs_added, second.events_added))
        self.assertEqual(first.state_digest, second.state_digest)
        self.assertEqual(first.evidence_manifest_sha256, second.evidence_manifest_sha256)

    def test_read_only_authoritative_snapshot_is_unchanged(self):
        authoritative = {"qms": {"ncr_count": 2}, "traveler": {"mode": "read-only"}}
        before = copy.deepcopy(authoritative)
        shadow = polar.PolarAs9100Shadow(authoritative)
        fingerprint = shadow.authoritative_fingerprint
        shadow.replay(self.steps, self.manifest)
        self.assertEqual(before, authoritative)
        self.assertEqual(fingerprint, shadow.authoritative_fingerprint)

    def test_human_disposition_is_copy_only_and_automatic_is_disabled(self):
        shadow = polar.PolarAs9100Shadow()
        shadow.replay(self.steps, self.manifest)
        original = copy.deepcopy(shadow.evidence_packs["W1"])
        for bad in (
            "", "system", "bot", "AI", "Jordan",
            "System Reviewer", "AI Reviewer", "Bot Reviewer",
            "system/reviewer", "pipeline_reviewer", "service-account reviewer",
            "Worker.Reviewer",
            "System2 Operator", "AI2 Reviewer", "bot123 user",
            "agent007 reviewer", "service2 account",
        ):
            with self.assertRaises(PermissionError):
                shadow.disposition_copy("W1", bad)
        released = shadow.disposition_copy("W1", "Jordan Reviewer")
        self.assertEqual("APPROVED_FOR_HUMAN_DISPOSITION", released["disposition_state"])
        self.assertEqual("Jordan Reviewer", released["disposed_by"])
        self.assertFalse(released["sent"])
        self.assertEqual(original, shadow.evidence_packs["W1"])
        with self.assertRaises(PermissionError) as held:
            shadow.disposition_copy("W2", "Jordan Reviewer")
        self.assertEqual("held evidence cannot release a report", str(held.exception))
        with self.assertRaises(PermissionError) as automatic:
            shadow.automatic_disposition("W1")
        self.assertEqual("automatic release is disabled", str(automatic.exception))

    def test_fixture_and_manifest_tampering_fail_closed(self):
        module_dir = Path(polar.__file__).resolve().parent
        fixture = module_dir / "fixtures" / "polar_as9100_3_wafers.json"
        manifest_file = module_dir / "fixtures" / "manifest.json"
        manifest = json.loads(manifest_file.read_text())
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            bad_fixture = tmp / "fixture.json"
            bad_fixture.write_text(fixture.read_text().replace('"steps_per_wafer":12', '"steps_per_wafer":11'))
            with self.assertRaises(polar.IntegrityError):
                polar.load_fixture(bad_fixture, manifest_file)
            bad_manifest = dict(manifest)
            bad_manifest["expected_exception_count"] = 2
            bad_manifest_path = tmp / "manifest.json"
            bad_manifest_path.write_text(json.dumps(bad_manifest, sort_keys=True))
            with self.assertRaises(polar.IntegrityError):
                polar.load_fixture(fixture, bad_manifest_path)

    def test_cli_acceptance_summary(self):
        result = polar.run_acceptance()
        self.assertEqual(36, result["step_count"])
        self.assertEqual(polar.EXPECTED_STATUSES, result["statuses"])
        self.assertEqual(3, result["exception_count"])
        self.assertEqual(3, result["evidence_pack_count"])
        self.assertTrue(result["replay_zero_add"])
        self.assertEqual("APPROVED_FOR_HUMAN_DISPOSITION", result["human_disposition_state"])
        self.assertFalse(result["sent"])


if __name__ == "__main__":
    unittest.main()
