from __future__ import annotations

import copy
import hashlib
import json
import sys
import unittest
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from delaware_newlab_lineage import (  # noqa: E402
    DelawareNewLabShadow,
    IntegrityError,
    load_fixture,
    verify_manifest_signature,
    verify_records,
)


class DelawareNewLabLineageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records, cls.manifest = load_fixture()
        cls.by_id = {record["request_id"]: record for record in cls.records}

    def test_frozen_manifest_and_truth_set_are_exact(self):
        self.assertEqual(200, len(self.records))
        self.assertEqual(150, self.manifest["expected_ready"])
        self.assertEqual(50, self.manifest["expected_hold"])
        self.assertEqual(
            {
                "MISSING_MATRIX_SDS_CUSTODY": 15,
                "DUPLICATE_CONTAINER": 10,
                "METHOD_MATRIX_MISMATCH": 10,
                "CALIBRATION_QC_FAIL": 10,
                "LEGACY_NEW_FACILITY_ID_COLLISION": 5,
            },
            self.manifest["expected_hold_codes"],
        )
        self.assertEqual(
            Counter(self.manifest["expected_hold_codes"]),
            Counter(
                record["truth_hold"]
                for record in self.records
                if record["truth_hold"] is not None
            ),
        )
        verify_manifest_signature(self.manifest)
        verify_records(self.records, self.manifest)
        fixture_text = (HERE / "fixtures" / "delaware_200_requests.json").read_text(
            encoding="utf-8"
        )
        self.assertEqual(
            self.manifest["dataset_sha256"],
            hashlib.sha256(fixture_text.encode("utf-8")).hexdigest(),
        )

    def test_first_replay_is_exact_150_ready_50_hold(self):
        shadow = DelawareNewLabShadow({"authoritative": "unchanged"})
        report = shadow.replay(self.records, self.manifest)
        self.assertEqual(150, report.ready)
        self.assertEqual(50, report.hold)
        self.assertEqual(0, report.replayed)
        self.assertEqual(
            dict(sorted(self.manifest["expected_hold_codes"].items())),
            report.hold_counts,
        )
        self.assertEqual(150, report.accessions_added)
        self.assertEqual(150, report.jobs_added)
        self.assertEqual(150, report.reports_added)
        self.assertEqual(50, report.holds_added)
        self.assertEqual(200, report.events_added)
        self.assertEqual(150, len(shadow.accessions))
        self.assertEqual(150, len(shadow.jobs))
        self.assertEqual(150, len(shadow.reports))
        self.assertEqual(50, len(shadow.holds))
        self.assertEqual(200, len(shadow.events))

    def test_held_requests_schedule_nothing_and_ready_reports_stage_only(self):
        shadow = DelawareNewLabShadow()
        report = shadow.replay(self.records, self.manifest)
        held = [item for item in report.outcomes if item["status"] == "HOLD"]
        ready = [item for item in report.outcomes if item["status"] == "READY"]
        self.assertEqual(50, len(held))
        self.assertEqual(150, len(ready))
        self.assertTrue(all(item["scheduled_jobs"] == 0 for item in held))
        self.assertTrue(all(item["report_state"] is None for item in held))
        self.assertTrue(
            all(item["report_state"] == "STAGED_HUMAN_REVIEW" for item in ready)
        )
        self.assertTrue(
            all(report["state"] == "STAGED_HUMAN_REVIEW" for report in shadow.reports.values())
        )

    def test_ready_lineage_hashes_values_units_qualifiers_survive_exactly(self):
        shadow = DelawareNewLabShadow()
        report = shadow.replay(self.records, self.manifest)
        for outcome in report.outcomes:
            if outcome["status"] != "READY":
                continue
            source = self.by_id[outcome["request_id"]]
            accession = shadow.accessions[outcome["request_id"]]
            job = shadow.jobs[outcome["request_id"]]
            staged = shadow.reports[outcome["request_id"]]
            self.assertEqual(source["source_sha256"], outcome["source_sha256"])
            self.assertEqual(source["source_sha256"], accession["source_sha256"])
            self.assertEqual(source["method_sha256"], outcome["method_sha256"])
            self.assertEqual(source["method_sha256"], job["method_sha256"])
            self.assertEqual(
                source["value_unit_qualifier_sha256"],
                outcome["value_unit_qualifier_sha256"],
            )
            self.assertEqual(
                source["value_unit_qualifier_sha256"],
                staged["value_unit_qualifier_sha256"],
            )
            self.assertEqual(source["value"], staged["value"])
            self.assertEqual(source["unit"], staged["unit"])
            self.assertEqual(source["qualifier"], staged["qualifier"])

    def test_full_second_replay_adds_zero_effects(self):
        authoritative = {"source": "buyer-system", "revision": 11}
        shadow = DelawareNewLabShadow(authoritative)
        authoritative_fingerprint = shadow.authoritative_fingerprint
        first = shadow.replay(self.records, self.manifest)
        state_after_first = first.state_digest
        counts_after_first = (
            len(shadow.accessions),
            len(shadow.jobs),
            len(shadow.reports),
            len(shadow.holds),
            len(shadow.events),
        )
        second = shadow.replay(self.records, self.manifest)
        self.assertEqual(0, second.ready)
        self.assertEqual(0, second.hold)
        self.assertEqual(200, second.replayed)
        self.assertEqual(0, second.accessions_added)
        self.assertEqual(0, second.jobs_added)
        self.assertEqual(0, second.reports_added)
        self.assertEqual(0, second.holds_added)
        self.assertEqual(0, second.events_added)
        self.assertEqual(state_after_first, second.state_digest)
        self.assertEqual(
            counts_after_first,
            (
                len(shadow.accessions),
                len(shadow.jobs),
                len(shadow.reports),
                len(shadow.holds),
                len(shadow.events),
            ),
        )
        self.assertEqual(authoritative_fingerprint, shadow.authoritative_fingerprint)
        self.assertEqual(authoritative, shadow.authoritative_state)

    def test_duplicate_containers_hold_without_cross_request_scheduling(self):
        shadow = DelawareNewLabShadow()
        shadow.replay(self.records, self.manifest)
        duplicates = [
            record for record in self.records
            if record["truth_hold"] == "DUPLICATE_CONTAINER"
        ]
        self.assertEqual(10, len(duplicates))
        for record in duplicates:
            request_id = record["request_id"]
            self.assertEqual(
                "DUPLICATE_CONTAINER", shadow.holds[request_id]["hold_code"]
            )
            self.assertNotIn(request_id, shadow.accessions)
            self.assertNotIn(request_id, shadow.jobs)
            self.assertNotIn(request_id, shadow.reports)

    def test_manifest_and_record_tampering_are_rejected(self):
        bad_manifest = copy.deepcopy(self.manifest)
        bad_manifest["expected_ready"] = 149
        with self.assertRaises(IntegrityError):
            verify_manifest_signature(bad_manifest)

        bad_records = copy.deepcopy(self.records)
        bad_records[0]["value"] += 1
        with self.assertRaises(IntegrityError):
            verify_records(bad_records, self.manifest)

    def test_release_requires_named_human_and_automatic_release_is_impossible(self):
        shadow = DelawareNewLabShadow()
        shadow.replay(self.records, self.manifest)
        request_id = "DNREC-REQ-0001"
        staged = copy.deepcopy(shadow.reports[request_id])
        with self.assertRaises(PermissionError):
            shadow.release_report(request_id, "")
        for actor in (
            "auto",
            " system ",
            "BOT",
            "a-u-t-o",
            "automation",
            "agent",
            "autonomous",
        ):
            with self.subTest(actor=actor):
                with self.assertRaises(PermissionError):
                    shadow.release_report(request_id, actor)
                self.assertEqual(staged, shadow.reports[request_id])
        with self.assertRaises(PermissionError):
            shadow.release_report(request_id, None)  # type: ignore[arg-type]
        self.assertEqual(staged, shadow.reports[request_id])
        with self.assertRaises(PermissionError):
            shadow.automatic_release(request_id)
        self.assertEqual(staged, shadow.reports[request_id])
        receipt = shadow.release_report(request_id, "Named QA Reviewer")
        self.assertEqual("RELEASED_BY_NAMED_HUMAN", receipt["state"])
        self.assertEqual("Named QA Reviewer", receipt["released_by"])
        with self.assertRaises(PermissionError):
            shadow.release_report(request_id, "Second Reviewer")
        self.assertEqual("Named QA Reviewer", shadow.reports[request_id]["released_by"])


if __name__ == "__main__":
    unittest.main()