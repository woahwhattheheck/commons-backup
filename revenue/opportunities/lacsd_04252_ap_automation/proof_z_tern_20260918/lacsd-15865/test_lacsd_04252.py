from __future__ import annotations

import copy
import unittest
from pathlib import Path

from lacsd_04252 import (
    AUTHORITY_FALSE,
    CASE_SCHEMA,
    ContractError,
    compile_evidence,
    evaluate_case,
    evaluate_matrix,
    strict_load,
    strict_loads,
    validate_manifest,
    verify_evidence,
)

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "fixtures" / "manifest.json"
CASES = ROOT / "fixtures" / "ap_cases.json"
AS_OF = "2026-09-18T02:00:00Z"


def manifest():
    return strict_load(MANIFEST)


def matrix():
    return strict_load(CASES)


def base_case(**updates):
    row = {
        "schema": CASE_SCHEMA,
        "case_id": "base-001",
        "invoice_id": "invoice-base-001",
        "extraction_fields_total": 100,
        "extraction_fields_correct": 99,
        "received_at_utc": "2026-09-16T12:00:00Z",
        "ready_at_utc": "2026-09-17T12:00:00Z",
        "po_required": True,
        "po_present": True,
        "vendor_match": True,
        "invoice_total_cents": 10000,
        "po_total_cents": 10000,
        "tolerance_cents": 50,
        "duplicate": False,
        "routing_signoff_needed": True,
        "routing_signoff_present": True,
        "oracle_sync_evidenced": True,
        "audit_trail_complete": True,
        "dashboard_fresh": True,
    }
    row.update(updates)
    return row


class AcceptanceCaseTests(unittest.TestCase):
    def test_acceptance_boundary_and_authority(self):
        result = evaluate_case(base_case())
        self.assertEqual(result["decision"], "ACCEPT_EVIDENCE_READY")
        self.assertEqual(result["accuracy_bps"], 9900)
        for field in AUTHORITY_FALSE:
            self.assertFalse(result[field])

    def test_accuracy_below_99_holds(self):
        result = evaluate_case(base_case(extraction_fields_correct=98))
        self.assertEqual(result["decision"], "HOLD_EXTRACTION_ACCURACY")

    def test_cycle_under_48_hours_passes(self):
        result = evaluate_case(base_case(ready_at_utc="2026-09-18T11:59:59Z"))
        self.assertEqual(result["decision"], "ACCEPT_EVIDENCE_READY")
        self.assertEqual(result["cycle_seconds"], 172799)

    def test_cycle_exactly_48_hours_holds(self):
        result = evaluate_case(base_case(ready_at_utc="2026-09-18T12:00:00Z"))
        self.assertEqual(result["decision"], "HOLD_CYCLE_TIME")

    def test_missing_routing_signoff_holds(self):
        result = evaluate_case(base_case(routing_signoff_present=False))
        self.assertEqual(result["decision"], "HOLD_APPROVAL")

    def test_banned_admission_identifier_absent(self):
        banned = "approval" + "_required"
        for rel in (
            "lacsd_04252.py",
            "test_lacsd_04252.py",
            "fixtures/ap_cases.json",
            "fixtures/manifest.json",
            "README.md",
        ):
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertNotIn(banned, text)

    def test_nonpo_invoice_does_not_inherit_po_variance(self):
        result = evaluate_case(
            base_case(
                po_required=False,
                po_present=False,
                invoice_total_cents=40000,
                po_total_cents=10000,
            )
        )
        self.assertEqual(result["decision"], "ACCEPT_EVIDENCE_READY")

    def test_bool_int_alias_rejected(self):
        with self.assertRaises(ContractError):
            evaluate_case(base_case(duplicate=0))

    def test_correct_fields_cannot_exceed_total(self):
        with self.assertRaises(ContractError):
            evaluate_case(base_case(extraction_fields_correct=101))

    def test_ready_cannot_precede_receipt(self):
        with self.assertRaises(ContractError):
            evaluate_case(base_case(ready_at_utc="2026-09-16T11:59:59Z"))

    def test_unknown_key_rejected(self):
        row = base_case()
        row["magic"] = True
        with self.assertRaises(ContractError):
            evaluate_case(row)

    def test_deterministic_under_key_reordering(self):
        row = base_case()
        reversed_row = dict(reversed(list(row.items())))
        self.assertEqual(evaluate_case(row), evaluate_case(reversed_row))


class MatrixTests(unittest.TestCase):
    def test_shipped_matrix_covers_every_terminal(self):
        result = evaluate_matrix(matrix())
        self.assertEqual(result["case_count"], 11)
        self.assertTrue(all(count == 1 for count in result["decision_counts"].values()))
        for field in AUTHORITY_FALSE:
            self.assertFalse(result[field])

    def test_expected_decision_mismatch_fails_closed(self):
        doc = matrix()
        doc["cases"][0]["expected_decision"] = "HOLD_APPROVAL"
        with self.assertRaises(ContractError):
            evaluate_matrix(doc)

    def test_duplicate_case_id_fails_closed(self):
        doc = matrix()
        doc["cases"][1]["case"]["case_id"] = doc["cases"][0]["case"]["case_id"]
        with self.assertRaises(ContractError):
            evaluate_matrix(doc)

    def test_missing_terminal_fails_closed(self):
        doc = matrix()
        doc["cases"] = [
            row for row in doc["cases"]
            if row["expected_decision"] != "HOLD_DASHBOARD_FRESHNESS"
        ]
        with self.assertRaises(ContractError):
            evaluate_matrix(doc)


