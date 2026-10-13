"""Focused tests for the real supplier enquiry exporter, not the desk's core."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from datetime import date, datetime
from unittest.mock import patch

import supplier_enquiries as se

TODAY = date(2026, 9, 8)
def request(**updates):
    result = {"id": "synthetic-request-1", "job_ref": "FICTITIOUS training job",
              "make": "Example", "model": "A100", "serial": "00021",
              "requested_part": "000-BELT", "quantity": 3, "notes": "Example only"}
    result.update(updates)
    return result

def row(**updates):
    result = {"id": "offer-1", "supplier": "Fictitious Supplier A",
              "supplier_sku": "000-SKU", "part_number": "000-BELT",
              "description": "Fictitious training part", "source_url": "https://catalog.example/000",
              "checked_on": "2026-09-08", "currency": "USD",
              "make": "Example", "model": "A100", "serial_scope": "",
              "lead_time": "Example quote: 2 days, not verified", "source_note": "Synthetic fixture",
              "aliases": ["000-OLD"], "unit_price": "32.45", "shipping": "8.00",
              "stock_status": "in_stock", "stock_qty": 9}
    result.update(updates)
    return result

def build(rows=None, req=None, **kwargs):
    return se.build_enquiries(req or request(), rows or [row()], as_of=TODAY, **kwargs)

def codes(result):
    return {q["code"] for q in result["enquiries"][0]["options"][0]["questions"]}

class ExportTests(unittest.TestCase):
    def test_decimal_exact_and_no_invented_shipping_or_tax_total(self):
        result = build()
        opt = result["enquiries"][0]["options"][0]
        self.assertEqual(opt["line_amount"], "97.35")
        self.assertNotIn("total", opt)
        self.assertIn("basis unverified", result["enquiries"][0]["text"])
        self.assertIn("tax_and_validity", codes(result))

    def test_cent_fraction_multiplication(self):
        self.assertEqual(build([row(unit_price="0.10")])["enquiries"][0]["options"][0]["line_amount"], "0.30")

    def test_unknown_money_is_not_zero(self):
        result = build([row(unit_price=None, shipping="")])
        self.assertIsNone(result["enquiries"][0]["options"][0]["line_amount"])
        self.assertTrue({"missing_price", "missing_shipping"} <= codes(result))
        self.assertIn("USD UNKNOWN", result["enquiries"][0]["text"])

    def test_different_currencies_remain_separate_alternatives(self):
        result = build([row(), row(id="offer-2", currency="EUR", unit_price="25.11")])
        options = result["enquiries"][0]["options"]
        self.assertEqual([x["line_amount"] for x in options], ["97.35", "75.33"])
        self.assertEqual([x["catalog"]["currency"] for x in options], ["USD", "EUR"])
        self.assertIn("ALTERNATIVES", result["enquiries"][0]["text"])
        self.assertNotIn("172.68", result["enquiries"][0]["text"])

    def test_one_draft_per_exact_supplier_not_per_currency(self):
        result = build([row(), row(id="b", supplier="B"), row(id="c", supplier="B", currency="EUR")])
        self.assertEqual(len(result["enquiries"]), 2)
        self.assertEqual(sorted(len(x["options"]) for x in result["enquiries"]), [1, 2])

    def test_do_not_merge_different_supplier_identifiers(self):
        result = build([row(supplier="Acme"), row(id="b", supplier="acme")])
        self.assertEqual(len(result["enquiries"]), 2)

    def test_freshness_boundary_is_explicit_policy(self):
        self.assertNotIn("aged_source", codes(build([row(checked_on="2026-09-01")])))
        self.assertIn("aged_source", codes(build([row(checked_on="2026-08-31")])))
        self.assertIn("aged_source", codes(build([row(checked_on="2026-09-07")], max_age_days=0)))

    def test_future_date_is_flagged_not_fresh(self):
        self.assertIn("future_source_date", codes(build([row(checked_on="2026-09-09")])))

    def test_missing_equipment_stays_unknown(self):
        result = build(req=request(model="", serial=""))
        self.assertTrue({"missing_model", "missing_serial", "fit_confirmation"} <= codes(result))
        self.assertIn("(model missing)", result["enquiries"][0]["text"])

    def test_serial_scope_requires_reference_even_for_matching_model(self):
        result = build([row(serial_scope="A0001–A0200")])
        self.assertTrue({"serial_scope", "fit_confirmation"} <= codes(result))

    def test_stock_zero_and_in_stock_disagreement(self):
        result = build([row(stock_qty=0)])
        self.assertTrue({"stock_conflict", "insufficient_stock_quantity"} <= codes(result))

    def test_out_of_stock_and_positive_quantity_disagreement(self):
        result = build([row(stock_status="out_of_stock", stock_qty=9)])
        self.assertTrue({"stock_conflict", "out_of_stock"} <= codes(result))

    def test_unknown_stock_and_lead_time_are_questions(self):
        result = build([row(stock_qty=None, stock_status="unknown", lead_time="")])
        self.assertTrue({"unknown_stock", "unknown_stock_quantity", "missing_lead_time"} <= codes(result))

    def test_insufficient_stock_keeps_requested_quantity(self):
        result = build([row(stock_qty=2)])
        self.assertIn("insufficient_stock_quantity", codes(result))
        self.assertEqual(result["request"]["quantity"], 3)

    def test_repeated_snapshot_deduplicates(self):
        result = build([row(), row()])
        self.assertEqual(len(result["enquiries"][0]["options"]), 1)

    def test_conflicting_repeated_id_rejected(self):
        with self.assertRaises(se.EnquiryError):
            build([row(), row(unit_price="33.00")])

    def test_input_objects_not_mutated(self):
        req, rows = request(), [row()]
        old = copy.deepcopy((req, rows))
        build(rows, req)
        self.assertEqual((req, rows), old)

    def test_provenance_and_leading_zero_ids_preserved(self):
        original = row(source_note="file.csv / row 0002 / SHA256 012abc\nOriginal note")
        result = build([original])
        option = result["enquiries"][0]["options"][0]
        self.assertEqual(option["catalog"], original)
        self.assertEqual(option["catalog_sha256"], se.sha(original))
        self.assertIn("000-SKU", result["enquiries"][0]["text"])
        self.assertIn(original["source_note"], result["enquiries"][0]["text"])

    def test_reordered_inputs_have_identical_identity(self):
        a,b = row(),row(id="b",supplier="B")
        self.assertEqual(build([a,b]), build([b,a]))

    def test_changed_quantity_source_and_policy_change_identity(self):
        base = build()
        self.assertNotEqual(base["input_sha256"], build(req=request(quantity=4))["input_sha256"])
        self.assertNotEqual(base["enquiries"][0]["id"], build([row(unit_price="33.00")])["enquiries"][0]["id"])
        self.assertNotEqual(base["input_sha256"], build(max_age_days=8)["input_sha256"])

    def test_invalid_numeric_inputs(self):
        for val in (1.1, True, "-1.00", "NaN", "1e2", "1.001", "Infinity", " 3.00"):
            with self.subTest(val=val), self.assertRaises(se.EnquiryError):
                build([row(unit_price=val)])
        for val in (True, 0, -1, 1.0, "3", 1_000_001):
            with self.subTest(q=val), self.assertRaises(se.EnquiryError):
                build(req=request(quantity=val))

    def test_bad_dates_and_currency(self):
        for val in ("2026-02-30", "2026-9-8", "2026-09-08T00:00:00Z", ""):
            with self.subTest(d=val), self.assertRaises(se.EnquiryError):
                build([row(checked_on=val)])
        with self.assertRaises(se.EnquiryError):
            build([row(currency="usd")])

    def test_no_nonfinite_extra_metadata(self):
        with self.assertRaises(se.EnquiryError):
            build([row(extra=float("nan"))])

    def test_invalid_urls_and_controls(self):
        for val in ("javascript:alert(1)", "https://user:pass@x.example/a",
                    "https://x.example:invalid/a", "https://x.example/a b"):
            with self.subTest(u=val), self.assertRaises(se.EnquiryError):
                build([row(source_url=val)])
        with self.assertRaises(se.EnquiryError):
            build([row(description="bad\x00value")])

    def test_full_json_read_limits_and_duplicate_keys(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/"input.json"
            for raw in (b'{"a":1,"a":2}', b'{"x":NaN}', b'\xff'):
                p.write_bytes(raw)
                with self.subTest(raw=raw), self.assertRaises(se.EnquiryError):
                    se.read_json(p)
            p.write_bytes(b"\xef\xbb\xbf" + b'{"a":1}')
            self.assertEqual(se.read_json(p), {"a":1})
            p.write_bytes(b" "*20)
            with patch.object(se, "MAX_INPUT_BYTES", 10), self.assertRaises(se.EnquiryError):
                se.read_json(p)

    def test_pack_real_files_hashes_print_escape_and_no_overwrite(self):
        result = build([row(supplier="../../<script>alert(1)</script>", source_note="<img onerror='boom'>")])
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)/"pack"
            manifest = se.write_pack(result, out)
            for name, metadata in manifest["files"].items():
                raw = (out/name).read_bytes()
                self.assertEqual(len(raw), metadata["bytes"])
                self.assertEqual(hashlib.sha256(raw).hexdigest(), metadata["sha256"])
            page = (out/"index.html").read_text()
            self.assertNotIn("<script>", page)
            self.assertIn("&lt;script&gt;", page)
            self.assertNotIn("<img onerror=", page)
            before = {x.name:x.read_bytes() for x in out.iterdir()}
            with self.assertRaises(se.EnquiryError):
                se.write_pack(result,out)
            self.assertEqual(before, {x.name:x.read_bytes() for x in out.iterdir()})
            self.assertTrue(all("/" not in n for n in before))

    def test_partial_pack_has_no_completion_manifest(self):
        result = build()
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)/"pack"
            with patch.object(Path, "write_bytes", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    se.write_pack(result, out)
            self.assertTrue(out.is_dir())
            self.assertFalse((out/"MANIFEST.json").exists())

    def test_no_network_during_build_and_write(self):
        with patch("socket.socket", side_effect=AssertionError("unexpected network")):
            result = build()
            with tempfile.TemporaryDirectory() as d:
                se.write_pack(result, Path(d)/"pack")
        self.assertEqual(result["network_actions"], 0)
        self.assertEqual(result["status"], "unsent")

    def test_real_cli_and_non_destructive_retry(self):
        with tempfile.TemporaryDirectory() as d:
            home=Path(d)
            req=home/"request.json"; cat=home/"catalog.json"; out=home/"pack"
            req.write_text(json.dumps(request()))
            cat.write_text(json.dumps({"operation_id":"retained-import", "items":[row()]}))
            command=[sys.executable, "-S", str(Path(se.__file__)), "--request", str(req),
                     "--catalog", str(cat), "--out", str(out), "--as-of","2026-09-08"]
            run=subprocess.run(command, capture_output=True, text=True, timeout=10)
            self.assertEqual(run.returncode,0,run.stderr)
            self.assertEqual(json.loads(run.stdout)["enquiries"],1)
            self.assertEqual(se.read_json(out/"enquiries.json")["status"],"unsent")
            repeat=subprocess.run(command,capture_output=True,text=True,timeout=10)
            self.assertEqual(repeat.returncode,2)
            self.assertIn("already exists",repeat.stderr)

    def test_invalid_envelope_limits(self):
        for raw in ({}, [], None):
            with self.subTest(raw=raw), self.assertRaises(se.EnquiryError):
                se.build_enquiries(request(), raw, as_of=TODAY)
        with self.assertRaises(se.EnquiryError):
            se.build_enquiries(request(), [row()]*501,as_of=TODAY)
        with self.assertRaises(se.EnquiryError):
            se.build_enquiries(request(), [row()], as_of=datetime(2026,9,8))
        with self.assertRaises(se.EnquiryError):
            build(max_age_days=True)


    def test_out_of_stock_conflict_and_shortage_both_retained(self):
        result=build([row(stock_status="out_of_stock",stock_qty=2)])
        self.assertTrue({"out_of_stock","stock_conflict","insufficient_stock_quantity"} <= codes(result))

    def test_malformed_optional_desk_metadata_is_controlled_input_error(self):
        for metadata in ("string", [], {"effective_fit":"made-up","review":{}},
                         {"effective_fit":"compatible","review":"not-an-object"}):
            with self.subTest(metadata=metadata), self.assertRaises(se.EnquiryError):
                build([row(desk_option=metadata)])

    def test_request_description_reaches_supplier_text(self):
        result=build(req=request(description="Repair symptom supplied by the shop"))
        self.assertIn("Repair symptom supplied by the shop",result["enquiries"][0]["text"])



    def test_modified_pack_cannot_write_outside_pack_directory(self):
        result=build()
        result["enquiries"][0]["id"]="../../outside"
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/"pack"
            with self.assertRaises(se.EnquiryError):
                se.write_pack(result,out)
            self.assertFalse(out.exists())

    def test_duplicate_pack_ids_and_unhashable_fit_are_controlled_errors(self):
        result=build()
        result["enquiries"].append(copy.deepcopy(result["enquiries"][0]))
        with tempfile.TemporaryDirectory() as d, self.assertRaises(se.EnquiryError):
            se.write_pack(result,Path(d)/"pack")
        with self.assertRaises(se.EnquiryError):
            build([row(desk_option={"effective_fit":[],"review":{}})])


if __name__ == "__main__":
    unittest.main()
