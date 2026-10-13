from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from revenue.procurement_award_price_intelligence.source_adapters import (
    Error, REQUEST, TRUTH, canon, compile, load, verify,
)


def raw(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def payload_sha(value):
    return hashlib.sha256(canon(value)).hexdigest()


def source(source_id="s1", source_class="AWARD_NOTICE", authority="BUYER_OFFICIAL"):
    return {
        "source_id": source_id,
        "uri": f"https://buyer.example.gov/{source_id}",
        "sha256": "a" * 64,
        "observed_at": "2026-09-16T00:00:00Z",
        "authority": authority,
        "source_class": source_class,
        "title": "Official source",
    }


def target():
    return {
        "target_id": "t1", "currency": "USD", "basis": "CONTRACT_TOTAL",
        "unit": None, "term_months": 12, "allowed_price_kinds": ["AWARD", "BID"],
    }


def request(documents):
    return {
        "schema": REQUEST, "dataset_id": "d1", "generated_at": "2026-09-16T01:00:00Z",
        "max_source_age_seconds": 86400, "truth_boundary": TRUTH,
        "documents": documents, "target": target(),
    }


def document(adapter, payload, source_class, authority="BUYER_OFFICIAL", source_id="s1"):
    return {
        "adapter": adapter,
        "source": source(source_id, source_class, authority),
        "payload_sha256": payload_sha(payload),
        "payload": payload,
    }


def award():
    return {
        "opportunity_id": "opp1", "award_id": "a1", "vendor": "Vendor LLC",
        "award_amount_minor": 123400, "currency": "USD", "basis": "CONTRACT_TOTAL",
        "unit": None, "term_months": 12, "award_date": "2026-09-15",
    }


def bid():
    return {
        "opportunity_id": "opp1", "tabulation_id": "tab1", "currency": "USD",
        "basis": "CONTRACT_TOTAL", "unit": None, "term_months": 12,
        "bid_date": "2026-09-14",
        "rows": [
            {"row_id": "r1", "vendor": "A LLC", "bid_amount_minor": 111100, "responsive": True},
            {"row_id": "r2", "vendor": "B LLC", "bid_amount_minor": None, "responsive": True},
            {"row_id": "r3", "vendor": "C LLC", "bid_amount_minor": 99900, "responsive": False},
        ],
    }


def contract():
    return {
        "opportunity_id": "opp1", "contract_id": "c1", "vendor": "Winner LLC",
        "currency": "USD", "base_amount_minor": 200000, "basis": "CONTRACT_TOTAL",
        "unit": None, "term_months": 12, "effective_date": "2026-09-15",
        "option_amount_minor": 50000, "option_term_months": 6,
    }


def amendment():
    return {
        "opportunity_id": "opp1", "contract_id": "c1", "amendment_id": "m1",
        "vendor": "Winner LLC", "currency": "USD", "amount_minor": 25000,
        "term_months": 3, "effective_date": "2026-09-16", "change_type": "AMENDMENT",
    }


class SourceAdapterTests(unittest.TestCase):
    def compile_doc(self, doc):
        return tuple(json.loads(part) for part in compile(raw(request([doc]))))

    def test_award_ready_and_canonical_origin(self):
        doc = document("AWARD_NOTICE_JSON_V1", award(), "AWARD_NOTICE")
        doc["source"]["uri"] = "https://BUYER.Example.GOV:443/private/path"
        price, packet, receipt = self.compile_doc(doc)
        self.assertEqual("AWARD", price["observations"][0]["price_kind"])
        self.assertEqual("PRICE_EVIDENCE_READY", packet["price_engine_status"])
        self.assertEqual("https://buyer.example.gov", price["sources"][0]["uri"])
        locator_sha = hashlib.sha256(doc["source"]["uri"].encode()).hexdigest()
        self.assertEqual(locator_sha, packet["source_audit"][0]["source_locator_sha256"])
        self.assertEqual(
            [{"source_id": "s1", "sha256": locator_sha}],
            receipt["source_locator_sha256s"],
        )

    def test_board_award_allowed(self):
        price, _, _ = self.compile_doc(document("AWARD_NOTICE_JSON_V1", award(), "BOARD_AWARD"))
        self.assertEqual(1, len(price["observations"]))

    def test_bid_holds_ambiguous_and_nonresponsive_rows(self):
        price, packet, _ = self.compile_doc(document("BID_TABULATION_JSON_V1", bid(), "BID_TABULATION"))
        self.assertEqual(1, len(price["observations"]))
        self.assertEqual(
            {"AMBIGUOUS_AMOUNT", "NONRESPONSIVE_BID_EXCLUDED"},
            {row["code"] for row in packet["holds"]},
        )

    def test_contract_separates_option(self):
        price, packet, _ = self.compile_doc(document("EXECUTED_CONTRACT_JSON_V1", contract(), "EXECUTED_CONTRACT"))
        self.assertEqual(["AWARD", "OPTION"], sorted(row["price_kind"] for row in price["observations"]))
        self.assertIn("OPTION_NON_ANCHOR", {row["code"] for row in packet["holds"]})

    def test_amendment_never_becomes_award(self):
        price, packet, _ = self.compile_doc(document("AMENDMENT_OPTION_JSON_V1", amendment(), "AMENDMENT"))
        self.assertEqual("OPTION", price["observations"][0]["price_kind"])
        self.assertIn("CHANGE_RECORD_NON_ANCHOR", {row["code"] for row in packet["holds"]})

    def test_secondary_is_preserved_not_promoted(self):
        price, packet, _ = self.compile_doc(document("AWARD_NOTICE_JSON_V1", award(), "AWARD_NOTICE", "SECONDARY_INDEX"))
        self.assertEqual("SECONDARY_INDEX", price["sources"][0]["authority"])
        self.assertEqual("HOLD_NO_HISTORY", packet["price_engine_status"])
        self.assertIn("SOURCE_NOT_BUYER_OFFICIAL", {row["code"] for row in packet["holds"]})

    def test_source_and_payload_digests_are_audited(self):
        doc = document("AWARD_NOTICE_JSON_V1", award(), "AWARD_NOTICE")
        price, packet, _ = self.compile_doc(doc)
        self.assertEqual("a" * 64, price["sources"][0]["sha256"])
        audit = packet["source_audit"][0]
        self.assertEqual("a" * 64, audit["raw_source_sha256"])
        self.assertEqual(doc["payload_sha256"], audit["payload_sha256"])

    def test_payload_hash_mismatch_fails(self):
        doc = document("AWARD_NOTICE_JSON_V1", award(), "AWARD_NOTICE")
        doc["payload_sha256"] = "0" * 64
        self.assertRaisesRegex(Error, "payload_sha256 mismatch", compile, raw(request([doc])))

    def test_wrong_source_class_fails(self):
        doc = document("AWARD_NOTICE_JSON_V1", award(), "BID_TABULATION")
        self.assertRaisesRegex(Error, "source_class incompatible", compile, raw(request([doc])))

    def test_http_credentials_and_nondefault_port_fail(self):
        for uri in (
            "http://buyer.example.gov/a",
            "https://u:p@buyer.example.gov/a",
            "https://buyer.example.gov:8443/a",
        ):
            doc = document("AWARD_NOTICE_JSON_V1", award(), "AWARD_NOTICE")
            doc["source"]["uri"] = uri
            with self.subTest(uri=uri):
                with self.assertRaisesRegex(Error, "https URI|credential|default HTTPS port"):
                    compile(raw(request([doc])))

    def test_strict_json_and_bool_money(self):
        for bad in (b'{"x":1.5}', b'{"x":NaN}'):
            with self.assertRaisesRegex(Error, "non-integer"):
                load(bad)
        with self.assertRaisesRegex(Error, "duplicate JSON key"):
            load(b'{"x":1,"x":2}')
        with self.assertRaisesRegex(Error, "BOM"):
            load(b'\xef\xbb\xbf{}')
        payload = award(); payload["award_amount_minor"] = True
        with self.assertRaisesRegex(Error, "integer required"):
            compile(raw(request([document("AWARD_NOTICE_JSON_V1", payload, "AWARD_NOTICE")])))

    def test_hold_not_guess_boundaries(self):
        cases = [
            ("award_amount_minor", None, "AMBIGUOUS_AMOUNT"),
            ("term_months", None, "MISSING_TERM"),
        ]
        for field, value, code in cases:
            payload = award(); payload[field] = value
            price, packet, _ = self.compile_doc(document("AWARD_NOTICE_JSON_V1", payload, "AWARD_NOTICE"))
            with self.subTest(field=field):
                self.assertEqual([], price["observations"])
                self.assertIn(code, {row["code"] for row in packet["holds"]})
        payload = award(); payload.update(basis="HOURLY_RATE", unit=None)
        price, packet, _ = self.compile_doc(document("AWARD_NOTICE_JSON_V1", payload, "AWARD_NOTICE"))
        self.assertEqual([], price["observations"])
        self.assertIn("MISSING_RATE_UNIT", {row["code"] for row in packet["holds"]})
        payload = award(); payload["unit"] = "each"
        price, packet, _ = self.compile_doc(document("AWARD_NOTICE_JSON_V1", payload, "AWARD_NOTICE"))
        self.assertEqual([], price["observations"])
        self.assertIn("UNEXPECTED_LUMP_UNIT", {row["code"] for row in packet["holds"]})

    def test_row_and_source_identity_validation(self):
        payload = bid(); payload["rows"][1] = copy.deepcopy(payload["rows"][0])
        with self.assertRaisesRegex(Error, "duplicate row_id"):
            compile(raw(request([document("BID_TABULATION_JSON_V1", payload, "BID_TABULATION")])))
        payload = bid(); payload["rows"][0]["responsive"] = 1
        with self.assertRaisesRegex(Error, "bool required"):
            compile(raw(request([document("BID_TABULATION_JSON_V1", payload, "BID_TABULATION")])))
        one = document("AWARD_NOTICE_JSON_V1", award(), "AWARD_NOTICE")
        with self.assertRaisesRegex(Error, "duplicate source_id"):
            compile(raw(request([one, copy.deepcopy(one)])))

    def test_bad_adapter_and_amendment_type_fail(self):
        doc = document("AWARD_NOTICE_JSON_V1", award(), "AWARD_NOTICE"); doc["adapter"] = "NOPE"
        with self.assertRaisesRegex(Error, "unsupported adapter"):
            compile(raw(request([doc])))
        payload = amendment(); payload["change_type"] = "REPRICE"
        with self.assertRaisesRegex(Error, "OPTION or AMENDMENT"):
            compile(raw(request([document("AMENDMENT_OPTION_JSON_V1", payload, "AMENDMENT")])))

    def test_authority_ceiling_is_false(self):
        _, packet, receipt = self.compile_doc(document("AWARD_NOTICE_JSON_V1", award(), "AWARD_NOTICE"))
        self.assertTrue(all(value is False for value in packet["authority"].values()))
        self.assertTrue(all(value is False for value in receipt["authority"].values()))
        self.assertEqual(
            "CALLER_RETAINED_SOURCE_METADATA_NOT_PROVIDER_AUTHENTICATED",
            packet["source_authentication"],
        )

    def test_deterministic_verifiable_and_tamper_closed(self):
        doc = document("AWARD_NOTICE_JSON_V1", award(), "AWARD_NOTICE")
        request_bytes = raw(request([doc]))
        first = compile(request_bytes)
        self.assertEqual(first, compile(request_bytes))
        self.assertTrue(verify(request_bytes, *first)["verified"])
        price, packet, receipt = first
        with self.assertRaisesRegex(Error, "price input mismatch"):
            verify(request_bytes, price + b"x", packet, receipt)
        with self.assertRaisesRegex(Error, "packet mismatch"):
            verify(request_bytes, price, packet + b"x", receipt)
        with self.assertRaisesRegex(Error, "receipt mismatch"):
            verify(request_bytes, price, packet, receipt + b"x")

    def test_price_engine_consumes_output(self):
        from revenue.procurement_award_price_intelligence import engine
        price, _, _ = compile(raw(request([document("AWARD_NOTICE_JSON_V1", award(), "AWARD_NOTICE")])))
        packet, _, _ = engine.compile(price)
        self.assertEqual("PRICE_EVIDENCE_READY", json.loads(packet)["status"])

    def test_cli_compile_verify_and_no_overwrite(self):
        doc = document("AWARD_NOTICE_JSON_V1", award(), "AWARD_NOTICE")
        request_bytes = raw(request([doc]))
        with tempfile.TemporaryDirectory() as td:
            inp = Path(td) / "request.json"; inp.write_bytes(request_bytes)
            out = Path(td) / "generation"
            command = [sys.executable, "-m", "revenue.procurement_award_price_intelligence.source_adapters"]
            a = subprocess.run(command + ["compile", "--input", str(inp), "--out-dir", str(out)], cwd=Path(__file__).parents[2], capture_output=True, text=True)
            self.assertEqual(0, a.returncode, a.stderr)
            b = subprocess.run(
                command + ["verify", "--input", str(inp), "--price-input", str(out / "price_input.json"),
                           "--packet", str(out / "adapter_packet.json"), "--receipt", str(out / "adapter_receipt.json")],
                cwd=Path(__file__).parents[2], capture_output=True, text=True,
            )
            self.assertEqual(0, b.returncode, b.stderr)
            self.assertIn('"verified": true', b.stdout)
            before = {path.name: path.read_bytes() for path in out.iterdir()}
            c = subprocess.run(command + ["compile", "--input", str(inp), "--out-dir", str(out)], cwd=Path(__file__).parents[2], capture_output=True, text=True)
            self.assertEqual(2, c.returncode)
            self.assertEqual(before, {path.name: path.read_bytes() for path in out.iterdir()})


if __name__ == "__main__":
    unittest.main()
