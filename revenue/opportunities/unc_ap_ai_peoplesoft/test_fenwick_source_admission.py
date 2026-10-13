"""Source and request correlation coverage; all positive fixtures are synthetic."""
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import unc_ap_ai as facade
import unc_ap_ai_v2 as m
from test_cairn_batch_identity import source, invoice, AT


class TestCompiler(unittest.TestCase):
    def test_public_source_is_fail_closed(self):
        result = facade.compile_source({})
        self.assertIn(result["state"], {"HOLD_SOURCE_BYTES", "HOLD_DEADLINE"})
        self.assertTrue(all(v is False for v in result["authority"].values()))

    def test_public_source_cannot_accept_caller_clock(self):
        with self.assertRaises(TypeError):
            facade.compile_source({}, as_of=AT)

    def test_fixture_manifest_positive_control(self):
        ledger, docs = source()
        result = m._compile_source_at(ledger, docs, as_of=AT)
        self.assertEqual(result["state"], "SOURCE_BOUND")
        self.assertEqual(result["computed_documents"], ledger["required_documents"])
        self.assertTrue(all(v is False for v in result["authority"].values()))

    def test_missing_document(self):
        ledger, _ = source()
        self.assertEqual(m._compile_source_at(ledger, {}, as_of=AT)["state"], "HOLD_SOURCE_BYTES")

    def test_extra_document(self):
        ledger, docs = source(); docs["extra.txt"] = b"synthetic extra"
        self.assertEqual(m._compile_source_at(ledger, docs, as_of=AT)["state"], "HOLD_SOURCE_BYTES")

    def test_changed_document(self):
        ledger, docs = source(); docs["fixture.txt"] = b"different synthetic bytes"
        self.assertEqual(m._compile_source_at(ledger, docs, as_of=AT)["state"], "HOLD_SOURCE_BYTES")

    def test_empty_manifest(self):
        ledger, docs = source(); ledger["required_documents"] = []
        with self.assertRaises(m.ContractError): m._compile_source_at(ledger, docs, as_of=AT)

    def test_unbound_generation(self):
        ledger, docs = source(); ledger["source_generation"] = "a" * 64
        with self.assertRaises(m.ContractError): m._compile_source_at(ledger, docs, as_of=AT)

    def test_path_traversal_document_name(self):
        ledger, docs = source(); ledger["required_documents"][0]["name"] = "../fixture.txt"
        with self.assertRaises(m.ContractError): m._compile_source_at(ledger, docs, as_of=AT)

    def test_duplicate_manifest_name(self):
        ledger, docs = source(); ledger["required_documents"] *= 2
        with self.assertRaises(m.ContractError): m._compile_source_at(ledger, docs, as_of=AT)

    def test_document_values_must_be_bytes(self):
        ledger, docs = source(); docs["fixture.txt"] = "synthetic text rather than exact bytes"
        with self.assertRaises(m.ContractError): m._compile_source_at(ledger, docs, as_of=AT)

    def test_excessive_document_count(self):
        ledger, _ = source(); docs = {f"f{n}.txt": b"x" for n in range(65)}
        with self.assertRaises(m.ContractError): m._compile_source_at(ledger, docs, as_of=AT)

    def test_deadline_exact_boundary(self):
        ledger, docs = source(); when = datetime(2026, 9, 25, 16, tzinfo=timezone.utc)
        self.assertEqual(m._compile_source_at(ledger, docs, as_of=when)["state"], "HOLD_DEADLINE")

    def test_time_before_observation(self):
        ledger, docs = source(); when = datetime(2026, 9, 17, tzinfo=timezone.utc)
        with self.assertRaises(m.ContractError): m._compile_source_at(ledger, docs, as_of=when)

    def test_closed_source(self):
        ledger, docs = source(); ledger["status"] = "CLOSED"
        self.assertEqual(m._compile_source_at(ledger, docs, as_of=AT)["state"], "HOLD_NOT_OPEN")

    def test_caller_documents_do_not_replace_fixed_ledger(self):
        _, docs = source()
        self.assertIn(facade.compile_source(docs)["state"], {"HOLD_SOURCE_BYTES", "HOLD_DEADLINE"})

    def test_legacy_flags_cannot_promote_readiness(self):
        value = json.loads(Path(m.__file__).with_name("source_ledger.json").read_text())
        for field, forged in (("exact_current_bytes_sha256", "a" * 64), ("addenda_complete", True)):
            changed = dict(value); changed[field] = forged
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "ledger.json"; path.write_text(json.dumps(changed))
                with patch.object(m, "_SOURCE_LEDGER_PATH", path), self.assertRaises(m.ContractError):
                    m.load_source_ledger()

    def test_duplicate_and_float_json_rejected(self):
        for raw in ('{"x":1,"x":2}', '{"x":1.0}', '{"x":NaN}'):
            with self.assertRaises(m.ContractError): m.load_strict_json(raw)

    def test_old_request_for_new_amount_fails(self):
        row = invoice()
        for field in ("expected_amount_cents", "extracted_amount_cents", "purchase_order_amount_cents", "receipt_amount_cents"):
            row[field] += 1
        self.assertEqual(m.evaluate_invoice_case(row, extraction_threshold_basis_points=9900)["disposition"], "HOLD_INTEGRATION")

    def test_other_invoice_evidence_fails(self):
        row = invoice(); row["integration"] = invoice("OTHER")["integration"]
        self.assertEqual(m.evaluate_invoice_case(row, extraction_threshold_basis_points=9900)["disposition"], "HOLD_INTEGRATION")

    def test_ack_digest_fails(self):
        row = invoice(); row["integration"]["ack_sha256"] = "0" * 64
        self.assertEqual(m.evaluate_invoice_case(row, extraction_threshold_basis_points=9900)["disposition"], "HOLD_INTEGRATION")

    def test_wrong_retry_effect_fails(self):
        row = invoice(); row["integration"]["retry_effect_key"] = "different"
        self.assertEqual(m.evaluate_invoice_case(row, extraction_threshold_basis_points=9900)["disposition"], "HOLD_INTEGRATION")

    def test_boolean_effect_count_rejected(self):
        row = invoice(); row["integration"]["effect_count"] = True
        with self.assertRaises(m.ContractError): m.evaluate_invoice_case(row, extraction_threshold_basis_points=9900)


if __name__ == "__main__":
    unittest.main()
