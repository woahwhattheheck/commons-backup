"""Independent synthetic acceptance cases for #15930; no provider calls.

Run with: python -B -m unittest -v test_cairn_batch_identity.py
Private _compile_bundle_at is used only to hold the fixture clock/source constant.
No buyer-source generation is approved by these fixtures.
"""
import copy
from datetime import datetime, timezone
import hashlib
import unittest
import unc_ap_ai_v2 as m

AT = datetime(2026, 9, 18, 6, 0, tzinfo=timezone.utc)


def invoice(invoice_id="INV-001", supplier_id="SUP-7", amount=12500):
    row = {
        "invoice_id": invoice_id, "supplier_id": supplier_id,
        "extracted_supplier_id": supplier_id,
        "expected_amount_cents": amount, "extracted_amount_cents": amount,
        "match_mode": "THREE_WAY", "purchase_order_amount_cents": amount,
        "receipt_amount_cents": amount, "routing_signoff_needed": True,
        "routing_signoff_present": True, "extraction_fields_total": 100,
        "extraction_fields_correct": 100, "duplicate_seen": False,
        "audit_events": ["received", "extracted", "validated", "matched",
                         "routing_started", "routing_completed", "erp_staged"],
    }
    row["integration"] = m.expected_integration_evidence(row)
    return row


def partner():
    return {
        "name": "SYNTHETIC TEST PARTNER", "ap_automation_evidence": "fixture",
        "peoplesoft_evidence": "fixture", "route": "offline fixture only",
        "researched_at": "2026-09-17T21:15:00-04:00",
    }


def source():
    raw = b"SYNTHETIC fixture; not a buyer document"
    docs = {"fixture.txt": raw}
    manifest = [{"name": "fixture.txt", "sha256": hashlib.sha256(raw).hexdigest()}]
    ledger = {
        "schema": m.SOURCE_SCHEMA, "buyer": m.BUYER,
        "solicitation_id": m.SOLICITATION_ID, "first_party_url": m.FIRST_PARTY_URL,
        "status": "OPEN", "observed_at": "2026-09-18T00:00:00Z",
        "offer_due_at": "2026-09-25T16:00:00Z",
        "source_generation": m.receipt({"schema": m.SOURCE_MANIFEST_SCHEMA,
                                        "documents": manifest}),
        "required_documents": manifest,
    }
    return ledger, docs


def bundle(cases):
    ledger, docs = source()
    return m._compile_bundle_at(ledger, docs, cases, [partner()], as_of=AT)


def evaluate(row):
    return m.evaluate_invoice_case(row, extraction_threshold_basis_points=9900)


