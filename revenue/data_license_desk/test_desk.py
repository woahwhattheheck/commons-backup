from __future__ import annotations

import copy
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from revenue.data_license_desk.cli import main
from revenue.data_license_desk.desk import (
    HOLD,
    READY,
    DataLicenseError,
    build_catalog,
    canonical_json,
    sha256,
    verify_catalog,
)

H = "a" * 64
NOW = "2026-09-13T10:00:00Z"

def build(doc):
    return build_catalog(doc, NOW)

def verify(doc, receipt, packs, at=NOW):
    return verify_catalog(doc, receipt, packs, at)

def base_doc():
    return {
        "schema": "commons-data-license/v1",
        "evaluated_at": "2026-09-13T10:00:00Z",
        "datasets": [{
            "dataset_id": "public-receipt-corpus",
            "version": "2026.09.13",
            "source_sha256": "1" * 64,
            "provenance_sha256": "2" * 64,
            "rights": {
                "basis": "OWNED",
                "license_id": "TJL-Data-1.0",
                "license_evidence_sha256": "3" * 64,
                "permitted_grants": ["EVALUATION", "INTERNAL_USE"],
                "transfer_allowed": True,
            },
            "sensitive_class": "REDACTED",
            "redaction": {
                "status": "VERIFIED",
                "policy_sha256": "4" * 64,
                "review_evidence_sha256": "5" * 64,
                "reviewed_at": "2026-09-13T09:00:00Z",
            },
            "schema_fields": ["event_id", "latency_ms", "outcome"],
            "sample_rows": [
                {"event_id": "evt-001", "latency_ms": 12.5, "outcome": "PASS"},
                {"event_id": "evt-002", "latency_ms": 15, "outcome": "HOLD"},
            ],
            "offer": {
                "currency": "USD",
                "price_cents": 250000,
                "grant": "EVALUATION",
                "term_days": 30,
                "expires_at": "2026-10-13T10:00:00Z",
            },
        }],
    }

