"""Regression suite for the additive v2 review surface. No provider calls."""
import copy
import csv
import hashlib
from html.parser import HTMLParser
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import ap_review as r
import unc_ap_ai_v2 as engine


def case(invoice_id="INV-001", amount=12500):
    value = {
        "invoice_id": invoice_id, "supplier_id": "SUP-7", "extracted_supplier_id": "SUP-7",
        "expected_amount_cents": amount, "extracted_amount_cents": amount,
        "match_mode": "THREE_WAY", "purchase_order_amount_cents": amount,
        "receipt_amount_cents": amount, "routing_signoff_needed": True,
        "routing_signoff_present": True, "extraction_fields_total": 100,
        "extraction_fields_correct": 100, "duplicate_seen": False,
        "audit_events": ["received", "extracted", "validated", "matched",
                         "routing_started", "routing_completed", "erp_staged"],
    }
    value["integration"] = engine.expected_integration_evidence(value)
    return value


def intake(cases=None):
    return {"schema": r.INPUT_SCHEMA, "evidence_class": "SYNTHETIC", "currency": "USD",
            "extraction_threshold_basis_points": 9900, "cases": cases if cases is not None else [case()]}


def seal(value):
    value["receipt_sha256"] = r.digest({k: v for k, v in value.items() if k != "receipt_sha256"})
    return value


