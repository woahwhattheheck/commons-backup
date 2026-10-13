from datetime import datetime, timezone
import hashlib
import unittest

import unc_ap_ai as m


AS_OF = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)
AUDIT = [
    "received", "extracted", "validated", "matched",
    "routing_started", "routing_completed", "erp_staged",
]


def bound_ledger(documents):
    manifest = [
        {"name": name, "sha256": hashlib.sha256(raw).hexdigest()}
        for name, raw in sorted(documents.items())
    ]
    generation = m.receipt(
        {"schema": m.SOURCE_MANIFEST_SCHEMA, "documents": manifest}
    )
    return {
        "schema": m.SOURCE_SCHEMA,
        "buyer": m.BUYER,
        "solicitation_id": m.SOLICITATION_ID,
        "first_party_url": m.FIRST_PARTY_URL,
        "status": "OPEN",
        "observed_at": "2026-09-17T21:15:00-04:00",
        "offer_due_at": "2026-09-25T12:00:00-04:00",
        "source_generation": generation,
        "required_documents": manifest,
    }


def valid_case():
    case = {
        "invoice_id": "INV-001",
        "supplier_id": "SUP-7",
        "extracted_supplier_id": "SUP-7",
        "expected_amount_cents": 125_000,
        "extracted_amount_cents": 125_000,
        "match_mode": "TWO_WAY",
        "purchase_order_amount_cents": 125_000,
        "receipt_amount_cents": None,
        "routing_signoff_needed": False,
        "routing_signoff_present": False,
        "extraction_fields_total": 100,
        "extraction_fields_correct": 100,
        "duplicate_seen": False,
        "integration": {},
        "audit_events": list(AUDIT),
    }
    case["integration"] = m.expected_integration_evidence(case)
    return case


class TestSourceBinding(unittest.TestCase):
    def test_public_legacy_source_is_fail_closed(self):
        self.assertEqual(m.compile_source({})["state"], "HOLD_SOURCE_BYTES")

    def test_exact_manifest_and_retained_bytes_promote_only_exact_generation(self):
        documents = {
            "RFP.pdf": b"official-rfp-bytes-v1",
            "Addendum-1.pdf": b"official-addendum-bytes-v1",
        }
        ledger = bound_ledger(documents)
        result = m._compile_source_at(ledger, documents, as_of=AS_OF)
        self.assertEqual(result["state"], "SOURCE_BOUND")
        self.assertEqual(
            {row["name"]: row["sha256"] for row in result["computed_documents"]},
            {name: hashlib.sha256(raw).hexdigest() for name, raw in documents.items()},
        )

    def test_changed_retained_bytes_hold(self):
        documents = {"RFP.pdf": b"official-rfp-bytes-v1"}
        ledger = bound_ledger(documents)
        changed = {"RFP.pdf": b"official-rfp-bytes-v2"}
        self.assertEqual(
            m._compile_source_at(ledger, changed, as_of=AS_OF)["state"],
            "HOLD_SOURCE_BYTES",
        )

    def test_missing_or_extra_retained_document_holds(self):
        documents = {
            "RFP.pdf": b"rfp",
            "Addendum-1.pdf": b"addendum",
        }
        ledger = bound_ledger(documents)
        self.assertEqual(
            m._compile_source_at(
                ledger, {"RFP.pdf": documents["RFP.pdf"]}, as_of=AS_OF
            )["state"],
            "HOLD_SOURCE_BYTES",
        )
        with_extra = dict(documents)
        with_extra["unbound.txt"] = b"not-in-manifest"
        self.assertEqual(
            m._compile_source_at(ledger, with_extra, as_of=AS_OF)["state"],
            "HOLD_SOURCE_BYTES",
        )

    def test_manifest_generation_cannot_self_remint(self):
        documents = {"RFP.pdf": b"rfp"}
        ledger = bound_ledger(documents)
        ledger["source_generation"] = "0" * 64
        with self.assertRaises(m.ContractError):
            m._compile_source_at(ledger, documents, as_of=AS_OF)


class TestRequestAckBinding(unittest.TestCase):
    def test_valid_request_ack_binding_passes(self):
        result = m.evaluate_invoice_case(
            valid_case(), extraction_threshold_basis_points=9_900
        )
        self.assertEqual(result["disposition"], "PASS")
        self.assertFalse(result["provider_ack_independently_authenticated"])

    def test_request_digest_tamper_holds(self):
        case = valid_case()
        case["integration"]["request_sha256"] = "0" * 64
        self.assertEqual(
            m.evaluate_invoice_case(
                case, extraction_threshold_basis_points=9_900
            )["disposition"],
            "HOLD_INTEGRATION",
        )

    def test_ack_digest_tamper_holds(self):
        case = valid_case()
        case["integration"]["ack_sha256"] = "f" * 64
        self.assertEqual(
            m.evaluate_invoice_case(
                case, extraction_threshold_basis_points=9_900
            )["disposition"],
            "HOLD_INTEGRATION",
        )

    def test_semantics_changed_after_binding_holds(self):
        case = valid_case()
        case["extraction_fields_correct"] = 99
        self.assertEqual(
            m.evaluate_invoice_case(
                case, extraction_threshold_basis_points=9_000
            )["disposition"],
            "HOLD_INTEGRATION",
        )

    def test_forged_ack_result_holds(self):
        case = valid_case()
        integration = case["integration"]
        integration["ack_sha256"] = m.receipt(
            {
                "schema": m.ACK_SCHEMA,
                "request_sha256": integration["request_sha256"],
                "effect_key": integration["effect_key"],
                "result": "REJECTED",
            }
        )
        self.assertEqual(
            m.evaluate_invoice_case(
                case, extraction_threshold_basis_points=9_900
            )["disposition"],
            "HOLD_INTEGRATION",
        )

    def test_effect_and_retry_identity_tamper_hold(self):
        for field, value in (
            ("effect_key", "invoice:OTHER"),
            ("retry_effect_key", "invoice:OTHER"),
        ):
            with self.subTest(field=field):
                case = valid_case()
                case["integration"][field] = value
                self.assertEqual(
                    m.evaluate_invoice_case(
                        case, extraction_threshold_basis_points=9_900
                    )["disposition"],
                    "HOLD_INTEGRATION",
                )

    def test_duplicate_effect_count_holds(self):
        case = valid_case()
        case["integration"]["effect_count"] = 2
        self.assertEqual(
            m.evaluate_invoice_case(
                case, extraction_threshold_basis_points=9_900
            )["disposition"],
            "HOLD_INTEGRATION",
        )


if __name__ == "__main__":
    unittest.main()
