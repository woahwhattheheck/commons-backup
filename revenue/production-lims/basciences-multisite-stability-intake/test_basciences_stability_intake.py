import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import basciences_stability_intake as ba

class BASciencesStabilityIntakeTests(unittest.TestCase):
    def setUp(self):
        self.records, self.manifest = ba.load_fixture()

    def test_exact_180_ready_40_hold_truth(self):
        shadow = ba.BASciencesStabilityIntakeShadow()
        result = shadow.replay(self.records, self.manifest)
        self.assertEqual((180, 40), (result.ready, result.hold))
        self.assertEqual({
            "EXPIRED_QUOTE": 7,
            "QUOTE_PO_CONFLICT": 7,
            "MISSING_CONTROLLED_OR_STORAGE_DATA": 7,
            "ABSENT_SPECIFICATION": 7,
            "AMBIGUOUS_RESULT_MAPPING": 6,
            "INCORRECT_STABILITY_TOTALS": 6,
        }, result.hold_counts)
        self.assertEqual((180, 180, 180, 40, 220), (
            result.accessions_added, result.jobs_added, result.reports_added,
            result.holds_added, result.events_added,
        ))

    def test_all_40_holds_stop_before_testing_and_reporting(self):
        shadow = ba.BASciencesStabilityIntakeShadow()
        shadow.replay(self.records, self.manifest)
        self.assertEqual(40, len(shadow.holds))
        for record_id, hold in shadow.holds.items():
            self.assertNotIn(record_id, shadow.accessions)
            self.assertNotIn(record_id, shadow.jobs)
            self.assertNotIn(record_id, shadow.results)
            self.assertNotIn(record_id, shadow.reports)
            self.assertNotIn(record_id, shadow.pull_schedules)
            self.assertEqual((0, 0, 0), (hold["testing_created"], hold["report_created"], hold["pulls_created"]))

    def test_valid_site_and_method_routes_are_exact(self):
        shadow = ba.BASciencesStabilityIntakeShadow()
        shadow.replay(self.records, self.manifest)
        by_id = {record["record_id"]: record for record in self.records}
        for record_id, accession in shadow.accessions.items():
            record = by_id[record_id]
            route = ba.ROUTES[record["form_type"]]
            self.assertEqual(route["site_id"], accession["site_id"])
            self.assertEqual(route["site_id"], shadow.jobs[record_id]["site_id"])
            self.assertEqual(route["method_id"], shadow.jobs[record_id]["method_id"])

    def test_result_and_coa_cardinality_is_exact(self):
        shadow = ba.BASciencesStabilityIntakeShadow()
        shadow.replay(self.records, self.manifest)
        by_id = {record["record_id"]: record for record in self.records}
        self.assertEqual(495, sum(len(rows) for rows in shadow.results.values()))
        for record_id, rows in shadow.results.items():
            record = by_id[record_id]
            expected = ba.ROUTES[record["form_type"]]["result_count"]
            self.assertEqual(expected, len(rows))
            self.assertEqual([row["result_id"] for row in rows], shadow.reports[record_id]["result_ids"])

    def test_stability_pull_schedule_is_exact_and_signed_to_source(self):
        shadow = ba.BASciencesStabilityIntakeShadow()
        shadow.replay(self.records, self.manifest)
        self.assertEqual(45, len(shadow.pull_schedules))
        self.assertEqual(180, sum(len(rows) for rows in shadow.pull_schedules.values()))
        by_id = {record["record_id"]: record for record in self.records}
        for record_id, pulls in shadow.pull_schedules.items():
            record = by_id[record_id]
            self.assertEqual("STABILITY", record["form_type"])
            self.assertEqual(list(ba.PULL_OFFSETS_DAYS), [item["offset_days"] for item in pulls])
            self.assertEqual(record["expected_stability_total"], sum(item["units"] for item in pulls))
            self.assertTrue(all(item["source_sha256"] == record["document_sha256"] for item in pulls))

    def test_every_normalized_field_retains_document_provenance(self):
        shadow = ba.BASciencesStabilityIntakeShadow()
        shadow.replay(self.records, self.manifest)
        by_id = {record["record_id"]: record for record in self.records}
        for record_id, accession in shadow.accessions.items():
            record = by_id[record_id]
            for field, provenance in accession["normalized"].items():
                self.assertEqual(record[field], provenance["value"])
                self.assertEqual(record["document_sha256"], provenance["source_sha256"])
                self.assertIn(f"field:{field}", provenance["source_coordinate"])

    def test_replay_is_zero_add_and_changed_payload_same_id_fails_before_mutation(self):
        shadow = ba.BASciencesStabilityIntakeShadow()
        first = shadow.replay(self.records, self.manifest)
        second = shadow.replay(self.records, self.manifest)
        self.assertEqual(220, second.replayed)
        self.assertEqual((0, 0, 0, 0, 0, 0, 0), (
            second.accessions_added, second.jobs_added, second.results_added,
            second.reports_added, second.pulls_added, second.holds_added, second.events_added,
        ))
        self.assertEqual(first.state_digest, second.state_digest)
        changed = copy.deepcopy(self.records)
        changed[0]["po_id"] = "PO-SYN-CHANGED"
        before = copy.deepcopy(shadow.__dict__)
        with self.assertRaisesRegex(ba.IntegrityError, "REPLAY_PAYLOAD_MISMATCH"):
            shadow.replay(changed, self.manifest)
        self.assertEqual(before, shadow.__dict__)

    def test_read_only_authoritative_state_never_changes(self):
        authoritative = {"production": {"records": 91}, "mode": "read-only"}
        before = copy.deepcopy(authoritative)
        shadow = ba.BASciencesStabilityIntakeShadow(authoritative)
        fingerprint = shadow.authoritative_fingerprint
        shadow.replay(self.records, self.manifest)
        self.assertEqual(before, authoritative)
        self.assertEqual(fingerprint, shadow.authoritative_fingerprint)

    def test_named_human_release_is_copy_only_and_reserved_fragments_fail(self):
        shadow = ba.BASciencesStabilityIntakeShadow()
        shadow.replay(self.records, self.manifest)
        record_id = next(iter(shadow.reports))
        before = copy.deepcopy(shadow.reports[record_id])
        for bad in ("", "Jordan", "12 34", "System Reviewer", "Serv ice Account", "Work flow Reviewer", "A I Reviewer"):
            with self.subTest(bad=bad):
                with self.assertRaises(PermissionError):
                    shadow.release_report(record_id, bad)
        released = shadow.release_report(record_id, "Jordan Reviewer")
        self.assertEqual("RELEASED_BY_NAMED_HUMAN", released["state"])
        self.assertEqual("Jordan Reviewer", released["released_by"])
        self.assertFalse(released["sent"])
        self.assertEqual(before, shadow.reports[record_id])
        with self.assertRaises(PermissionError):
            shadow.automatic_release(record_id)

    def test_fixture_manifest_and_document_tampering_fail_closed(self):
        base = Path(ba.__file__).resolve().parent
        fixture = base / "fixtures/basciences_220_intakes.json"
        manifest = base / "fixtures/manifest.json"
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            bad_fixture = td / "fixture.json"
            bad_fixture.write_text(fixture.read_text().replace('"ready_count":180', '"ready_count":179'), encoding="utf-8")
            with self.assertRaises(ba.IntegrityError):
                ba.load_fixture(bad_fixture, manifest)
            bad_manifest = json.loads(manifest.read_text())
            bad_manifest["expected_ready"] = 179
            bad_manifest_path = td / "manifest.json"
            bad_manifest_path.write_text(json.dumps(bad_manifest, sort_keys=True), encoding="utf-8")
            with self.assertRaises(ba.IntegrityError):
                ba.load_fixture(fixture, bad_manifest_path)
        records = copy.deepcopy(self.records)
        records[0]["document_signature"] = "0" * 64
        with self.assertRaises(ba.IntegrityError):
            ba.verify_records(records, self.manifest)

    def test_sensitive_shaped_fields_fail_closed(self):
        records = copy.deepcopy(self.records)
        records[0]["patient_name"] = "SYNTHETIC"
        with self.assertRaises(ba.IntegrityError):
            ba.verify_records(records, self.manifest)

    def test_run_acceptance_summary(self):
        result = ba.run_acceptance()
        self.assertEqual((180, 40, 180, 180, 495, 180, 45, 180), (
            result["ready"], result["hold"], result["accessions"], result["jobs"],
            result["results"], result["reports"], result["stability_schedules"], result["pull_events"],
        ))
        self.assertTrue(result["replay_zero_add"])
        self.assertEqual("RELEASED_BY_NAMED_HUMAN", result["release_state"])
        self.assertFalse(result["sent"])

    def test_cli_passes_with_metadata_only_summary(self):
        result = subprocess.run(
            [sys.executable, "basciences_stability_intake.py"],
            cwd=Path(ba.__file__).resolve().parent,
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        data = json.loads(result.stdout)
        self.assertTrue(data["ok"])
        self.assertEqual((180, 40), (data["ready"], data["hold"]))
        self.assertEqual(0, int(data["sent"]))

if __name__ == "__main__":
    unittest.main()
