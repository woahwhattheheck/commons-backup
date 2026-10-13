from __future__ import annotations

from copy import deepcopy
import hashlib
import unittest

try:
    from .acceptance import (
        EXPECTED_COUNTS,
        EXPECTED_QUARANTINES,
        check_acceptance,
        generate_acceptance_fixture,
    )
    from .rail import RailError, reconcile, verify_receipt
except ImportError:
    from acceptance import (
        EXPECTED_COUNTS,
        EXPECTED_QUARANTINES,
        check_acceptance,
        generate_acceptance_fixture,
    )
    from rail import RailError, reconcile, verify_receipt


def sha(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def batch(**overrides):
    row = {
        "event_id": "EV-BATCH-A",
        "kind": "tracer_batch",
        "batch_id": "SYNTH-BATCH-A",
        "protocol_id": "SYNTH-PROTOCOL-A",
        "synthesis_run_id": "SYNTH-SYNTHESIS-A",
        "batch_revision": 1,
        "supersedes_batch_id": "NONE",
        "release_evidence_sha256": sha("release-a"),
    }
    return {**row, **overrides}


def dose(**overrides):
    row = {
        "event_id": "EV-DOSE-A",
        "kind": "dose_receipt",
        "dose_receipt_id": "SYNTH-DOSE-A",
        "synthetic_subject_id": "SYNTH-SUBJECT-A",
        "batch_id": "SYNTH-BATCH-A",
        "protocol_id": "SYNTH-PROTOCOL-A",
        "administration_record_sha256": sha("admin-a"),
    }
    return {**row, **overrides}


def acquisition(**overrides):
    row = {
        "event_id": "EV-ACQ-A",
        "kind": "acquisition",
        "acquisition_id": "SYNTH-ACQ-A",
        "synthetic_subject_id": "SYNTH-SUBJECT-A",
        "dose_receipt_id": "SYNTH-DOSE-A",
        "protocol_id": "SYNTH-PROTOCOL-A",
        "scanner_id": "SYNTH-SCANNER-A",
        "acquisition_evidence_sha256": sha("acq-a"),
        "acquisition_label": "PLANNED",
    }
    return {**row, **overrides}


def qc(**overrides):
    row = {
        "event_id": "EV-QC-A",
        "kind": "scan_qc",
        "qc_id": "SYNTH-QC-A",
        "synthetic_subject_id": "SYNTH-SUBJECT-A",
        "acquisition_id": "SYNTH-ACQ-A",
        "qc_evidence_sha256": sha("qc-a"),
    }
    return {**row, **overrides}


def map_version(**overrides):
    row = {
        "event_id": "EV-MAP-A",
        "kind": "map_version",
        "map_id": "SYNTH-MAP-A",
        "synthetic_subject_id": "SYNTH-SUBJECT-A",
        "acquisition_id": "SYNTH-ACQ-A",
        "qc_id": "SYNTH-QC-A",
        "map_version": 1,
        "method_id": "SYNTH-METHOD-A",
        "segmentation_sha256": sha("seg-a"),
        "parameters_sha256": sha("param-a"),
        "map_sha256": sha("map-a"),
        "supersedes_map_id": "NONE",
    }
    return {**row, **overrides}


def handoff(**overrides):
    row = {
        "event_id": "EV-HANDOFF-A",
        "kind": "handoff_receipt",
        "handoff_id": "SYNTH-HANDOFF-A",
        "synthetic_subject_id": "SYNTH-SUBJECT-A",
        "map_id": "SYNTH-MAP-A",
        "handoff_role": "SYNTH-DOWNSTREAM-RECEIPT",
        "receipt_sha256": sha("handoff-a"),
    }
    return {**row, **overrides}


def valid_chain():
    return [batch(), dose(), acquisition(), qc(), map_version(), handoff()]


class WayneProvenanceRailTests(unittest.TestCase):
    def assertCode(self, code, callback):
        with self.assertRaises(RailError) as caught:
            callback()
        self.assertEqual(caught.exception.code, code)

    def test_acceptance_100_episode_contract(self):
        result = check_acceptance()
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["fixture_records"], 646)
        self.assertEqual(result["complete_synthetic_episodes"], 100)
        self.assertEqual(result["manifest"]["counts"], EXPECTED_COUNTS)

    def test_acceptance_quarantine_contract(self):
        manifest = check_acceptance()["manifest"]
        actual = {}
        for row in manifest["quarantines"]:
            actual[row["code"]] = actual.get(row["code"], 0) + 1
        self.assertEqual(actual, EXPECTED_QUARANTINES)

    def test_acceptance_order_invariant(self):
        fixture = generate_acceptance_fixture()
        self.assertEqual(
            reconcile(fixture)["receipt_sha256"],
            reconcile(list(reversed(fixture)))["receipt_sha256"],
        )

    def test_valid_chain_is_complete(self):
        manifest = reconcile(valid_chain())
        self.assertEqual(manifest["complete_synthetic_subjects"], 1)
        self.assertEqual(manifest["counts"]["handoffs_mapped"], 1)
        self.assertEqual(manifest["counts"]["quarantined"], 0)

    def test_exact_retry_collapses(self):
        chain = valid_chain()
        manifest = reconcile(chain + [deepcopy(chain[0]), deepcopy(chain[-1])])
        self.assertEqual(manifest["replay_collapsed"], 2)
        self.assertEqual(manifest["complete_synthetic_subjects"], 1)

    def test_changed_retry_conflicts(self):
        changed = batch(release_evidence_sha256=sha("changed"))
        self.assertCode("IDEMPOTENCY_CONFLICT", lambda: reconcile([batch(), changed]))

    def test_non_synthetic_subject_refused(self):
        self.assertCode(
            "NON_SYNTHETIC_SUBJECT",
            lambda: reconcile([batch(), dose(synthetic_subject_id="PATIENT-REAL-123")]),
        )

    def test_pii_shaped_field_refused(self):
        contaminated = {**batch(), "patient_id": "123"}
        self.assertCode("PII_FORBIDDEN", lambda: reconcile([contaminated]))

    def test_nested_payload_refused(self):
        contaminated = {**batch(), "raw_dicom": {"pixels": "nope"}}
        self.assertCode("NESTED_DATA_FORBIDDEN", lambda: reconcile([contaminated]))

    def test_unknown_batch_quarantines_dose_and_downstream(self):
        chain = valid_chain()[1:]
        chain[0]["batch_id"] = "SYNTH-BATCH-MISSING"
        manifest = reconcile(chain)
        codes = [row["code"] for row in manifest["quarantines"]]
        self.assertIn("DOSE_UNKNOWN_BATCH", codes)
        self.assertIn("ACQUISITION_UNAVAILABLE_DOSE", codes)
        self.assertEqual(manifest["complete_synthetic_subjects"], 0)

    def test_cross_subject_acquisition_quarantined(self):
        rows = valid_chain()
        rows[2]["synthetic_subject_id"] = "SYNTH-SUBJECT-B"
        manifest = reconcile(rows)
        self.assertIn("ACQUISITION_CROSS_SUBJECT", [q["code"] for q in manifest["quarantines"]])
        self.assertEqual(manifest["complete_synthetic_subjects"], 0)

    def test_cross_subject_qc_quarantined(self):
        rows = valid_chain()
        rows[3]["synthetic_subject_id"] = "SYNTH-SUBJECT-B"
        manifest = reconcile(rows)
        self.assertIn("QC_CROSS_SUBJECT", [q["code"] for q in manifest["quarantines"]])

    def test_map_without_qc_quarantined(self):
        rows = valid_chain()
        rows[4]["qc_id"] = "SYNTH-QC-MISSING"
        manifest = reconcile(rows)
        self.assertIn("MAP_UNAVAILABLE_QC", [q["code"] for q in manifest["quarantines"]])
        self.assertEqual(manifest["counts"]["map_versions_mapped"], 0)

    def test_two_maps_same_version_are_both_ambiguous(self):
        rows = valid_chain()[:-1]
        second = map_version(
            event_id="EV-MAP-B",
            map_id="SYNTH-MAP-B",
            segmentation_sha256=sha("seg-b"),
            parameters_sha256=sha("param-b"),
            map_sha256=sha("map-b"),
        )
        manifest = reconcile(rows + [second])
        ambiguous = [q for q in manifest["quarantines"] if q["code"] == "MAP_VERSION_AMBIGUOUS"]
        self.assertEqual(len(ambiguous), 2)
        self.assertEqual(manifest["counts"]["map_versions_mapped"], 0)

    def test_map_revision_requires_parent(self):
        rows = valid_chain()[:-2]
        revised = map_version(map_version=2)
        manifest = reconcile(rows + [revised])
        self.assertIn("MAP_VERSION_MISSING_PARENT", [q["code"] for q in manifest["quarantines"]])

    def test_map_revision_parent_scope_mismatch_quarantined(self):
        rows = valid_chain()[:-1]
        second_acq = acquisition(
            event_id="EV-ACQ-B",
            acquisition_id="SYNTH-ACQ-B",
            acquisition_evidence_sha256=sha("acq-b"),
        )
        second_qc = qc(
            event_id="EV-QC-B",
            qc_id="SYNTH-QC-B",
            acquisition_id="SYNTH-ACQ-B",
            qc_evidence_sha256=sha("qc-b"),
        )
        revised = map_version(
            event_id="EV-MAP-B",
            map_id="SYNTH-MAP-B",
            acquisition_id="SYNTH-ACQ-B",
            qc_id="SYNTH-QC-B",
            map_version=2,
            supersedes_map_id="SYNTH-MAP-A",
            segmentation_sha256=sha("seg-b"),
            parameters_sha256=sha("param-b"),
            map_sha256=sha("map-b"),
        )
        manifest = reconcile(rows + [second_acq, second_qc, revised])
        self.assertIn(
            "MAP_SUPERSESSION_SCOPE_MISMATCH",
            [q["code"] for q in manifest["quarantines"]],
        )

    def test_handoff_to_superseded_map_quarantined(self):
        rows = valid_chain()[:-1]
        revised = map_version(
            event_id="EV-MAP-B",
            map_id="SYNTH-MAP-B",
            map_version=2,
            supersedes_map_id="SYNTH-MAP-A",
            segmentation_sha256=sha("seg-b"),
            parameters_sha256=sha("param-b"),
            map_sha256=sha("map-b"),
        )
        stale = handoff()
        current = handoff(
            event_id="EV-HANDOFF-B",
            handoff_id="SYNTH-HANDOFF-B",
            map_id="SYNTH-MAP-B",
            receipt_sha256=sha("handoff-b"),
        )
        manifest = reconcile(rows + [revised, stale, current])
        self.assertIn("HANDOFF_SUPERSEDED_MAP", [q["code"] for q in manifest["quarantines"]])
        self.assertEqual(manifest["counts"]["handoffs_mapped"], 1)

    def test_handoff_cross_subject_quarantined(self):
        rows = valid_chain()
        rows[-1]["synthetic_subject_id"] = "SYNTH-SUBJECT-B"
        manifest = reconcile(rows)
        self.assertIn("HANDOFF_CROSS_SUBJECT", [q["code"] for q in manifest["quarantines"]])

    def test_resynthesis_lineage_accepts_increasing_revision(self):
        first = batch()
        second = batch(
            event_id="EV-BATCH-B",
            batch_id="SYNTH-BATCH-B",
            synthesis_run_id="SYNTH-SYNTHESIS-B",
            batch_revision=2,
            supersedes_batch_id="SYNTH-BATCH-A",
            release_evidence_sha256=sha("release-b"),
        )
        manifest = reconcile([first, second])
        self.assertEqual(manifest["counts"]["tracer_batches"], 2)

    def test_resynthesis_lineage_rejects_unknown_parent(self):
        second = batch(
            batch_id="SYNTH-BATCH-B",
            batch_revision=2,
            supersedes_batch_id="SYNTH-BATCH-MISSING",
        )
        self.assertCode("BATCH_LINEAGE_INVALID", lambda: reconcile([second]))

    def test_resynthesis_lineage_rejects_protocol_change(self):
        first = batch()
        second = batch(
            event_id="EV-BATCH-B",
            batch_id="SYNTH-BATCH-B",
            protocol_id="SYNTH-PROTOCOL-B",
            synthesis_run_id="SYNTH-SYNTHESIS-B",
            batch_revision=2,
            supersedes_batch_id="SYNTH-BATCH-A",
            release_evidence_sha256=sha("release-b"),
        )
        self.assertCode("BATCH_LINEAGE_INVALID", lambda: reconcile([first, second]))

    def test_receipt_verifies_and_detects_tampering(self):
        manifest = reconcile(valid_chain())
        self.assertTrue(verify_receipt(manifest))
        tampered = deepcopy(manifest)
        tampered["counts"]["handoffs_mapped"] += 1
        self.assertFalse(verify_receipt(tampered))

    def test_duplicate_business_id_fails_closed(self):
        other = batch(
            event_id="EV-BATCH-B",
            synthesis_run_id="SYNTH-SYNTHESIS-B",
            release_evidence_sha256=sha("release-b"),
        )
        self.assertCode("DUPLICATE_BATCH_ID", lambda: reconcile([batch(), other]))


if __name__ == "__main__":
    unittest.main()