class DeskTests(unittest.TestCase):
    def test_ready_pack_is_deterministic_and_verified(self):
        doc = base_doc()
        receipt1, packs1 = build(doc)
        receipt2, packs2 = build(copy.deepcopy(doc))
        self.assertEqual(READY, receipt1["decision"])
        self.assertEqual(canonical_json(receipt1), canonical_json(receipt2))
        self.assertEqual(packs1, packs2)
        self.assertTrue(verify(doc, receipt1, packs1))
        self.assertFalse(receipt1["authority"]["license_executed"])
        payload = packs1["public-receipt-corpus"]
        self.assertEqual(receipt1["datasets"][0]["sample_pack_sha256"], sha256(payload))
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            self.assertEqual(["OFFER.md", "manifest.json", "sample.jsonl"], sorted(zf.namelist()))
            self.assertIn("READY FOR HUMAN LICENSE REVIEW", zf.read("OFFER.md").decode())
            self.assertIn("$2500.00 USD", zf.read("OFFER.md").decode())
            for info in zf.infolist():
                self.assertEqual((1980, 1, 1, 0, 0, 0), info.date_time)

    def test_unknown_rights_holds_and_emits_no_pack(self):
        doc = base_doc()
        doc["datasets"][0]["rights"]["basis"] = "UNKNOWN"
        receipt, packs = build(doc)
        self.assertEqual(HOLD, receipt["decision"])
        self.assertIn("RIGHTS_BASIS_NOT_TRANSFERABLE_OR_UNKNOWN", receipt["datasets"][0]["reasons"])
        self.assertEqual({}, packs)

    def test_restricted_rights_holds(self):
        doc = base_doc()
        doc["datasets"][0]["rights"]["basis"] = "THIRD_PARTY_RESTRICTED"
        self.assertEqual(HOLD, build(doc)[0]["decision"])

    def test_transfer_flag_required(self):
        doc = base_doc()
        doc["datasets"][0]["rights"]["transfer_allowed"] = False
        row = build(doc)[0]["datasets"][0]
        self.assertIn("TRANSFER_NOT_RECORDED_ALLOWED", row["reasons"])

    def test_offer_grant_must_be_permitted(self):
        doc = base_doc()
        doc["datasets"][0]["offer"]["grant"] = "COMMERCIAL_USE"
        row = build(doc)[0]["datasets"][0]
        self.assertIn("OFFER_GRANT_NOT_PERMITTED_BY_RIGHTS", row["reasons"])

    def test_unknown_sensitive_class_holds(self):
        doc = base_doc()
        doc["datasets"][0]["sensitive_class"] = "UNKNOWN"
        row = build(doc)[0]["datasets"][0]
        self.assertIn("SENSITIVE_CLASS_NOT_PUBLIC_OR_REDACTED", row["reasons"])

    def test_redacted_requires_verified_review(self):
        doc = base_doc()
        doc["datasets"][0]["redaction"]["status"] = "PENDING"
        row = build(doc)[0]["datasets"][0]
        self.assertIn("REDACTION_NOT_VERIFIED", row["reasons"])

    def test_future_redaction_review_holds(self):
        doc = base_doc()
        doc["datasets"][0]["redaction"]["reviewed_at"] = "2026-09-14T09:00:00Z"
        row = build(doc)[0]["datasets"][0]
        self.assertIn("REDACTION_REVIEW_IN_FUTURE", row["reasons"])

    def test_pii_shaped_field_holds(self):
        doc = base_doc()
        doc["datasets"][0]["schema_fields"].append("customer_email")
        row = build(doc)[0]["datasets"][0]
        self.assertIn("PII_OR_SECRET_SHAPED_FIELD", row["reasons"])

    def test_email_value_fails_closed(self):
        doc = base_doc()
        doc["datasets"][0]["sample_rows"][0]["outcome"] = "a@example.com"
        row = build(doc)[0]["datasets"][0]
        self.assertTrue(row["reasons"][0].startswith("MALFORMED:"))

    def test_secret_value_fails_closed(self):
        doc = base_doc()
        doc["datasets"][0]["sample_rows"][0]["outcome"] = "Bearer abcdefghijklmnop"
        row = build(doc)[0]["datasets"][0]
        self.assertTrue(row["reasons"][0].startswith("MALFORMED:"))

    def test_unknown_sample_field_holds(self):
        doc = base_doc()
        doc["datasets"][0]["sample_rows"][0]["extra"] = "x"
        row = build(doc)[0]["datasets"][0]
        self.assertIn("SAMPLE_FIELD_OUTSIDE_SCHEMA", row["reasons"])

    def test_nonfinite_sample_rejected(self):
        doc = base_doc()
        doc["datasets"][0]["sample_rows"][0]["latency_ms"] = float("inf")
        row = build(doc)[0]["datasets"][0]
        self.assertTrue(row["reasons"][0].startswith("MALFORMED:"))

    def test_expired_offer_holds(self):
        doc = base_doc()
        doc["datasets"][0]["offer"]["expires_at"] = "2026-09-13T09:59:59Z"
        row = build(doc)[0]["datasets"][0]
        self.assertIn("OFFER_EXPIRED", row["reasons"])

    def test_money_is_exact_at_large_integer_boundary(self):
        doc = base_doc()
        doc["datasets"][0]["offer"]["price_cents"] = 9_000_000_000_000_001
        receipt, packs = build(doc)
        self.assertEqual(HOLD, receipt["decision"])
        self.assertEqual({}, packs)
        self.assertIn("safe-range", receipt["datasets"][0]["reasons"][0])

    def test_bool_price_rejected(self):
        doc = base_doc()
        doc["datasets"][0]["offer"]["price_cents"] = True
        row = build(doc)[0]["datasets"][0]
        self.assertTrue(row["reasons"][0].startswith("MALFORMED:"))

    def test_duplicate_dataset_id_rejected(self):
        doc = base_doc()
        doc["datasets"].append(copy.deepcopy(doc["datasets"][0]))
        with self.assertRaises(DataLicenseError):
            build(doc)

    def test_receipt_mutation_fails_verification(self):
        doc = base_doc()
        receipt, packs = build(doc)
        receipt = copy.deepcopy(receipt)
        receipt["datasets"][0]["offer"]["price_cents"] += 1
        self.assertFalse(verify(doc, receipt, packs))

    def test_pack_mutation_fails_verification(self):
        doc = base_doc()
        receipt, packs = build(doc)
        bad = dict(packs)
        bad["public-receipt-corpus"] += b"x"
        self.assertFalse(verify(doc, receipt, bad))

    def test_missing_pack_fails_verification(self):
        doc = base_doc()
        receipt, _ = build(doc)
        self.assertFalse(verify(doc, receipt, {}))

    def test_extra_pack_fails_verification(self):
        doc = base_doc()
        receipt, packs = build(doc)
        packs = dict(packs)
        packs["extra"] = b"x"
        self.assertFalse(verify(doc, receipt, packs))

    def test_public_data_can_mark_redaction_not_required(self):
        doc = base_doc()
        ds = doc["datasets"][0]
        ds["sensitive_class"] = "PUBLIC"
        ds["redaction"] = {"status": "NOT_REQUIRED"}
        self.assertEqual(READY, build(doc)[0]["decision"])

    def test_cli_build_verify_and_symlink_input_refusal(self):
        doc = base_doc()
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            inp = td / "input.json"
            inp.write_bytes(canonical_json(doc))
            receipt = td / "receipt.json"
            packs = td / "packs"
            self.assertEqual(0, main(["build", str(inp), "--receipt", str(receipt), "--pack-dir", str(packs), "--at", NOW]))
            self.assertEqual(0, main(["verify", str(inp), "--receipt", str(receipt), "--pack-dir", str(packs), "--at", NOW]))
            link = td / "link.json"
            try:
                link.symlink_to(inp)
            except OSError:
                self.skipTest("symlink unavailable")
            self.assertEqual(2, main(["build", str(link), "--receipt", str(td/"x"), "--pack-dir", str(td/"p"), "--at", NOW]))

    def test_cli_hold_returns_three_and_no_pack(self):
        doc = base_doc()
        doc["datasets"][0]["rights"]["basis"] = "UNKNOWN"
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            inp = td / "input.json"
            inp.write_bytes(canonical_json(doc))
            receipt = td / "receipt.json"
            packs = td / "packs"
            self.assertEqual(3, main(["build", str(inp), "--receipt", str(receipt), "--pack-dir", str(packs), "--at", NOW]))
            self.assertTrue(receipt.exists())
            self.assertFalse((packs / "public-receipt-corpus.zip").exists())

    def test_hold_receipt_does_not_invent_transfer_permission(self):
        doc = base_doc()
        doc["datasets"][0]["rights"]["transfer_allowed"] = False
        row = build(doc)[0]["datasets"][0]
        self.assertFalse(row["rights"]["transfer_allowed"])
        self.assertEqual(HOLD, row["status"])

    def test_public_data_must_use_not_required_redaction_state(self):
        doc = base_doc()
        ds = doc["datasets"][0]
        ds["sensitive_class"] = "PUBLIC"
        ds["redaction"]["status"] = "VERIFIED"
        row = build(doc)[0]["datasets"][0]
        self.assertIn("PUBLIC_DATA_REDACTION_STATUS_INVALID", row["reasons"])

    def test_verification_uses_external_trusted_time(self):
        doc = base_doc()
        receipt, packs = build(doc)
        self.assertTrue(verify(doc, receipt, packs))
        self.assertFalse(verify(doc, receipt, packs, "2026-10-14T10:00:00Z"))

    def test_empty_sample_pack_is_not_ready(self):
        doc = base_doc()
        doc["datasets"][0]["sample_rows"] = []
        row = build(doc)[0]["datasets"][0]
        self.assertTrue(row["reasons"][0].startswith("MALFORMED:"))

if __name__ == "__main__":
    unittest.main()
