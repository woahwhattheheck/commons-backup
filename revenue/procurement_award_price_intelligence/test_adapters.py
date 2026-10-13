from __future__ import annotations

import copy
import json
import unittest
from unittest.mock import patch

from revenue.procurement_award_price_intelligence import adapters
from revenue.procurement_award_price_intelligence import engine


MWRD_HTML = b"""<!doctype html><html><body>
<div>File #: 26-0350   Version: 1</div>
<div>Final action: 5/21/2026</div>
<div>Title: Authority to award Contract 26-025-1H, Furnish and Deliver Stem Gate Valves to Various Locations, to Porter Pipe &amp; Supply Company, in an amount not to exceed $94,191.14, Account 101-20000-623090</div>
<div>Attachments:</div>
</body></html>"""

CORAL_HTML = b"""<!doctype html><html><body>
<div>File #: 26-1459 Version: 1</div>
<div>Final action: 5/5/2026</div>
<div>Title: A Resolution of the City Commission accepting the recommendation of the Chief Procurement Officer to award the Sanitary Sewer Submersible Electrical Control Panel Installation to Coreland Construction Corp., the most responsive and responsible bidder in the estimated amount of $829,898.94, pursuant to Section 2-763 of the Procurement Code.</div>
<div>Attachments:</div>
</body></html>"""

PDF_BYTES = b"%PDF-1.7\n% buyer-hosted tabulation fixture bytes\n"
PDF_BYTES_CHANGED = b"%PDF-1.7\n% buyer-hosted tabulation fixture bytes changed\n"
FIXED_NOW = "2026-09-16T20:30:00Z"


def base_request(profile="LEGISTAR_AWARD_HTML_V1"):
    if profile == "LEGISTAR_AWARD_HTML_V1":
        uri = "https://mwrd.legistar.com/LegislationDetail.aspx?GUID=abc&ID=123"
        extraction = {"mode": "LIVE_HTML", "state": "EXACT", "coverage": "COMPLETE_RECORD"}
        records = []
        allowed = ["AWARD"]
    else:
        uri = "https://www.cityofcoweta-ok.gov/DocumentCenter/View/2084/260427-Bid-Tab-PDF?bidId="
        extraction = {"mode": "TABULAR_PDF_TEXT", "state": "REVIEWED", "coverage": "COMPLETE_TABLE"}
        records = [
            {
                "record_id": "coweta-2026-tower-bright-lighting",
                "claim_key": "coweta-2026-radio-tower:bright-lighting",
                "opportunity_id": "coweta-pd-radio-tower-2026",
                "vendor": "Bright Lighting",
                "amount_minor": 7525000,
                "currency": "USD",
                "basis": "CONTRACT_TOTAL",
                "unit": None,
                "term_months": None,
                "event_date": "2026-04-22",
                "disposition": "INCLUDED_BY_SOURCE",
            },
            {
                "record_id": "coweta-2026-tower-globenet",
                "claim_key": "coweta-2026-radio-tower:globenet",
                "opportunity_id": "coweta-pd-radio-tower-2026",
                "vendor": "Globenet Telecommunications",
                "amount_minor": 10086736,
                "currency": "USD",
                "basis": "CONTRACT_TOTAL",
                "unit": None,
                "term_months": None,
                "event_date": "2026-04-22",
                "disposition": "INCLUDED_BY_SOURCE",
            },
        ]
        allowed = ["BID"]
    return {
        "schema": adapters.ADAPTER_INPUT,
        "dataset_id": "adapter-test",
        "max_source_age_seconds": 86400,
        "truth_boundary": adapters.TRUTH_BOUNDARY,
        "source": {"profile": profile, "uri": uri},
        "lineage": {"relation": "ORIGINAL", "sequence": 0, "parent_source_sha256": None},
        "extraction": extraction,
        "records": records,
        "target": {
            "target_id": "target",
            "currency": "USD",
            "basis": "CONTRACT_TOTAL",
            "unit": None,
            "term_months": None,
            "allowed_price_kinds": allowed,
        },
    }


