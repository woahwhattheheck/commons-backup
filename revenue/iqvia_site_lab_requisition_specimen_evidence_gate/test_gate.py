from __future__ import annotations

import copy
import unittest

from .acceptance import run_acceptance
from .fixtures import frozen_packets
from .gate import (
    AUTHORITY,
    CODES,
    EvidenceError,
    SOURCE_REF_KIND,
    STATUS_HOLD,
    STATUS_READY,
    compute_source_refs,
    evaluate_batch,
    evaluate_packet,
    output_manifest,
    render_csv,
    render_json,
    verify_report,
)


def refresh(packet, *names):
    refs = compute_source_refs(packet["sources"])
    for name in names:
        packet["source_refs"][name] = refs[name]


class IqviaSiteLabGateTests(unittest.TestCase):
    def test_full_frozen_acceptance_contract(self):
        receipt = run_acceptance()
        self.assertEqual(receipt["status"], "PASS")
        self.assertEqual((receipt["packets"], receipt["ready"], receipt["hold"]), (180, 145, 35))
        self.assertEqual(receipt["reason_counts"], {code: 5 for code in CODES})

    def test_pure_evaluation_does_not_mutate_source_packets(self):
        packets = frozen_packets()
        before = copy.deepcopy(packets)
        report = evaluate_batch(packets)
        self.assertEqual(packets, before)
        self.assertEqual(report["authority"], AUTHORITY)

    def test_byte_identical_json_csv_manifest_replay(self):
        a = evaluate_batch(frozen_packets())
        b = evaluate_batch(frozen_packets())
        self.assertEqual(render_json(a), render_json(b))
        self.assertEqual(render_csv(a), render_csv(b))
        self.assertEqual(output_manifest(a), output_manifest(b))
        self.assertTrue(verify_report(frozen_packets(), a))

    def test_source_semantic_mutation_under_stale_hash_fails(self):
        packet = frozen_packets()[0]
        packet["sources"]["requisition"]["visit_id"] = "VISIT-99"
        with self.assertRaisesRegex(EvidenceError, "source_refs"):
            evaluate_packet(packet)

    def test_cross_source_hash_transplant_fails(self):
        packet = frozen_packets()[0]
        packet["source_refs"]["protocol"] = packet["source_refs"]["requisition"]
        with self.assertRaisesRegex(EvidenceError, "source_refs"):
            evaluate_packet(packet)

    def test_old_self_grading_expected_knob_is_not_in_schema(self):
        packet = frozen_packets()[0]
        packet["expected_protocol_id"] = "PROTO-ATTACKER"
        with self.assertRaisesRegex(EvidenceError, "packet must contain exactly"):
            evaluate_packet(packet)

    def test_refreshed_requisition_source_mismatch_holds(self):
        packet = frozen_packets()[0]
        packet["sources"]["requisition"]["visit_id"] = "VISIT-99"
        refresh(packet, "requisition")
        row = evaluate_packet(packet)
        self.assertEqual(row["status"], STATUS_HOLD)
        self.assertEqual(row["reason_codes"], ["PROTOCOL_VISIT_MISMATCH"])

    def test_requisition_generation_cannot_cross_collection(self):
        packet = frozen_packets()[0]
        packet["sources"]["collection"]["requisition_version"] = "REQ-v2"
        refresh(packet, "collection")
        row = evaluate_packet(packet)
        self.assertEqual(row["reason_codes"], ["REQUISITION_GENERATION_MISMATCH"])

    def test_query_resolution_transplant_needs_new_source_ref_then_holds(self):
        packet = frozen_packets()[0]
        packet["sources"]["queries"]["items"][0]["status"] = "OPEN"
        packet["sources"]["queries"]["items"][0]["resolution_evidence_hash"] = None
        with self.assertRaisesRegex(EvidenceError, "source_refs"):
            evaluate_packet(packet)
        refresh(packet, "queries")
        self.assertEqual(evaluate_packet(packet)["reason_codes"], ["UNRESOLVED_QUERY"])

    def test_method_allowlist_drift_is_bound_to_method_source(self):
        packet = frozen_packets()[0]
        packet["sources"]["method"]["allowed_sample_types"] = ["PLASMA"]
        with self.assertRaisesRegex(EvidenceError, "source_refs"):
            evaluate_packet(packet)
        refresh(packet, "method")
        self.assertEqual(
            evaluate_packet(packet)["reason_codes"],
            ["ACCESSION_METHOD_INCOMPATIBLE"],
        )

    def test_kit_expiry_drift_is_bound_to_kit_source(self):
        packet = frozen_packets()[0]
        packet["sources"]["kit"]["expires_at"] = "2026-09-01T00:00:00Z"
        with self.assertRaisesRegex(EvidenceError, "source_refs"):
            evaluate_packet(packet)
        refresh(packet, "kit")
        self.assertEqual(evaluate_packet(packet)["reason_codes"], ["KIT_INVALID_FOR_COLLECTION"])

    def test_courier_limits_come_from_kit_not_courier_candidate(self):
        packet = frozen_packets()[0]
        self.assertNotIn("transport_min_c", packet["sources"]["courier"])
        packet["sources"]["kit"]["transport_max_c"] = 3.0
        refresh(packet, "kit")
        self.assertEqual(evaluate_packet(packet)["reason_codes"], ["COURIER_EVIDENCE_INVALID"])

    def test_kit_lot_lineage_mismatch_holds(self):
        packet = frozen_packets()[0]
        packet["sources"]["courier"]["kit_lot"] = "KIT-OTHER"
        refresh(packet, "courier")
        self.assertEqual(evaluate_packet(packet)["reason_codes"], ["KIT_INVALID_FOR_COLLECTION"])

    def test_collection_outside_requisition_window_holds(self):
        packet = frozen_packets()[0]
        packet["sources"]["collection"]["collected_at"] = "2026-09-13T17:00:00Z"
        refresh(packet, "collection")
        self.assertEqual(evaluate_packet(packet)["reason_codes"], ["COLLECTION_WINDOW_BREACH"])

    def test_missing_courier_observation_holds(self):
        packet = frozen_packets()[0]
        packet["sources"]["courier"]["scan_id"] = None
        packet["sources"]["courier"]["temperature_c"] = None
        refresh(packet, "courier")
        self.assertEqual(evaluate_packet(packet)["reason_codes"], ["COURIER_EVIDENCE_INVALID"])

    def test_source_authenticity_is_mechanically_false(self):
        row = evaluate_packet(frozen_packets()[0])
        self.assertEqual(row["status"], STATUS_READY)
        self.assertIs(row["source_authenticity_verified"], False)
        self.assertEqual(row["source_ref_kind"], SOURCE_REF_KIND)
        report = evaluate_batch([frozen_packets()[0]])
        self.assertIs(report["source_authenticity_verified"], False)

    def test_verify_report_rejects_resealed_semantic_tamper(self):
        packets = frozen_packets()
        report = evaluate_batch(packets)
        forged = copy.deepcopy(report)
        forged["results"][0]["status"] = STATUS_HOLD
        self.assertFalse(verify_report(packets, forged))

    def test_unknown_source_field_fails_closed_even_with_refreshed_hash(self):
        packet = frozen_packets()[0]
        packet["sources"]["kit"]["buyer_says_ready"] = True
        refresh(packet, "kit")
        with self.assertRaisesRegex(EvidenceError, "sources.kit must contain exactly"):
            evaluate_packet(packet)

    def test_nonfinite_source_number_fails_before_hashing(self):
        packet = frozen_packets()[0]
        packet["sources"]["courier"]["temperature_c"] = float("nan")
        with self.assertRaises(EvidenceError):
            compute_source_refs(packet["sources"])

    def test_duplicate_packet_identity_fails_closed(self):
        packet = frozen_packets()[0]
        with self.assertRaises(EvidenceError):
            evaluate_batch([packet, copy.deepcopy(packet)])

    def test_report_contains_no_consequential_authority(self):
        report = evaluate_batch(frozen_packets())
        payload = render_json(report).decode("utf-8").lower()
        self.assertEqual(set(report["status_counts"]), {STATUS_READY, STATUS_HOLD})
        self.assertNotIn('"clinical_decision"', payload)
        self.assertNotIn('"specimen_disposition"', payload)
        self.assertNotIn('"eligible"', payload)
        self.assertNotIn('"source_authenticity_verified":true', payload)


if __name__ == "__main__":
    unittest.main()
