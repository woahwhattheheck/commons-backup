from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import unittest

from .acceptance import EXPECTED_HOLD_GROUPS, make_ready_packet, run_acceptance
from .gate import (
    EvidenceGateError,
    GateLedger,
    HOLD,
    READY,
    SensitiveEvidenceError,
    evaluate,
    verify_decision,
    verify_manifest,
)


class CrownBioProvenanceGateTests(unittest.TestCase):
    def packet(self):
        return make_ready_packet(1)

    def test_ready_packet(self):
        decision = evaluate(self.packet())
        self.assertEqual(READY, decision.status)
        self.assertEqual((), decision.reasons)
        self.assertTrue(verify_decision(decision))

    def test_model_lineage_mismatch(self):
        packet = self.packet()
        packet["artifact_model_id"] = "mdl_wrong"
        decision = evaluate(packet)
        self.assertEqual(HOLD, decision.status)
        self.assertIn("MODEL_LINEAGE_MISMATCH", decision.reasons)

    def test_passage_mismatch_and_out_of_scope(self):
        packet = self.packet()
        packet["passage"] = 15
        decision = evaluate(packet)
        self.assertIn("PASSAGE_OUT_OF_SCOPE", decision.reasons)
        self.assertIn("PASSAGE_LINEAGE_MISMATCH", decision.reasons)

    def test_study_lineage_mismatch(self):
        packet = self.packet()
        packet["custody_study_id"] = "std_wrong"
        self.assertIn("STUDY_LINEAGE_MISMATCH", evaluate(packet).reasons)

    def test_use_scope(self):
        packet = self.packet()
        packet["declared_use"] = "diagnostic_release"
        self.assertIn("USE_OUT_OF_SCOPE", evaluate(packet).reasons)

    def test_assay_scope(self):
        packet = self.packet()
        packet["assay_version"] = "v9.9"
        self.assertIn("ASSAY_OUT_OF_DECLARED_SCOPE", evaluate(packet).reasons)

    def test_site_scope(self):
        packet = self.packet()
        packet["accreditation_site_id"] = "site_other"
        self.assertIn("ACCREDITATION_SITE_MISMATCH", evaluate(packet).reasons)

    def test_stale_accreditation_scope(self):
        packet = self.packet()
        packet["accreditation_valid_through"] = "2026-09-12"
        self.assertIn("ACCREDITATION_SCOPE_STALE", evaluate(packet).reasons)

    def test_qc_not_ready(self):
        packet = self.packet()
        packet["qc_state"] = "hold_for_review"
        self.assertIn("QC_NOT_READY", evaluate(packet).reasons)

    def test_zero_checksum_sentinel(self):
        packet = self.packet()
        packet["artifact_sha256"] = "0" * 64
        self.assertIn("ARTIFACT_DIGEST_SENTINEL", evaluate(packet).reasons)

    def test_unknown_field_rejected(self):
        packet = self.packet()
        packet["internal_note"] = "x"
        with self.assertRaises(EvidenceGateError):
            evaluate(packet)

    def test_direct_phi_key_rejected(self):
        packet = self.packet()
        packet["patient_name"] = "x"
        with self.assertRaises(SensitiveEvidenceError):
            evaluate(packet)

    def test_nested_sensitive_key_rejected_before_unknown_field(self):
        packet = self.packet()
        packet["wrapper"] = {"diagnosis": "x"}
        with self.assertRaises(SensitiveEvidenceError):
            evaluate(packet)

    def test_dict_subclass_rejected(self):
        class Evil(dict):
            pass
        with self.assertRaises(EvidenceGateError):
            evaluate(Evil(self.packet()))

    def test_invalid_timestamp_rejected(self):
        packet = self.packet()
        packet["recorded_at"] = "2026-02-31T10:00:00Z"
        with self.assertRaises(EvidenceGateError):
            evaluate(packet)

    def test_invalid_scope_date_rejected(self):
        packet = self.packet()
        packet["accreditation_valid_through"] = "2027-02-31"
        with self.assertRaises(EvidenceGateError):
            evaluate(packet)

    def test_bool_passage_rejected(self):
        packet = self.packet()
        packet["passage"] = True
        with self.assertRaises(EvidenceGateError):
            evaluate(packet)

    def test_exact_replay_collapses_without_new_manifest_row(self):
        ledger = GateLedger()
        packet = self.packet()
        first = ledger.apply(packet)
        replay = ledger.apply(deepcopy(packet))
        self.assertFalse(first.replayed)
        self.assertTrue(replay.replayed)
        self.assertEqual(first.decision_digest, replay.decision_digest)
        self.assertEqual(1, ledger.entry_count)

    def test_same_event_changed_payload_holds_and_is_audited(self):
        ledger = GateLedger()
        packet = self.packet()
        ledger.apply(packet)
        changed = deepcopy(packet)
        changed["artifact_sha256"] = "f" * 64
        conflict = ledger.apply(changed)
        self.assertEqual(HOLD, conflict.status)
        self.assertEqual(("EVENT_ID_CHANGED_PAYLOAD",), conflict.reasons)
        self.assertEqual(2, ledger.entry_count)
        self.assertTrue(verify_manifest(ledger.canonical_manifest()))

    def test_manifest_order_invariant(self):
        packets = [make_ready_packet(i) for i in range(12)]
        forward = GateLedger()
        reverse = GateLedger()
        for packet in packets:
            forward.apply(packet)
        for packet in reversed(packets):
            reverse.apply(packet)
        self.assertEqual(forward.canonical_manifest(), reverse.canonical_manifest())

    def test_manifest_tamper_rejected(self):
        ledger = GateLedger()
        ledger.apply(self.packet())
        manifest = ledger.canonical_manifest()
        manifest["rows"][0]["decision"]["status"] = HOLD
        self.assertFalse(verify_manifest(manifest))

    def test_decision_tamper_rejected(self):
        decision = evaluate(self.packet())
        tampered = replace(decision, packet_digest="f" * 64)
        self.assertFalse(verify_decision(tampered))

    def test_acceptance_fixture_exact_distribution(self):
        result = run_acceptance()
        self.assertTrue(result["passed"])
        self.assertEqual(150, result["total"])
        self.assertEqual(126, result["study_ready"])
        self.assertEqual(24, result["hold"])
        self.assertEqual(EXPECTED_HOLD_GROUPS, result["hold_reasons"])
        self.assertEqual(10, result["exact_replays"])
        self.assertTrue(result["checks"]["manifest_valid"])


if __name__ == "__main__":
    unittest.main()