def raw(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


class AdapterTests(unittest.TestCase):
    def compile_with(self, request, body, content_type, final_uri=None):
        source_uri = request["source"]["uri"]
        final_uri = final_uri or source_uri
        with patch.object(
            adapters,
            "_fetch_https",
            return_value=(body, final_uri, content_type),
        ), patch.object(adapters, "_now_utc", return_value=FIXED_NOW):
            return adapters.compile_adapter(raw(request))

    def test_legistar_live_fetch_compiles_buyer_official_ready(self):
        request = base_request()
        normalized_bytes, receipt_bytes = self.compile_with(request, MWRD_HTML, "text/html")
        normalized = json.loads(normalized_bytes)
        receipt = json.loads(receipt_bytes)
        self.assertEqual(normalized["sources"][0]["authority"], "BUYER_OFFICIAL")
        self.assertEqual(normalized["sources"][0]["source_class"], "BOARD_AWARD")
        self.assertEqual(normalized["sources"][0]["sha256"], engine.digest(MWRD_HTML))
        self.assertEqual(normalized["observations"][0]["vendor"], "Porter Pipe & Supply Company")
        self.assertEqual(normalized["observations"][0]["amount_minor"], 9419114)
        self.assertEqual(normalized["observations"][0]["event_date"], "2026-05-21")
        self.assertEqual(receipt["source_authentication"], "LIVE_HTTPS_FETCH_CODE_OWNED_BUYER_HOST_ALLOWLIST")
        self.assertTrue(all(value is False for value in receipt["authority"].values()))
        packet, _, _ = engine.compile(normalized_bytes)
        self.assertEqual(json.loads(packet)["status"], "PRICE_EVIDENCE_READY")

    def test_coral_gables_estimated_award_title_parses(self):
        request = base_request()
        request["source"]["uri"] = "https://coralgables.legistar.com/LegislationDetail.aspx?GUID=abc&ID=7996401"
        normalized_bytes, _ = self.compile_with(request, CORAL_HTML, "text/html")
        observation = json.loads(normalized_bytes)["observations"][0]
        self.assertEqual(observation["vendor"], "Coreland Construction Corp.")
        self.assertEqual(observation["amount_minor"], 82989894)
        self.assertEqual(observation["event_date"], "2026-05-05")

    def test_legistar_records_must_be_code_derived(self):
        request = base_request()
        request["records"] = [base_request("BUYER_BID_TABULATION_PDF_V1")["records"][0]]
        with self.assertRaises(adapters.AdapterError):
            adapters._decode_request(raw(request))

    def test_pdf_reviewed_rows_bind_live_document_hash(self):
        request = base_request("BUYER_BID_TABULATION_PDF_V1")
        normalized_bytes, receipt_bytes = self.compile_with(request, PDF_BYTES, "application/pdf")
        normalized = json.loads(normalized_bytes)
        receipt = json.loads(receipt_bytes)
        self.assertEqual(receipt["extraction"]["method"], "HUMAN_REVIEWED_ROWS_BOUND_TO_LIVE_HTTPS_DOCUMENT_SHA256")
        self.assertEqual(receipt["source_sha256"], engine.digest(PDF_BYTES))
        self.assertEqual(len(normalized["observations"]), 2)
        packet, _, _ = engine.compile(normalized_bytes)
        self.assertEqual(json.loads(packet)["status"], "PRICE_EVIDENCE_READY")

    def test_pdf_ocr_is_hold_and_rows_cannot_promote(self):
        request = base_request("BUYER_BID_TABULATION_PDF_V1")
        request["extraction"] = {"mode": "OCR", "state": "REVIEWED", "coverage": "UNKNOWN"}
        normalized_bytes, receipt_bytes = self.compile_with(request, PDF_BYTES, "application/pdf")
        normalized = json.loads(normalized_bytes)
        receipt = json.loads(receipt_bytes)
        self.assertEqual(receipt["status"], "HOLD_AMBIGUOUS_EXTRACTION")
        self.assertEqual(receipt["observation_count"], 0)
        self.assertEqual(len(receipt["held_record_ids"]), 2)
        self.assertEqual(normalized["observations"], [])
        packet, _, _ = engine.compile(normalized_bytes)
        self.assertEqual(json.loads(packet)["status"], "HOLD_NO_HISTORY")

    def test_pdf_ambiguous_text_is_hold(self):
        request = base_request("BUYER_BID_TABULATION_PDF_V1")
        request["extraction"] = {"mode": "TABULAR_PDF_TEXT", "state": "AMBIGUOUS", "coverage": "UNKNOWN"}
        _, receipt_bytes = self.compile_with(request, PDF_BYTES, "application/pdf")
        self.assertEqual(json.loads(receipt_bytes)["status"], "HOLD_AMBIGUOUS_EXTRACTION")

    def test_held_rows_still_require_typed_money(self):
        request = base_request("BUYER_BID_TABULATION_PDF_V1")
        request["extraction"] = {"mode": "OCR", "state": "AMBIGUOUS", "coverage": "UNKNOWN"}
        request["records"][0]["amount_minor"] = True
        with self.assertRaises(adapters.AdapterError):
            self.compile_with(request, PDF_BYTES, "application/pdf")

    def test_partial_pdf_coverage_holds_entire_range(self):
        request = base_request("BUYER_BID_TABULATION_PDF_V1")
        request["extraction"]["coverage"] = "PARTIAL"
        normalized_bytes, receipt_bytes = self.compile_with(request, PDF_BYTES, "application/pdf")
        self.assertEqual(json.loads(normalized_bytes)["observations"], [])
        receipt = json.loads(receipt_bytes)
        self.assertEqual(receipt["status"], "HOLD_AMBIGUOUS_EXTRACTION")
        self.assertIn("partial", receipt["hold_reason"].lower())

    def test_source_rejected_bid_is_excluded_not_promoted(self):
        request = base_request("BUYER_BID_TABULATION_PDF_V1")
        request["records"][1]["disposition"] = "REJECTED_BY_SOURCE"
        normalized_bytes, receipt_bytes = self.compile_with(request, PDF_BYTES, "application/pdf")
        normalized = json.loads(normalized_bytes)
        receipt = json.loads(receipt_bytes)
        self.assertEqual(len(normalized["observations"]), 1)
        self.assertEqual(receipt["excluded_record_ids"], ["coweta-2026-tower-globenet"])

    def test_unknown_bid_disposition_holds_entire_table(self):
        request = base_request("BUYER_BID_TABULATION_PDF_V1")
        request["records"][1]["disposition"] = "UNKNOWN"
        normalized_bytes, receipt_bytes = self.compile_with(request, PDF_BYTES, "application/pdf")
        self.assertEqual(json.loads(normalized_bytes)["observations"], [])
        receipt = json.loads(receipt_bytes)
        self.assertEqual(receipt["status"], "HOLD_AMBIGUOUS_EXTRACTION")
        self.assertIn("UNKNOWN", receipt["hold_reason"])

    def test_option_lineage_never_promotes_as_base_bid(self):
        request = base_request("BUYER_BID_TABULATION_PDF_V1")
        request["lineage"] = {"relation": "OPTION", "sequence": 1, "parent_source_sha256": "a" * 64}
        normalized_bytes, _ = self.compile_with(request, PDF_BYTES, "application/pdf")
        normalized = json.loads(normalized_bytes)
        self.assertEqual({row["price_kind"] for row in normalized["observations"]}, {"OPTION"})
        packet, _, _ = engine.compile(normalized_bytes)
        self.assertEqual(json.loads(packet)["status"], "HOLD_NO_HISTORY")

    def test_renewal_lineage_never_promotes_as_base_bid(self):
        request = base_request("BUYER_BID_TABULATION_PDF_V1")
        request["lineage"] = {"relation": "RENEWAL", "sequence": 2, "parent_source_sha256": "b" * 64}
        normalized_bytes, _ = self.compile_with(request, PDF_BYTES, "application/pdf")
        self.assertEqual({row["price_kind"] for row in json.loads(normalized_bytes)["observations"]}, {"RENEWAL"})

    def test_amendment_lineage_is_source_class_amendment(self):
        request = base_request("BUYER_BID_TABULATION_PDF_V1")
        request["lineage"] = {"relation": "AMENDMENT", "sequence": 1, "parent_source_sha256": "c" * 64}
        normalized_bytes, _ = self.compile_with(request, PDF_BYTES, "application/pdf")
        self.assertEqual(json.loads(normalized_bytes)["sources"][0]["source_class"], "AMENDMENT")

    def test_unknown_host_rejected_before_fetch(self):
        request = base_request()
        request["source"]["uri"] = "https://example.com/LegislationDetail.aspx?ID=1"
        with self.assertRaises(adapters.AdapterError):
            adapters._decode_request(raw(request))

    def test_redirect_to_unapproved_host_rejected(self):
        request = base_request()
        with self.assertRaises(adapters.AdapterError):
            self.compile_with(request, MWRD_HTML, "text/html", final_uri="https://example.com/redirected")

    def test_content_type_mismatch_rejected(self):
        request = base_request()
        with self.assertRaises(adapters.AdapterError):
            self.compile_with(request, MWRD_HTML, "application/pdf")

    def test_pdf_magic_required(self):
        request = base_request("BUYER_BID_TABULATION_PDF_V1")
        with self.assertRaises(adapters.AdapterError):
            self.compile_with(request, b"not-a-pdf", "application/pdf")

    def test_duplicate_record_id_rejected(self):
        request = base_request("BUYER_BID_TABULATION_PDF_V1")
        request["records"][1]["record_id"] = request["records"][0]["record_id"]
        with self.assertRaises(adapters.AdapterError):
            self.compile_with(request, PDF_BYTES, "application/pdf")

    def test_duplicate_json_key_rejected(self):
        malformed = (
            b'{"schema":"procurement-award-source-adapters/input/v1",'
            b'"schema":"procurement-award-source-adapters/input/v1"}'
        )
        with self.assertRaises(adapters.AdapterError):
            adapters._decode_request(malformed)

    def test_source_byte_drift_invalidates_verification(self):
        request = base_request("BUYER_BID_TABULATION_PDF_V1")
        normalized_bytes, receipt_bytes = self.compile_with(request, PDF_BYTES, "application/pdf")
        with patch.object(adapters, "_fetch_https", return_value=(PDF_BYTES_CHANGED, request["source"]["uri"], "application/pdf")):
            with self.assertRaises(adapters.AdapterError):
                adapters.verify_adapter(raw(request), normalized_bytes, receipt_bytes)

    def test_verify_succeeds_when_live_source_bytes_match(self):
        request = base_request("BUYER_BID_TABULATION_PDF_V1")
        normalized_bytes, receipt_bytes = self.compile_with(request, PDF_BYTES, "application/pdf")
        with patch.object(adapters, "_fetch_https", return_value=(PDF_BYTES, request["source"]["uri"], "application/pdf")):
            self.assertTrue(adapters.verify_adapter(raw(request), normalized_bytes, receipt_bytes))

    def test_tampered_normalized_output_fails_verification(self):
        request = base_request("BUYER_BID_TABULATION_PDF_V1")
        normalized_bytes, receipt_bytes = self.compile_with(request, PDF_BYTES, "application/pdf")
        tampered = normalized_bytes.replace(b"Bright Lighting", b"Bright LightinG")
        with patch.object(adapters, "_fetch_https", return_value=(PDF_BYTES, request["source"]["uri"], "application/pdf")):
            with self.assertRaises(adapters.AdapterError):
                adapters.verify_adapter(raw(request), tampered, receipt_bytes)

    def test_future_receipt_capture_time_rejected(self):
        request = base_request("BUYER_BID_TABULATION_PDF_V1")
        normalized_bytes, receipt_bytes = self.compile_with(request, PDF_BYTES, "application/pdf")
        receipt = json.loads(receipt_bytes)
        receipt["captured_at"] = "2099-01-01T00:00:00Z"
        future_receipt = engine.canon(receipt)
        with patch.object(adapters, "_fetch_https", return_value=(PDF_BYTES, request["source"]["uri"], "application/pdf")):
            with self.assertRaises(adapters.AdapterError):
                adapters.verify_adapter(raw(request), normalized_bytes, future_receipt)

    def test_target_bool_or_float_money_cannot_enter_engine_schema(self):
        request = base_request("BUYER_BID_TABULATION_PDF_V1")
        request["records"][0]["amount_minor"] = 1.25
        with self.assertRaises((adapters.AdapterError, engine.Error)):
            self.compile_with(request, PDF_BYTES, "application/pdf")


if __name__ == "__main__":
    unittest.main()
