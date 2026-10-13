#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("bowser_morner_gate", HERE / "bowser_morner_gate.py")
gate = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = gate
SPEC.loader.exec_module(gate)
FIXTURE = HERE / "fixtures" / "bowser_120_specimens.json.gz.b64"
MANIFEST = HERE / "fixtures" / "manifest.json"


class BowserMornerGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.specimens, cls.run_qc = gate.load_fixture(FIXTURE)
        cls.result = gate.run_gate(cls.specimens, cls.run_qc)
        cls.fixture_manifest = json.loads(MANIFEST.read_text())

    def test_fixture_signed_and_frozen(self):
        self.assertEqual(gate.sha256_file(FIXTURE), self.fixture_manifest["fixture_archive_sha256"])
        self.assertEqual(len(self.specimens), 120)

    def test_exact_100_route_20_hold(self):
        self.assertEqual(self.result.manifest["routed_count"], 100)
        self.assertEqual(self.result.manifest["intake_hold_count"], 20)
        self.assertEqual(
            self.result.manifest["intake_hold_counts"],
            {
                gate.HOLD_DUPLICATE: 6,
                gate.HOLD_INCOMPLETE: 7,
                gate.HOLD_SCOPE: 7,
            },
        )

    def test_all_five_service_classes_use_golden_route(self):
        for row in self.result.manifest["routed"]:
            expected = gate.ROUTES[row["service_class"]]
            self.assertEqual(row["lab_namespace"], expected["lab"])
            self.assertEqual(row["controlled_method"], expected["method"])
            self.assertEqual(row["method_revision"], expected["revision"])
            self.assertEqual(row["preparation"], expected["preparation"])

    def test_namespace_and_lineage_are_unique_and_complete(self):
        routed = self.result.manifest["routed"]
        accessions = [row["accession_id"] for row in routed]
        self.assertEqual(len(accessions), len(set(accessions)))
        self.assertTrue(all(row["source_sha256"] and row["custody"] for row in routed))
        self.assertTrue(all(row["lab_namespace"] in {"DAYTON", "TOLEDO", "SPRINGFIELD"} for row in routed))

    def test_forced_calibration_defect_blocks_entire_associated_run(self):
        blocked_run = "TOL-AGG-03"
        run = next(row for row in self.result.manifest["runs"] if row["run_id"] == blocked_run)
        self.assertEqual(run["status"], gate.QA_HOLD_CAL)
        reports = [row for row in self.result.manifest["reports"] if row["run_id"] == blocked_run]
        self.assertGreater(len(reports), 0)
        self.assertTrue(all(row["status"] == gate.QA_HOLD_CAL for row in reports))
        clear = [row for row in self.result.manifest["reports"] if row["run_id"] != blocked_run]
        self.assertTrue(all(row["status"] == gate.STAGED for row in clear))

    def test_intake_holds_never_enter_worklist_or_reports(self):
        held_ids = {row["specimen_id"] for row in self.result.manifest["holds"] if row["specimen_id"]}
        routed_ids = {row["specimen_id"] for row in self.result.manifest["routed"]}
        # Duplicate defects intentionally reuse a valid source ID; every other held source is absent.
        duplicate_ids = {row["specimen_id"] for row in self.result.manifest["holds"] if row["status"] == gate.HOLD_DUPLICATE}
        self.assertFalse((held_ids - duplicate_ids) & routed_ids)
        self.assertEqual(len(self.result.manifest["reports"]), 100)

    def test_human_release_gate(self):
        report = next(row for row in self.result.manifest["reports"] if row["status"] == gate.STAGED)
        with self.assertRaises(PermissionError):
            gate.release_report(report, "automation")
        released = gate.release_report(report, gate.HUMAN_REVIEWER)
        self.assertEqual(released["status"], gate.RELEASED)
        self.assertEqual(released["released_by"], gate.HUMAN_REVIEWER)
        blocked = next(row for row in self.result.manifest["reports"] if row["status"] == gate.QA_HOLD_CAL)
        with self.assertRaises(ValueError):
            gate.release_report(blocked, gate.HUMAN_REVIEWER)

    def test_replay_is_byte_stable_and_adds_nothing(self):
        second = gate.run_gate(self.specimens, self.run_qc)
        self.assertEqual(gate.canonical_json(self.result.manifest), gate.canonical_json(second.manifest))
        self.assertEqual(self.result.audit_sha256, second.audit_sha256)
        self.assertEqual(self.result.manifest_sha256, second.manifest_sha256)
        self.assertEqual(len(second.manifest["routed"]), 100)

    def test_fixture_truth_hashes_match(self):
        expected = self.fixture_manifest["expected"]
        self.assertEqual(self.result.manifest_sha256, expected["manifest_sha256"])
        self.assertEqual(self.result.audit_sha256, expected["audit_sha256"])
        self.assertEqual(self.result.manifest["report_status_counts"], expected["report_status_counts"])

    def test_no_production_write_or_automatic_release(self):
        self.assertFalse(self.result.manifest["production_write_performed"])
        self.assertTrue(self.result.manifest["human_release_required"])
        self.assertFalse(any(row["released"] for row in self.result.manifest["reports"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
