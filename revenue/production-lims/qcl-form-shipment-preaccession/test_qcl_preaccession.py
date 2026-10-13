from __future__ import annotations
import copy
import hashlib
import sys
import unittest
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from qcl_preaccession import (  # noqa: E402
    FORBIDDEN_PHI_KEYS,
    IntegrityError,
    QCLPreaccessionShadow,
    load_fixture,
    verify_manifest_signature,
    verify_records,
)

class QCLPreaccessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records, cls.manifest = load_fixture()
        cls.by_id = {record["intake_id"]: record for record in cls.records}

    def test_frozen_truth_set_is_exact(self):
        self.assertEqual(200, len(self.records))
        self.assertEqual(160, self.manifest["expected_ready"])
        self.assertEqual(40, self.manifest["expected_hold"])
        expected = {
            "QUOTE_MISSING_OR_CONFLICT": 7,
            "PO_MISSING_OR_CONFLICT": 7,
            "METHOD_MISSING_OR_CONFLICT": 7,
            "LOT_MISSING_OR_CONFLICT": 7,
            "SAMPLE_QUANTITY_MISSING_OR_CONFLICT": 6,
            "STORAGE_MISSING_OR_CONFLICT": 6,
        }
        self.assertEqual(expected, self.manifest["expected_hold_codes"])
        self.assertEqual(
            Counter(expected),
            Counter(r["truth_hold"] for r in self.records if r["truth_hold"]),
        )
        verify_manifest_signature(self.manifest)
        verify_records(self.records, self.manifest)
        fixture_text = (HERE / "fixtures" / "qcl_200_intakes.json").read_text(encoding="utf-8")
        self.assertEqual(
            self.manifest["dataset_sha256"],
            hashlib.sha256(fixture_text.encode("utf-8")).hexdigest(),
        )

    def test_first_replay_routes_exactly_160_and_holds_40(self):
        shadow = QCLPreaccessionShadow({"authoritative": "unchanged"})
        report = shadow.replay(self.records, self.manifest)
        self.assertEqual((160, 40, 0), (report.ready, report.hold, report.replayed))
        self.assertEqual(
            (160, 160, 160, 160, 40, 200),
            (
                report.accessions_added,
                report.workflows_added,
                report.test_jobs_added,
                report.staged_reports_added,
                report.holds_added,
                report.events_added,
            ),
        )
        self.assertEqual(dict(sorted(self.manifest["expected_hold_codes"].items())), report.hold_counts)
        self.assertEqual(160, len(shadow.accessions))
        self.assertEqual(40, len(shadow.holds))

    def test_correct_workflow_is_preserved_exactly_once(self):
        shadow = QCLPreaccessionShadow()
        report = shadow.replay(self.records, self.manifest)
        ready = [item for item in report.outcomes if item["status"] == "READY"]
        self.assertEqual(160, len(ready))
        for item in ready:
            src = self.by_id[item["intake_id"]]
            self.assertEqual(src["workflow"], item["workflow"])
            self.assertEqual(src["workflow"], shadow.accessions[item["intake_id"]]["workflow"])
            self.assertEqual(src["workflow"], shadow.workflows[item["intake_id"]]["workflow"])
            self.assertEqual(src["workflow"], shadow.test_jobs[item["intake_id"]]["workflow"])

    def test_held_items_never_enter_testing_or_reporting(self):
        shadow = QCLPreaccessionShadow()
        report = shadow.replay(self.records, self.manifest)
        held = [item for item in report.outcomes if item["status"] == "HOLD"]
        self.assertEqual(40, len(held))
        for item in held:
            intake_id = item["intake_id"]
            self.assertEqual((0, 0, 0), (
                item["workflow_created"], item["test_job_created"], item["report_created"]
            ))
            self.assertNotIn(intake_id, shadow.accessions)
            self.assertNotIn(intake_id, shadow.workflows)
            self.assertNotIn(intake_id, shadow.test_jobs)
            self.assertNotIn(intake_id, shadow.staged_reports)

    def test_every_normalized_field_retains_source_hash_and_coordinates(self):
        shadow = QCLPreaccessionShadow()
        shadow.replay(self.records, self.manifest)
        for intake_id, accession in shadow.accessions.items():
            src = self.by_id[intake_id]
            self.assertEqual(src["normalized_sha256"], accession["normalized_sha256"])
            provenance = accession["field_provenance"]
            self.assertEqual(set(src["fields"]), set(provenance))
            for field_name, field in src["fields"].items():
                self.assertEqual(field["source"], provenance[field_name])
                self.assertTrue(provenance[field_name]["document_sha256"])
                self.assertTrue(provenance[field_name]["coordinates"])

    def test_fixture_is_synthetic_deidentified_and_phi_shaped_fields_reject(self):
        self.assertTrue(all(r["deidentified"] for r in self.records))
        self.assertTrue(all(not ({k.lower() for k in r} & FORBIDDEN_PHI_KEYS) for r in self.records))
        bad = copy.deepcopy(self.records)
        bad[0]["patient_name"] = "synthetic-but-forbidden"
        with self.assertRaises(IntegrityError):
            verify_records(bad, self.manifest)

    def test_full_second_replay_adds_zero_duplicates(self):
        authoritative = {"source": "buyer-system", "revision": 4}
        shadow = QCLPreaccessionShadow(authoritative)
        fingerprint = shadow.authoritative_fingerprint
        first = shadow.replay(self.records, self.manifest)
        first_digest = first.state_digest
        counts = (
            len(shadow.accessions), len(shadow.workflows), len(shadow.test_jobs),
            len(shadow.staged_reports), len(shadow.holds), len(shadow.events)
        )
        second = shadow.replay(self.records, self.manifest)
        self.assertEqual((0, 0, 200), (second.ready, second.hold, second.replayed))
        self.assertEqual((0, 0, 0, 0, 0, 0), (
            second.accessions_added, second.workflows_added, second.test_jobs_added,
            second.staged_reports_added, second.holds_added, second.events_added
        ))
        self.assertEqual(first_digest, second.state_digest)
        self.assertEqual(counts, (
            len(shadow.accessions), len(shadow.workflows), len(shadow.test_jobs),
            len(shadow.staged_reports), len(shadow.holds), len(shadow.events)
        ))
        self.assertEqual(fingerprint, shadow.authoritative_fingerprint)
        self.assertEqual(authoritative, shadow.authoritative_state)

    def test_manifest_and_normalized_field_tampering_are_rejected(self):
        bad_manifest = copy.deepcopy(self.manifest)
        bad_manifest["expected_ready"] = 159
        with self.assertRaises(IntegrityError):
            verify_manifest_signature(bad_manifest)
        bad_records = copy.deepcopy(self.records)
        bad_records[0]["fields"]["lot"]["source"]["coordinates"] = "tampered"
        with self.assertRaises(IntegrityError):
            verify_records(bad_records, self.manifest)

    def test_release_requires_named_human_and_auto_release_fails_closed(self):
        shadow = QCLPreaccessionShadow()
        shadow.replay(self.records, self.manifest)
        with self.assertRaises(PermissionError):
            shadow.release_report("QCL-INTAKE-0001", "")
        with self.assertRaises(PermissionError):
            shadow.automatic_release("QCL-INTAKE-0001")
        receipt = shadow.release_report("QCL-INTAKE-0001", "Named QA Reviewer")
        self.assertEqual("RELEASED_BY_NAMED_HUMAN", receipt["state"])
        self.assertEqual("Named QA Reviewer", receipt["released_by"])

if __name__ == "__main__":
    unittest.main()