class PursuitContractTests(unittest.TestCase):
    def test_current_deadline_consensus_keeps_submission_gate_closed(self):
        result = validate_manifest(manifest(), AS_OF)
        self.assertFalse(result["deadline_conflict"])
        self.assertEqual(result["deadline_state"], "CURRENT_BUYER_PAGES_AGREE")
        self.assertEqual(result["bid_due_utc"], "2026-10-15T18:00:00Z")
        self.assertEqual(
            result["submission_state"], "HOLD_QUESTCDN_PACKET_AND_PLANHOLDER"
        )
        self.assertEqual(
            result["submission_control_state"],
            "QUESTCDN_PACKET_DOWNLOAD_AND_PLANHOLDER_NOT_ESTABLISHED",
        )
        self.assertEqual(result["teaming_build_state"], "READY")
        self.assertEqual(result["commercial_offer_state"], "PROPOSED_NOT_ACCEPTED")
        self.assertEqual(result["commercial_offer_price_usd_cents"], 500000)
        for field in AUTHORITY_FALSE:
            self.assertFalse(result[field])

    def test_offer_cannot_self_accept(self):
        doc = manifest()
        doc["commercial_offer"]["state"] = "ACCEPTED"
        with self.assertRaises(ContractError):
            validate_manifest(doc, AS_OF)

    def test_offer_cannot_authorize_external_send(self):
        doc = manifest()
        doc["commercial_offer"]["external_send_authorized"] = True
        with self.assertRaises(ContractError):
            validate_manifest(doc, AS_OF)

    def test_manifest_cannot_authorize_submission(self):
        doc = manifest()
        doc["authority"]["submission_authorized"] = True
        with self.assertRaises(ContractError):
            validate_manifest(doc, AS_OF)

    def test_manifest_cannot_authorize_oracle_write(self):
        doc = manifest()
        doc["authority"]["oracle_write_authorized"] = True
        with self.assertRaises(ContractError):
            validate_manifest(doc, AS_OF)

    def test_packet_cannot_self_attest_retention(self):
        doc = manifest()
        doc["submission_evidence"]["authorized_packet_retained"] = True
        with self.assertRaises(ContractError):
            validate_manifest(doc, AS_OF)

    def test_proper_download_cannot_self_attest(self):
        doc = manifest()
        doc["submission_evidence"]["proper_download_evidenced"] = True
        with self.assertRaises(ContractError):
            validate_manifest(doc, AS_OF)

    def test_planholder_status_cannot_self_promote(self):
        doc = manifest()
        doc["submission_evidence"]["planholder_status"] = "PLANHOLDER"
        with self.assertRaises(ContractError):
            validate_manifest(doc, AS_OF)

    def test_legacy_purchasing_list_cannot_replace_current_deadline_root(self):
        doc = manifest()
        doc["sources"]["current_list"]["url"] = (
            "https://www.lacsd.org/opportunities/bids-purchasing/"
            "purchasing-section-projects/-sortn-RFPTitle"
        )
        with self.assertRaises(ContractError):
            validate_manifest(doc, AS_OF)

    def test_detail_deadline_drift_rejected(self):
        doc = manifest()
        doc["sources"]["detail"]["due_utc"] = "2026-10-16T18:00:00Z"
        with self.assertRaises(ContractError):
            validate_manifest(doc, AS_OF)

    def test_list_deadline_drift_rejected(self):
        doc = manifest()
        doc["sources"]["current_list"]["due_utc"] = "2026-09-30T18:00:00Z"
        with self.assertRaises(ContractError):
            validate_manifest(doc, AS_OF)

    def test_future_source_generation_rejected(self):
        doc = manifest()
        doc["sources"]["detail"]["captured_at_utc"] = "2026-09-18T02:00:01Z"
        with self.assertRaises(ContractError):
            validate_manifest(doc, AS_OF)

    def test_requirements_cannot_reduce_accuracy_target(self):
        doc = manifest()
        doc["requirements"]["target_accuracy_bps"] = 9800
        with self.assertRaises(ContractError):
            validate_manifest(doc, AS_OF)

    def test_duplicate_json_key_rejected(self):
        with self.assertRaises(ContractError):
            strict_loads('{"a":1,"a":2}')

    def test_nonfinite_json_rejected(self):
        with self.assertRaises(ContractError):
            strict_loads('{"a":NaN}')

    def test_expired_latest_public_window_holds_teaming(self):
        result = validate_manifest(manifest(), "2026-10-15T18:00:00Z")
        self.assertEqual(result["teaming_build_state"], "HOLD_RESPONSE_WINDOW")
        self.assertEqual(result["submission_state"], "HOLD_QUESTCDN_PACKET_AND_PLANHOLDER")


class EvidenceBundleTests(unittest.TestCase):
    def test_compile_bundle_is_review_ready_not_submission_ready(self):
        bundle = compile_evidence(manifest(), matrix(), AS_OF)
        self.assertEqual(bundle["teaming_review_verdict"], "READY_FOR_PAID_TEAMING_REVIEW")
        self.assertEqual(bundle["submission_verdict"], "HOLD_QUESTCDN_PACKET_AND_PLANHOLDER")
        for field in AUTHORITY_FALSE:
            self.assertFalse(bundle[field])
        self.assertTrue(verify_evidence(bundle, manifest(), matrix(), AS_OF))

    def test_bundle_tamper_is_detected(self):
        bundle = compile_evidence(manifest(), matrix(), AS_OF)
        forged = copy.deepcopy(bundle)
        forged["submission_verdict"] = "READY"
        self.assertFalse(verify_evidence(forged, manifest(), matrix(), AS_OF))


if __name__ == "__main__":
    unittest.main()
