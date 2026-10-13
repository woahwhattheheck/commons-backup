from __future__ import annotations

import copy
import unittest
from pathlib import Path

from agt_d7371_fame_ftir import (
    AgTD7371Lane,
    METHOD_CODE,
    METHOD_VERSION,
    UNITS,
    canonical_json,
    expected_ftir_payload,
    load_fixture,
    named_human,
    sha256_text,
    summarize,
    verify_manifest,
)

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "fixtures" / "agt_100_records.json"
MANIFEST = HERE / "fixtures" / "manifest.json"


class AgTD7371LaneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = verify_manifest(FIXTURE, MANIFEST)
        cls.records = load_fixture(FIXTURE)

    def _run(self):
        lane = AgTD7371Lane()
        results = lane.process_many(copy.deepcopy(self.records))
        return lane, results

    def test_01_manifest_and_expanded_fixture_are_hash_bound(self) -> None:
        self.assertEqual(100, len(self.records))
        self.assertEqual(
            self.manifest["expanded_fixture_sha256"],
            sha256_text(canonical_json(self.records)),
        )
        self.assertTrue(self.manifest["synthetic_only"])
        self.assertFalse(self.manifest["automatic_release"])

    def test_02_exact_80_ready_20_hold_truth(self) -> None:
        lane, results = self._run()
        summary = summarize(results)
        self.assertEqual({"READY": 80, "HOLD": 20}, summary["states"])
        self.assertEqual(
            {
                "DUPLICATE_SAMPLE_ID": 5,
                "INCOMPLETE_CUSTODY": 10,
                "OOS_FAME": 5,
            },
            summary["hold_codes"],
        )
        self.assertEqual(80, len(lane.state.accessions))
        self.assertEqual(20, len(lane.state.holds))

    def test_03_ready_accessions_have_exact_method_units_rounding_qc_and_source_binding(self) -> None:
        lane, _ = self._run()
        records_by_submission = {item["submission_id"]: item for item in self.records}
        self.assertEqual(80, len({item["sample_id"] for item in lane.state.accessions}))
        for accession in lane.state.accessions:
            submission = lane.state.accession_by_sample[accession["sample_id"]]
            source = records_by_submission[submission]
            self.assertEqual(METHOD_CODE, accession["method_code"])
            self.assertEqual(METHOD_VERSION, accession["method_version"])
            self.assertEqual(UNITS, accession["units"])
            self.assertEqual(1, accession["rounding_decimals"])
            self.assertEqual(source["reported_fame_vv"], accession["reported_fame_vv"])
            self.assertEqual(source["ftir_sha256"], accession["ftir_sha256"])
            self.assertEqual(sha256_text(canonical_json(source)), accession["source_sha256"])

    def test_04_all_20_truth_exceptions_add_zero_accession_and_zero_report_state(self) -> None:
        lane, results = self._run()
        held_submissions = {r["submission_id"] for r in results if r["state"] == "HOLD"}
        accession_submissions = set(lane.state.accession_by_sample.values())
        self.assertEqual(20, len(held_submissions))
        self.assertTrue(held_submissions.isdisjoint(accession_submissions))
        self.assertEqual(80, len(lane.state.accessions))
        self.assertEqual(80, len(lane.state.staged_reports))
        self.assertEqual(
            {item["sample_id"] for item in lane.state.accessions},
            set(lane.state.staged_reports),
        )

    def test_05_ftir_payload_hash_and_content_tamper_fail_closed(self) -> None:
        lane = AgTD7371Lane()
        probe = copy.deepcopy(self.records[0])
        probe["submission_id"] = "PROBE-FTIR-TAMPER"
        probe["sample_id"] = "PROBE-FTIR-TAMPER"
        probe["ftir_filename"] = f'{probe["sample_id"]}.spc.synthetic.txt'
        probe["ftir_payload"] = expected_ftir_payload(
            probe["sample_id"], probe["raw_fame_vv"], probe["qc_recovery_pct"]
        ) + "|tamper"
        probe["ftir_sha256"] = sha256_text(probe["ftir_payload"])
        result = lane.process(probe)
        self.assertEqual(("HOLD", "FTIR_SOURCE_MISMATCH"), (result["state"], result["code"]))
        self.assertEqual(0, len(lane.state.accessions))

    def test_06_method_version_and_result_format_mismatch_fail_closed(self) -> None:
        for field, value, expected in [
            ("method_version", "STALE", "METHOD_BINDING_MISMATCH"),
            ("units", "ppm", "RESULT_FORMAT_MISMATCH"),
            ("rounding_decimals", 2, "RESULT_FORMAT_MISMATCH"),
        ]:
            lane = AgTD7371Lane()
            probe = copy.deepcopy(self.records[1])
            probe["submission_id"] = f"PROBE-{field}"
            probe["sample_id"] = f"PROBE-{field}"
            probe["ftir_filename"] = f'{probe["sample_id"]}.spc.synthetic.txt'
            probe["ftir_payload"] = expected_ftir_payload(
                probe["sample_id"], probe["raw_fame_vv"], probe["qc_recovery_pct"]
            )
            probe["ftir_sha256"] = sha256_text(probe["ftir_payload"])
            probe[field] = value
            result = lane.process(probe)
            self.assertEqual(("HOLD", expected), (result["state"], result["code"]))

    def test_07_exact_replay_is_100_idempotent_and_zero_add(self) -> None:
        lane, first = self._run()
        self.assertEqual({"READY": 80, "HOLD": 20}, summarize(first)["states"])
        before = lane.state.digest()
        counts_before = (
            len(lane.state.accessions), len(lane.state.holds),
            len(lane.state.events), len(lane.state.staged_reports),
        )
        replay = lane.process_many(copy.deepcopy(self.records))
        self.assertEqual({"IDEMPOTENT": 100}, summarize(replay)["states"])
        self.assertEqual(before, lane.state.digest())
        self.assertEqual(
            counts_before,
            (
                len(lane.state.accessions), len(lane.state.holds),
                len(lane.state.events), len(lane.state.staged_reports),
            ),
        )

    def test_08_changed_payload_same_submission_fails_closed_without_mutation(self) -> None:
        lane = AgTD7371Lane()
        first = copy.deepcopy(self.records[0])
        self.assertEqual("READY", lane.process(first)["state"])
        before = lane.state.digest()
        changed = copy.deepcopy(first)
        changed["raw_fame_vv"] += 1.0
        result = lane.process(changed)
        self.assertEqual(("HOLD", "REPLAY_PAYLOAD_CONFLICT"), (result["state"], result["code"]))
        self.assertEqual(before, lane.state.digest())

    def test_09_golden_accession_report_audit_digests_match(self) -> None:
        lane, _ = self._run()
        self.assertEqual(self.manifest["expected_accession_sha256"], lane.state.accession_digest())
        self.assertEqual(self.manifest["expected_report_sha256"], lane.state.report_digest())
        self.assertEqual(self.manifest["expected_audit_sha256"], lane.state.digest())

    def test_10_named_human_release_is_copy_only_unsent_and_automation_labels_rejected(self) -> None:
        lane, _ = self._run()
        sample_id = lane.state.accessions[0]["sample_id"]
        before = copy.deepcopy(lane.state.staged_reports[sample_id])
        released = lane.release_report(sample_id, "Jordan Rivera")
        self.assertEqual("RELEASED_BY_NAMED_HUMAN", released["state"])
        self.assertFalse(released["sent"])
        self.assertEqual(before, lane.state.staged_reports[sample_id])
        for reviewer in [
            "AI Reviewer", "System Operator", "Bot Reviewer", "service account",
            "workflow agent", "Jordan Automation", "12 34", "Madonna",
        ]:
            with self.subTest(reviewer=reviewer):
                self.assertFalse(named_human(reviewer))
                with self.assertRaises(PermissionError):
                    lane.release_report(sample_id, reviewer)

    def test_11_automatic_release_is_disabled(self) -> None:
        lane, _ = self._run()
        with self.assertRaises(PermissionError):
            lane.automatic_release(lane.state.accessions[0]["sample_id"])

    def test_12_processing_does_not_mutate_fixture_records(self) -> None:
        records = copy.deepcopy(self.records)
        frozen = canonical_json(records)
        lane = AgTD7371Lane()
        lane.process_many(records)
        self.assertEqual(frozen, canonical_json(records))

    def test_13_qc_target_conversion_fails_before_state_mutation(self) -> None:
        lane = AgTD7371Lane()
        probe = copy.deepcopy(self.records[0])
        probe["qc_target_vv"] = "not-a-number"
        before = lane.state.digest()
        with self.assertRaisesRegex(ValueError, "qc_target_vv must be numeric"):
            lane.process(probe)
        self.assertEqual(before, lane.state.digest())
        self.assertEqual({}, lane.state.processed_submissions)
        self.assertEqual([], lane.state.holds)
        self.assertEqual([], lane.state.events)

        coercible = copy.deepcopy(self.records[0])
        coercible["qc_target_vv"] = "3.0"
        self.assertEqual("READY", lane.process(coercible)["state"])

        wrong_numeric_lane = AgTD7371Lane()
        wrong_numeric = copy.deepcopy(self.records[0])
        wrong_numeric["qc_target_vv"] = 4.0
        result = wrong_numeric_lane.process(wrong_numeric)
        self.assertEqual(("HOLD", "QC_MISMATCH"), (result["state"], result["code"]))
        self.assertIn(wrong_numeric["submission_id"], wrong_numeric_lane.state.processed_submissions)

    def test_14_changed_replay_malformed_qc_preserves_conflict_precedence(self) -> None:
        lane = AgTD7371Lane()
        first = copy.deepcopy(self.records[0])
        self.assertEqual("READY", lane.process(first)["state"])
        before = lane.state.digest()

        changed = copy.deepcopy(first)
        changed["qc_target_vv"] = "not-a-number"
        result = lane.process(changed)

        self.assertEqual(
            ("HOLD", "REPLAY_PAYLOAD_CONFLICT"),
            (result["state"], result["code"]),
        )
        self.assertEqual(before, lane.state.digest())


if __name__ == "__main__":
    unittest.main(verbosity=2)