class ReviewTests(unittest.TestCase):
    def test_consistent(self):
        result = r.compile_review(intake())
        self.assertEqual(result["status"], "CONSISTENT")
        self.assertEqual(result["summary"]["consistent_count"], 1)
        self.assertEqual(result["rows"][0]["engine_result"]["provider_ack_independently_authenticated"], False)
        self.assertTrue(all(v is False for v in result["authority"].values()))

    def test_one_cent(self):
        row = case(); row["extracted_amount_cents"] += 1
        result = r.compile_review(intake([row]))
        self.assertEqual(result["status"], "REVIEW_REQUIRED")
        self.assertEqual(result["rows"][0]["disposition"], "HOLD_AMOUNT")
        self.assertEqual(result["summary"]["net_difference_cents"], 1)

    def test_cancelling_differences(self):
        a, b = case("A"), case("B")
        a["extracted_amount_cents"] += 1; b["extracted_amount_cents"] -= 1
        summary = r.compile_review(intake([a, b]))["summary"]
        self.assertEqual(summary["net_difference_cents"], 0)
        self.assertEqual(summary["absolute_difference_cents"], 2)
        self.assertEqual(summary["exception_count"], 2)

    def test_above_binary_float_integer_range(self):
        row = case(amount=(1 << 53) + 1)
        self.assertEqual(r.compile_review(intake([row]))["summary"]["expected_amount_cents"], (1 << 53) + 1)

    def test_aggregate_larger_than_input_integer_range(self):
        result = r.compile_review(intake([case("A", r.MAX_INTEGER), case("B", r.MAX_INTEGER)]))
        self.assertEqual(result["summary"]["expected_amount_cents"], r.MAX_INTEGER * 2)
        self.assertEqual(r.verify_review(r.canonical(result)), result)
        self.assertIn(str(r.MAX_INTEGER).encode(), r.render_outputs(result)["review.csv"])

    def test_zero_amount(self):
        self.assertEqual(r.compile_review(intake([case(amount=0)]))["status"], "CONSISTENT")

    def test_non_po_mode(self):
        row = case(); row["match_mode"] = "NONE"; row["purchase_order_amount_cents"] = None; row["receipt_amount_cents"] = None
        row["integration"] = engine.expected_integration_evidence(row)
        self.assertEqual(r.compile_review(intake([row]))["status"], "CONSISTENT")

    def test_two_way_mode(self):
        row = case(); row["match_mode"] = "TWO_WAY"; row["receipt_amount_cents"] = None
        row["integration"] = engine.expected_integration_evidence(row)
        self.assertEqual(r.compile_review(intake([row]))["status"], "CONSISTENT")

    def test_missing_receipt(self):
        row = case(); row["receipt_amount_cents"] = None
        self.assertEqual(r.compile_review(intake([row]))["rows"][0]["disposition"], "HOLD_MATCH")

    def test_missing_signoff(self):
        row = case(); row["routing_signoff_present"] = False
        self.assertEqual(r.compile_review(intake([row]))["rows"][0]["disposition"], "HOLD_ROUTING_SIGNOFF")

    def test_wrong_supplier(self):
        row = case(); row["extracted_supplier_id"] = "OTHER"
        self.assertEqual(r.compile_review(intake([row]))["rows"][0]["disposition"], "HOLD_SUPPLIER")

    def test_extraction_threshold(self):
        row = case(); row["extraction_fields_correct"] = 98
        self.assertEqual(r.compile_review(intake([row]))["rows"][0]["disposition"], "HOLD_EXTRACTION")

    def test_incorrect_request_digest(self):
        row = case(); row["integration"]["request_sha256"] = "a" * 64
        self.assertEqual(r.compile_review(intake([row]))["rows"][0]["disposition"], "HOLD_INTEGRATION")

    def test_incorrect_ack_digest(self):
        row = case(); row["integration"]["ack_sha256"] = "b" * 64
        self.assertEqual(r.compile_review(intake([row]))["rows"][0]["disposition"], "HOLD_INTEGRATION")

    def test_audit_failure(self):
        row = case(); row["audit_events"].remove("validated")
        self.assertEqual(r.compile_review(intake([row]))["rows"][0]["disposition"], "HOLD_AUDIT")

    def test_duplicate_seen(self):
        row = case(); row["duplicate_seen"] = True
        self.assertEqual(r.compile_review(intake([row]))["rows"][0]["disposition"], "HOLD_DUPLICATE")

    def test_duplicate_invoice_id(self):
        with self.assertRaises(r.ReviewError):
            r.compile_review(intake([case(), case()]))

    def test_same_invoice_other_supplier(self):
        a, b = case(), case(); b["supplier_id"] = b["extracted_supplier_id"] = "SUP-8"
        b["integration"] = engine.expected_integration_evidence(b)
        self.assertEqual(r.compile_review(intake([a, b]))["summary"]["consistent_count"], 2)

    def test_duplicate_supplied_effect_key(self):
        a, b = case("A"), case("B"); b["integration"]["effect_key"] = a["integration"]["effect_key"]
        with self.assertRaises(r.ReviewError):
            r.compile_review(intake([a, b]))

    def test_order_invariance(self):
        a, b = case("A"), case("B")
        self.assertEqual(r.compile_review(intake([b, a])), r.compile_review(intake([a, b])))

    def test_no_mutation(self):
        value = intake([case("B"), case("A")]); before = copy.deepcopy(value)
        result = r.compile_review(value); result["normalized_input"]["cases"][0]["invoice_id"] = "NEW"
        self.assertEqual(value, before)

    def test_unknown_top_field(self):
        value = intake(); value["source"] = {"ready": True}
        with self.assertRaises(r.ReviewError): r.compile_review(value)

    def test_unknown_case_field(self):
        value = intake(); value["cases"][0]["discount"] = 1
        with self.assertRaises(r.ReviewError): r.compile_review(value)

    def test_unknown_integration_field(self):
        value = intake(); value["cases"][0]["integration"]["authenticated"] = True
        with self.assertRaises(r.ReviewError): r.compile_review(value)

    def test_duplicate_decoded_json(self):
        with self.assertRaises(r.ReviewError): r.compile_review(b'{"amount":1,"amou\\u006et":2}')

    def test_float_constants(self):
        for token in ("1.0", "1e2", "NaN", "Infinity", "-Infinity"):
            with self.subTest(token=token), self.assertRaises(r.ReviewError): r.parse(token.encode())

    def test_direct_float(self):
        value = intake(); value["cases"][0]["expected_amount_cents"] = 12500.0
        with self.assertRaises(r.ReviewError): r.compile_review(value)

    def test_bool_as_money(self):
        value = intake(); value["cases"][0]["expected_amount_cents"] = True
        with self.assertRaises(r.ReviewError): r.compile_review(value)

    def test_bool_as_threshold(self):
        value = intake(); value["extraction_threshold_basis_points"] = True
        with self.assertRaises(r.ReviewError): r.compile_review(value)

    def test_unhashable_match_mode(self):
        value = intake(); value["cases"][0]["match_mode"] = []
        with self.assertRaises(r.ReviewError): r.compile_review(value)

    def test_limits(self):
        for value in (intake([]), intake([case(str(n)) for n in range(1001)])):
            with self.assertRaises(r.ReviewError): r.compile_review(value)
        with self.assertRaises(r.ReviewError): r.parse(b" " * (r.MAX_BYTES + 1))
        with self.assertRaises(r.ReviewError): r.parse(b"1" * 25)
        with self.assertRaises(r.ReviewError): r.compile_review(intake([case(amount=r.MAX_INTEGER + 1)]))

    def test_depth_and_cycles(self):
        value = []
        for _ in range(30): value = [value]
        with self.assertRaises(r.ReviewError): r.normalize_input(value)
        value = []; value.append(value)
        with self.assertRaises(r.ReviewError): r.normalize_input(value)

    def test_subclasses(self):
        class D(dict): pass
        with self.assertRaises(r.ReviewError): r.normalize_input(D(intake()))

    def test_nonstring_key(self):
        value = intake(); value[1] = "x"
        with self.assertRaises(r.ReviewError): r.compile_review(value)

    def test_invalid_utf8_and_surrogate(self):
        for raw in (b'"\xff"', b'"\\ud800"'):
            with self.assertRaises(r.ReviewError): r.normalize_input(raw)

    def test_identity_ambiguity(self):
        for identity in (" A", "A ", "A\x00B", "A\u202eB", "e\u0301", "", "x" * 257):
            row = case(); row["invoice_id"] = identity
            with self.subTest(identity=repr(identity)), self.assertRaises(r.ReviewError):
                r.compile_review(intake([row]))

    def test_long_valid_identity(self):
        self.assertEqual(r.compile_review(intake([case("x" * 256)]))["status"], "CONSISTENT")

    def test_currency_and_schema(self):
        for field, value in (("currency", "EUR"), ("schema", "new"), ("evidence_class", "AUTHENTICATED")):
            data = intake(); data[field] = value
            with self.assertRaises(r.ReviewError): r.compile_review(data)

    def test_operator_data_still_unverified(self):
        value = intake(); value["evidence_class"] = "OPERATOR_SUPPLIED_UNVERIFIED"
        out = r.compile_review(value)
        self.assertEqual(out["evidence_class"], value["evidence_class"])
        self.assertFalse(out["authority"]["provider_authenticated"])

    def test_replay(self):
        report = r.compile_review(intake())
        self.assertEqual(r.verify_review(r.canonical(report), against=intake()), report)

    def test_resealed_total_forgery(self):
        report = r.compile_review(intake()); report["summary"]["expected_amount_cents"] += 1
        with self.assertRaises(r.ReviewError): r.verify_review(seal(report))

    def test_resealed_disposition_forgery(self):
        row = case(); row["extracted_amount_cents"] += 1
        report = r.compile_review(intake([row])); report["rows"][0]["disposition"] = "PASS"; report["status"] = "CONSISTENT"
        with self.assertRaises(r.ReviewError): r.verify_review(seal(report))

    def test_resealed_authority_forgery(self):
        report = r.compile_review(intake()); report["authority"]["payment"] = True
        with self.assertRaises(r.ReviewError): r.verify_review(seal(report))

    def test_engine_identity_changed(self):
        report = r.compile_review(intake()); report["engine_source_sha256"] = "a" * 64
        with self.assertRaises(r.ReviewError): r.verify_review(seal(report))

    def test_input_swap_against_original(self):
        report = r.compile_review(intake([case("B")]))
        with self.assertRaises(r.ReviewError): r.verify_review(report, against=intake())

    def test_unknown_report_field(self):
        report = r.compile_review(intake()); report["accepted"] = True
        with self.assertRaises(r.ReviewError): r.verify_review(seal(report))

    def test_bool_report_value(self):
        report = r.compile_review(intake()); report["summary"]["invoice_count"] = True
        with self.assertRaises(r.ReviewError): r.verify_review(seal(report))

    def test_duplicate_report_key(self):
        raw = r.canonical(r.compile_review(intake()))
        raw = b'{"schema":"other",' + raw[1:]
        with self.assertRaises(r.ReviewError): r.verify_review(raw)

    def test_html_escapes_text_and_has_no_active_content(self):
        row = case('<script>alert("test")</script>'); row["supplier_id"] = row["extracted_supplier_id"] = '<img src="test">'
        row["integration"] = engine.expected_integration_evidence(row)
        html = r.render_outputs(r.compile_review(intake([row])))["review.html"].decode()
        tags = []
        class Parser(HTMLParser):
            def handle_starttag(self, tag, attrs): tags.append((tag, dict(attrs)))
        Parser().feed(html)
        self.assertFalse(any(t in ("script", "img", "iframe", "form", "a") for t, _ in tags))
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("default-src 'none'", html)

    def test_csv_formula_defanging(self):
        for prefix in ("=", "+", "-", "@"):
            row = case(prefix + "FORMULA")
            text = r.render_outputs(r.compile_review(intake([row])))["review.csv"].decode()
            self.assertEqual(list(csv.reader(io.StringIO(text)))[1][0], "'" + row["invoice_id"])

    def test_csv_exact_numbers_and_quotes(self):
        row = case('INV,"quoted"', (1 << 53) + 1)
        text = r.render_outputs(r.compile_review(intake([row])))["review.csv"].decode()
        line = list(csv.reader(io.StringIO(text)))[1]
        self.assertEqual(line[0], row["invoice_id"])
        self.assertEqual(line[3], str((1 << 53) + 1))

    def test_renderer_rejects_unverified_report(self):
        report = r.compile_review(intake()); report["summary"]["exception_count"] = 0; report["status"] = "PAID"
        with self.assertRaises(r.ReviewError): r.render_outputs(seal(report))

    def test_engine_direct_result_preserved(self):
        row = case(); report = r.compile_review(intake([row]))
        self.assertEqual(report["rows"][0]["engine_result"], engine.evaluate_invoice_case(row, extraction_threshold_basis_points=9900))