class CairnBatchIdentity(unittest.TestCase):
    def test_distinct_invoices_control(self):
        result = bundle([invoice(), invoice("INV-002")])
        self.assertEqual(result["state"], "INTERNAL_WORKSHARE_READY")

    def test_single_invoice_control(self):
        self.assertEqual(evaluate(invoice())["disposition"], "PASS")

    def test_duplicate_supplier_invoice_is_not_ready(self):
        row = invoice()
        self.assertNotEqual(bundle([row, copy.deepcopy(row)])["state"],
                            "INTERNAL_WORKSHARE_READY")

    def test_same_business_identity_different_amount_is_not_ready(self):
        self.assertNotEqual(bundle([invoice(amount=12500), invoice(amount=12501)])["state"],
                            "INTERNAL_WORKSHARE_READY")

    def test_supplier_scopes_effect_identity(self):
        first = invoice(supplier_id="SUP-7")
        second = invoice(supplier_id="SUP-8")
        self.assertNotEqual(first["integration"]["effect_key"],
                            second["integration"]["effect_key"])

    def test_request_generation_controls_request_binding(self):
        self.assertNotEqual(evaluate(invoice(amount=12500))["request_binding_sha256"],
                            evaluate(invoice(amount=12501))["request_binding_sha256"])

    def test_wrong_request_digest_is_rejected(self):
        row = invoice()
        row["integration"]["request_sha256"] = "0" * 64
        self.assertEqual(evaluate(row)["disposition"], "HOLD_INTEGRATION")

    def test_observed_bad_digests_have_distinct_receipts(self):
        first, second = invoice(), invoice()
        first["integration"]["request_sha256"] = "0" * 64
        second["integration"]["request_sha256"] = "1" * 64
        self.assertNotEqual(evaluate(first)["receipt_sha256"],
                            evaluate(second)["receipt_sha256"])

    def test_audit_inputs_are_receipt_bound(self):
        first, second = invoice(), invoice()
        second["audit_events"].append("synthetic_secondary_review")
        self.assertNotEqual(evaluate(first)["receipt_sha256"],
                            evaluate(second)["receipt_sha256"])

    def test_retry_count_is_receipt_bound(self):
        first, second = invoice(), invoice()
        second["integration"]["retry_count"] = 2
        self.assertNotEqual(evaluate(first)["receipt_sha256"],
                            evaluate(second)["receipt_sha256"])

    def test_partner_observation_is_receipt_bound(self):
        first, second = partner(), partner()
        second["researched_at"] = "2026-09-18T00:00:00-04:00"
        self.assertNotEqual(m.compile_partner(first)["receipt_sha256"],
                            m.compile_partner(second)["receipt_sha256"])

    def test_changed_source_bytes_do_not_bind(self):
        ledger, docs = source()
        docs["fixture.txt"] += b"changed"
        self.assertEqual(m._compile_source_at(ledger, docs, as_of=AT)["state"],
                         "HOLD_SOURCE_BYTES")

    def test_deadline_control(self):
        ledger, docs = source()
        after = datetime(2026, 9, 25, 16, 0, tzinfo=timezone.utc)
        self.assertEqual(m._compile_source_at(ledger, docs, as_of=after)["state"],
                         "HOLD_DEADLINE")

    def test_money_bool_rejected(self):
        row = invoice()
        row["expected_amount_cents"] = True
        with self.assertRaises(m.ContractError):
            evaluate(row)

    def test_unknown_case_field_rejected(self):
        row = invoice()
        row["unchecked_amount"] = 20
        with self.assertRaises(m.ContractError):
            evaluate(row)

    def test_amount_change_preserves_business_effect_identity(self):
        self.assertEqual(invoice(amount=12500)["integration"]["effect_key"],
                         invoice(amount=12501)["integration"]["effect_key"])

    def test_structured_effect_identity_prevents_delimiter_alias(self):
        a = invoice(invoice_id="B:C", supplier_id="A")
        b = invoice(invoice_id="C", supplier_id="A:B")
        self.assertNotEqual(a["integration"]["effect_key"], b["integration"]["effect_key"])

    def test_different_suppliers_same_invoice_is_valid_control(self):
        result = bundle([invoice(supplier_id="SUP-7"), invoice(supplier_id="SUP-8")])
        self.assertEqual(result["state"], "INTERNAL_WORKSHARE_READY")
        self.assertEqual(result["batch_conflicts"], [])

    def test_duplicate_details_preserve_all_cases(self):
        result = bundle([invoice(), invoice(amount=12501), invoice("INV-002")])
        self.assertEqual(len(result["cases"]), 3)
        self.assertEqual(result["batch_conflicts"], [
            {"supplier_id": "SUP-7", "invoice_id": "INV-001", "case_count": 2}])

    def test_conflict_summary_is_order_invariant(self):
        rows = [invoice(), invoice("INV-002"), invoice(amount=12501)]
        self.assertEqual(bundle(rows)["batch_conflicts"], bundle(rows[::-1])["batch_conflicts"])

    def test_batch_receipt_binds_case_generation(self):
        self.assertNotEqual(bundle([invoice(amount=12500)])["batch_input_sha256"],
                            bundle([invoice(amount=12501)])["batch_input_sha256"])

    def test_no_external_authority(self):
        self.assertTrue(all(value is False for value in bundle([invoice()])["authority"].values()))


if __name__ == "__main__":
    unittest.main()
