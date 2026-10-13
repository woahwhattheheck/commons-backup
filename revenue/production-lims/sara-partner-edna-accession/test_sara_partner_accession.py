import copy
import json
import tempfile
import unittest
from pathlib import Path

import sara_partner_accession as sara


class SaraPartnerAccessionTests(unittest.TestCase):
    def setUp(self):
        self.records, self.manifest = sara.load_fixture()

    def test_exact_truth_set_192_ready_48_hold(self):
        shadow = sara.SaraPartnerAccessionShadow()
        report = shadow.replay(self.records, self.manifest)
        self.assertEqual(192, report.ready)
        self.assertEqual(48, report.hold)
        self.assertEqual({code: 8 for code in sara.HOLD_CODES}, report.hold_counts)
        self.assertEqual((192, 192, 192, 48, 240), (
            report.accessions_added, report.jobs_added, report.reports_added,
            report.holds_added, report.events_added,
        ))

    def test_failed_qpcr_control_holds_entire_batches(self):
        shadow = sara.SaraPartnerAccessionShadow()
        report = shadow.replay(self.records, self.manifest)
        held = [o for o in report.outcomes if o.get("hold_code") == "QPCR_CONTROL_FAIL"]
        self.assertEqual(8, len(held))
        ids = {o["record_id"] for o in held}
        self.assertEqual({f"SARA-REC-{i:04d}" for i in range(233, 241)}, ids)
        for record_id in ids:
            self.assertNotIn(record_id, shadow.jobs)
            self.assertNotIn(record_id, shadow.staged_reports)

    def test_ready_routes_and_client_program_isolation(self):
        shadow = sara.SaraPartnerAccessionShadow()
        report = shadow.replay(self.records, self.manifest)
        record_by_id = {r["record_id"]: r for r in self.records}
        for outcome in report.outcomes:
            if outcome["status"] != "READY":
                continue
            record = record_by_id[outcome["record_id"]]
            self.assertEqual(sara.FACILITY_ID, outcome["facility_id"])
            self.assertEqual(sara.PROGRAM_CLIENT[record["program_id"]], outcome["client_id"])
            self.assertEqual(record["scope_id"], outcome["scope_id"])
            self.assertEqual(record["panel_version"], outcome["panel_version"])
            self.assertEqual(record["control_batch_id"], outcome["control_batch_id"])
            staged = shadow.staged_reports[record["record_id"]]
            self.assertEqual(record["program_id"], staged["program_id"])
            self.assertEqual(record["client_id"], staged["client_id"])

    def test_provenance_and_report_digests_reconcile(self):
        shadow = sara.SaraPartnerAccessionShadow()
        report = shadow.replay(self.records, self.manifest)
        record_by_id = {r["record_id"]: r for r in self.records}
        for outcome in report.outcomes:
            if outcome["status"] != "READY":
                continue
            record = record_by_id[outcome["record_id"]]
            self.assertEqual(record["source_sha256"], outcome["source_sha256"])
            self.assertEqual(record["custody_sha256"], outcome["custody_sha256"])
            self.assertEqual(record["expected_report_digest"], outcome["report_digest"])
            self.assertEqual(record["expected_report_digest"], shadow.staged_reports[record["record_id"]]["report_digest"])

    def test_all_holds_create_zero_job_and_report_state(self):
        shadow = sara.SaraPartnerAccessionShadow()
        report = shadow.replay(self.records, self.manifest)
        held_ids = {o["record_id"] for o in report.outcomes if o["status"] == "HOLD"}
        self.assertEqual(48, len(held_ids))
        self.assertTrue(held_ids.isdisjoint(shadow.jobs))
        self.assertTrue(held_ids.isdisjoint(shadow.staged_reports))
        for record_id in held_ids:
            self.assertEqual(0, shadow.holds[record_id]["jobs_created"])
            self.assertEqual(0, shadow.holds[record_id]["report_created"])

    def test_full_replay_is_zero_add_and_state_stable(self):
        shadow = sara.SaraPartnerAccessionShadow()
        first = shadow.replay(self.records, self.manifest)
        digest = first.state_digest
        second = shadow.replay(self.records, self.manifest)
        self.assertEqual(240, second.replayed)
        self.assertEqual((0, 0, 0, 0, 0), (
            second.accessions_added, second.jobs_added, second.reports_added,
            second.holds_added, second.events_added,
        ))
        self.assertEqual(digest, second.state_digest)

    def test_read_only_authoritative_state_is_unchanged(self):
        authoritative = {"vendor": {"records": 77}, "mode": "production-read-only"}
        before = copy.deepcopy(authoritative)
        shadow = sara.SaraPartnerAccessionShadow(authoritative)
        fingerprint = shadow.authoritative_fingerprint
        shadow.replay(self.records, self.manifest)
        self.assertEqual(before, authoritative)
        self.assertEqual(fingerprint, shadow.authoritative_fingerprint)

    def test_named_human_release_is_copy_only_and_reserved_identities_fail(self):
        shadow = sara.SaraPartnerAccessionShadow()
        shadow.replay(self.records, self.manifest)
        record_id = next(iter(shadow.staged_reports))
        before = copy.deepcopy(shadow.staged_reports[record_id])
        for bad in ("", "auto", "system", "bot", "service-account", "AI", "Jordan"):
            with self.assertRaises(PermissionError):
                shadow.release_report(record_id, bad)
        released = shadow.release_report(record_id, "Jordan Reviewer")
        self.assertEqual("RELEASED_BY_NAMED_HUMAN", released["state"])
        self.assertEqual("Jordan Reviewer", released["released_by"])
        self.assertFalse(released["sent"])
        self.assertEqual(before, shadow.staged_reports[record_id])
        with self.assertRaises(PermissionError):
            shadow.automatic_release(record_id)

    def test_manifest_fixture_and_expanded_records_fail_closed_on_tamper(self):
        module_dir = Path(sara.__file__).resolve().parent
        fixture = module_dir / "fixtures" / "sara_240_submissions.json"
        manifest = json.loads((module_dir / "fixtures" / "manifest.json").read_text())
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            bad_fixture = tmp / "fixture.json"
            bad_fixture.write_text(fixture.read_text().replace('"clean_count":192', '"clean_count":191'))
            with self.assertRaises(sara.IntegrityError):
                sara.load_fixture(bad_fixture, module_dir / "fixtures" / "manifest.json")
            bad_manifest = dict(manifest)
            bad_manifest["expected_ready"] = 191
            bad_manifest_path = tmp / "manifest.json"
            bad_manifest_path.write_text(json.dumps(bad_manifest, sort_keys=True))
            with self.assertRaises(sara.IntegrityError):
                sara.load_fixture(fixture, bad_manifest_path)

    def test_runtime_acceptance_summary(self):
        result = sara.run_acceptance()
        self.assertEqual(192, result["ready"])
        self.assertEqual(48, result["hold"])
        self.assertEqual(192, result["accessions"])
        self.assertEqual(192, result["jobs"])
        self.assertEqual(192, result["staged_reports"])
        self.assertTrue(result["replay_zero_add"])
        self.assertEqual("RELEASED_BY_NAMED_HUMAN", result["release_state"])
        self.assertFalse(result["sent"])


if __name__ == "__main__":
    unittest.main()