@unittest.skipUnless(hasattr(os, "O_NOFOLLOW"), "POSIX only")
class PackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.output = self.root / "review"
        self.source = self.root / "input.json"; self.source.write_bytes(r.canonical(intake()))
        self.report = r.compile_review(intake())

    def test_pack_roundtrip_and_permissions(self):
        r.write_pack(self.output, self.report)
        self.assertEqual(r.verify_pack(self.output, against=self.source.read_bytes()), self.report)
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o700)
        self.assertTrue(all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in self.output.iterdir()))

    def test_existing_directory_refused(self):
        self.output.mkdir(); (self.output / "keep").write_text("KEEP")
        with self.assertRaises(r.ReviewError): r.write_pack(self.output, self.report)
        self.assertEqual((self.output / "keep").read_text(), "KEEP")

    def test_existing_file_refused(self):
        self.output.write_text("KEEP")
        with self.assertRaises(r.ReviewError): r.write_pack(self.output, self.report)
        self.assertEqual(self.output.read_text(), "KEEP")

    def test_output_directory_symlink_refused(self):
        target = self.root / "target"; target.mkdir(); self.output.symlink_to(target, target_is_directory=True)
        with self.assertRaises(r.ReviewError): r.write_pack(self.output, self.report)
        self.assertEqual(list(target.iterdir()), [])

    def test_input_symlink_refused(self):
        link = self.root / "link"; link.symlink_to(self.source)
        with self.assertRaises(r.ReviewError): r._read_file(link, cap=r.MAX_BYTES)

    def test_fifo_refused(self):
        fifo = self.root / "fifo"; os.mkfifo(fifo)
        with self.assertRaises(r.ReviewError): r._read_file(fifo, cap=r.MAX_BYTES)

    def test_empty_and_oversized_files(self):
        for raw in (b"", b"x" * 11):
            self.source.write_bytes(raw)
            with self.assertRaises(r.ReviewError): r._read_file(self.source, cap=10)

    def test_extra_file_refused(self):
        r.write_pack(self.output, self.report); (self.output / "extra").write_text("x")
        with self.assertRaises(r.ReviewError): r.verify_pack(self.output)

    def test_missing_manifest_refused(self):
        r.write_pack(self.output, self.report); (self.output / "manifest.json").unlink()
        with self.assertRaises(r.ReviewError): r.verify_pack(self.output)

    def test_export_tampering_refused(self):
        for name in ("review.json", "review.csv", "review.html", "manifest.json"):
            output = self.root / name.replace(".", "_"); r.write_pack(output, self.report)
            with (output / name).open("ab") as f: f.write(b" ")
            with self.subTest(name=name), self.assertRaises(r.ReviewError): r.verify_pack(output)

    def test_symlinked_export_refused(self):
        r.write_pack(self.output, self.report)
        item = self.output / "review.csv"; raw = item.read_bytes(); item.unlink()
        target = self.root / "other.csv"; target.write_bytes(raw); item.symlink_to(target)
        with self.assertRaises(r.ReviewError): r.verify_pack(self.output)

    def test_partial_write_has_no_completion_marker(self):
        with patch.object(r.os, "fsync", side_effect=OSError("simulated storage failure")):
            with self.assertRaises(r.ReviewError): r.write_pack(self.output, self.report)
        self.assertFalse((self.output / "manifest.json").exists())

    def call(self, *args, optimized=False):
        return subprocess.run([sys.executable, *(["-O"] if optimized else []), str(Path(r.__file__)), *map(str, args)],
                              capture_output=True, text=True, timeout=20)

    def test_cli_build_and_verify(self):
        built = self.call("build", "--input", self.source, "--out", self.output)
        self.assertEqual(built.returncode, 0, built.stderr)
        verified = self.call("verify", "--out", self.output, "--against", self.source)
        self.assertEqual(verified.returncode, 0, verified.stderr)
        self.assertIn("VERIFY OK / CONSISTENT", verified.stdout)

    def test_cli_optimized_roundtrip(self):
        built = self.call("build", "--input", self.source, "--out", self.output, optimized=True)
        self.assertEqual(built.returncode, 0, built.stderr)
        verified = self.call("verify", "--out", self.output, "--against", self.source, optimized=True)
        self.assertEqual(verified.returncode, 0, verified.stderr)

    def test_cli_review_required_is_successful_report_not_payment(self):
        value = intake(); value["cases"][0]["extracted_amount_cents"] += 1; self.source.write_bytes(r.canonical(value))
        result = self.call("build", "--input", self.source, "--out", self.output)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("REVIEW_REQUIRED", result.stdout)
        self.assertFalse(r.verify_pack(self.output)["authority"]["payment"])

    def test_cli_invalid_input_creates_no_output(self):
        self.source.write_bytes(b'{"a":1,"a":2}')
        result = self.call("build", "--input", self.source, "--out", self.output)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.output.exists())

    def test_cli_modified_original_refused(self):
        r.write_pack(self.output, self.report); self.source.write_bytes(r.canonical(intake([case("CHANGED")])))
        result = self.call("verify", "--out", self.output, "--against", self.source)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("Traceback", result.stderr)

    def test_cli_existing_output_refused(self):
        r.write_pack(self.output, self.report)
        before = {p.name: p.read_bytes() for p in self.output.iterdir()}
        result = self.call("build", "--input", self.source, "--out", self.output)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.output.iterdir()})


if __name__ == "__main__":
    unittest.main()
