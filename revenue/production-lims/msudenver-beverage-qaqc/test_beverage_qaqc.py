from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import beverage_qaqc as q


HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "fixtures" / "msudenver_100_requests.json"
MANIFEST = HERE / "fixtures" / "manifest.json"


class BeverageQAQCTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows, cls.manifest = q.load_fixture(FIXTURE, MANIFEST)

    def test_01_manifest_binds_exact_100_row_synthetic_fixture(self) -> None:
        self.assertEqual(len(self.rows), 100)
        self.assertTrue(all(isinstance(row, dict) for row in self.rows))
        self.assertEqual(self.manifest["demand_id"], q.DEMAND_ID)
        self.assertEqual(
            hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
            self.manifest["fixture_sha256"],
        )
        self.assertEqual(q.sha256_hex(self.rows), self.manifest["expanded_requests_sha256"])

    def test_02_full_acceptance_counts_are_exact(self) -> None:
        summary = q.run_fixture(FIXTURE, MANIFEST)
        self.assertEqual(summary["READY"], 80)
        self.assertEqual(summary["MISSING_SAMPLE_TEST_IDENTITY"], 8)
        self.assertEqual(summary["DUPLICATE_CLIENT_ID"], 5)
        self.assertEqual(summary["INCOMPATIBLE_PACKAGE_TEST_SELECTION"], 4)
        self.assertEqual(summary["QC_CONTROL_FAIL"], 3)
        self.assertEqual(summary["accessions"], 80)
        self.assertEqual(summary["jobs"], 180)
        self.assertEqual(summary["reports"], 80)
        self.assertEqual(summary["holds"], 20)
        self.assertEqual(summary["events"], 100)

    def test_03_ready_jobs_equal_catalog_and_golden_metadata(self) -> None:
        adapter = q.BeverageQAQC()
        results = adapter.ingest_many(self.rows)
        ready = [row for row, result in zip(self.rows, results) if result["status"] == "READY"]
        self.assertEqual(len(ready), 80)
        for row in ready:
            accession = adapter.state["accessions"][row["request_id"]]
            report = adapter.state["reports"][row["request_id"]]
            expected_tests = q.CATALOG[row["package"]]["tests"]
            self.assertEqual(len(report["job_ids"]), len(expected_tests))
            by_code = {r["test_code"]: r for r in row["golden_results"]}
            for job_id, code in zip(report["job_ids"], expected_tests):
                job = adapter.state["jobs"][job_id]
                golden = by_code[code]
                self.assertEqual(job["test_code"], code)
                self.assertEqual(job["value"], golden["value"])
                self.assertEqual(job["unit"], golden["unit"])
                self.assertEqual(job["rounding"], golden["rounding"])
                self.assertEqual(job["method_version"], golden["method_version"])
                self.assertEqual(job["source_payload_sha256"], accession["payload_sha256"])

    def test_04_qc_control_failures_never_accession_or_report(self) -> None:
        adapter = q.BeverageQAQC()
        results = adapter.ingest_many(self.rows)
        failed = [r for r in results if r.get("reason") == "QC_CONTROL_FAIL"]
        self.assertEqual(len(failed), 3)
        for result in failed:
            rid = result["request_id"]
            self.assertNotIn(rid, adapter.state["accessions"])
            self.assertNotIn(rid, adapter.state["reports"])
            self.assertEqual(adapter.state["holds"][rid]["reason"], "QC_CONTROL_FAIL")

    def test_05_every_hold_has_zero_jobs_and_zero_report(self) -> None:
        adapter = q.BeverageQAQC()
        results = adapter.ingest_many(self.rows)
        held_ids = {r["request_id"] for r in results if r["status"] == "HOLD"}
        self.assertEqual(len(held_ids), 20)
        for rid in held_ids:
            self.assertNotIn(rid, adapter.state["accessions"])
            self.assertNotIn(rid, adapter.state["reports"])
            self.assertFalse(any(job["accession_id"] == f"ACC-{rid}" for job in adapter.state["jobs"].values()))

    def test_06_full_same_ledger_replay_is_zero_add(self) -> None:
        adapter = q.BeverageQAQC()
        adapter.ingest_many(self.rows)
        before = adapter.snapshot()
        replay = adapter.ingest_many(self.rows)
        self.assertEqual(adapter.snapshot(), before)
        self.assertEqual(sum(r["status"] == "IDEMPOTENT" for r in replay), 100)

    def test_07_changed_same_request_id_fails_before_mutation(self) -> None:
        adapter = q.BeverageQAQC()
        row = deepcopy(self.rows[0])
        adapter.ingest(row)
        before = adapter.snapshot()
        changed = deepcopy(row)
        changed["sample_id"] = "DIFFERENT-SAMPLE"
        with self.assertRaises(q.ReplayPayloadMismatch):
            adapter.ingest(changed)
        self.assertEqual(adapter.snapshot(), before)

    def test_08_release_requires_named_human(self) -> None:
        adapter = q.BeverageQAQC()
        adapter.ingest(self.rows[0])
        for reviewer in ("", "Jordan", None, 7):
            before = adapter.snapshot()
            with self.assertRaises(q.ReleaseError):
                adapter.release_report_copy("MSU-001", reviewer)  # type: ignore[arg-type]
            self.assertEqual(adapter.snapshot(), before)

    def test_09_release_rejects_automation_service_identities(self) -> None:
        adapter = q.BeverageQAQC()
        adapter.ingest(self.rows[0])
        bad = (
            "System Reviewer",
            "AI Reviewer",
            "Bot Operator",
            "Automation Service",
            "agent007 reviewer",
            "service2 account",
        )
        for reviewer in bad:
            before = adapter.snapshot()
            with self.assertRaises(q.ReleaseError, msg=reviewer):
                adapter.release_report_copy("MSU-001", reviewer)
            self.assertEqual(adapter.snapshot(), before)

    def test_10_release_is_copy_only_unsent_and_stored_report_stays_staged(self) -> None:
        adapter = q.BeverageQAQC()
        adapter.ingest(self.rows[0])
        before = adapter.snapshot()
        released = adapter.release_report_copy("MSU-001", "Jordan Rivera")
        self.assertEqual(released["status"], "RELEASED_BY_NAMED_HUMAN_COPY")
        self.assertFalse(released["sent"])
        self.assertEqual(released["reviewer"], "Jordan Rivera")
        self.assertEqual(adapter.snapshot(), before)
        self.assertEqual(adapter.state["reports"]["MSU-001"]["status"], "STAGED_HUMAN_REVIEW")

    def test_11_tampered_fixture_is_rejected_by_sha(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            fixture = tmp / FIXTURE.name
            manifest = tmp / MANIFEST.name
            fixture.write_bytes(FIXTURE.read_bytes() + b" ")
            manifest.write_bytes(MANIFEST.read_bytes())
            with self.assertRaisesRegex(q.ManifestError, "fixture SHA-256 mismatch"):
                q.load_fixture(fixture, manifest)

    def test_12_tampered_manifest_is_rejected_by_canonical_digest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            fixture = tmp / FIXTURE.name
            manifest = tmp / MANIFEST.name
            fixture.write_bytes(FIXTURE.read_bytes())
            doc = json.loads(MANIFEST.read_text(encoding="utf-8"))
            doc["expected"]["jobs"] = 179
            manifest.write_text(json.dumps(doc), encoding="utf-8")
            with self.assertRaisesRegex(q.ManifestError, "canonical digest mismatch"):
                q.load_fixture(fixture, manifest)

    def test_13_incompatible_selection_fails_before_accession(self) -> None:
        adapter = q.BeverageQAQC()
        bad = deepcopy(self.rows[0])
        bad["request_id"] = "MSU-INCOMPATIBLE"
        bad["client_request_id"] = "CLIENT-INCOMPATIBLE"
        bad["matrix"] = "WINE"
        result = adapter.ingest(bad)
        self.assertEqual(result["reason"], "INCOMPATIBLE_PACKAGE_TEST_SELECTION")
        self.assertEqual(len(adapter.state["accessions"]), 0)
        self.assertEqual(len(adapter.state["jobs"]), 0)
        self.assertEqual(len(adapter.state["reports"]), 0)

    def test_14_coherent_generator_metadata_drift_fails_frozen_expansion_digest(self) -> None:
        original = deepcopy(q.TEST_META)
        try:
            # This is the predecessor-killing vector: _golden_result() and
            # _validate_golden_results() both read TEST_META, so without an
            # independently frozen expanded-row digest a coherent drift could
            # pass self-consistency checks.
            q.TEST_META["ABV"]["method_version"] = "BA-ABV-v99"
            with self.assertRaisesRegex(q.ManifestError, "expanded request SHA-256 mismatch"):
                q.load_fixture(FIXTURE, MANIFEST)
        finally:
            q.TEST_META.clear()
            q.TEST_META.update(original)


if __name__ == "__main__":
    unittest.main()
