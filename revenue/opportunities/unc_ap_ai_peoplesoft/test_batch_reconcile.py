"""Retained executable coverage for real offline batch reconciliation."""
from __future__ import annotations
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import itertools
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import batch_reconcile as m

AS_OF = "2026-09-18T01:45:00Z"
HERE = Path(__file__).resolve().parent


def invoice(identity="INV-001", quantity=2000, *, number=None, supplier="SUP-7", po="PO-1", receipt="REC-1", currency="USD", price=125):
    net = m.amount(quantity, price)
    return {"invoice_id": identity, "supplier_id": supplier,
            "invoice_number": number or identity, "currency": currency,
            "document_sha256": hashlib.sha256(identity.encode()).hexdigest(),
            "invoice_date": "2026-09-17", "document_type": "INVOICE", "approval": "APPROVED",
            "net_total_minor": net, "tax_minor": 0, "freight_minor": 0, "other_minor": 0,
            "gross_total_minor": net,
            "lines": [{"line_id": "LINE-1", "po_line_id": po, "uom": "EA",
                       "quantity_milliunits": quantity, "unit_price_minor": price, "net_minor": net,
                       "receipts": [{"receipt_id": receipt, "quantity_milliunits": quantity}] if receipt else []}]}


def history(quantity=3000):
    return {"invoice_id": "HIST-1", "supplier_id": "SUP-7", "invoice_number": "HIST-1", "currency": "USD",
            "document_sha256": hashlib.sha256(b"HIST-1").hexdigest(),
            "allocations": [{"allocation_id": "ALLOC-1", "po_line_id": "PO-1",
                             "quantity_milliunits": quantity, "net_minor": m.amount(quantity, 125),
                             "receipts": [{"receipt_id": "REC-1", "quantity_milliunits": quantity}]}]}


def snapshot():
    return {"schema_version": 1, "entity_id": "DEMO-ENTITY", "snapshot_id": "DEMO-SNAPSHOT-1",
            "captured_at": "2026-09-18T01:30:00Z",
            "coverage": {"po_register": "COMPLETE", "receipt_register": "COMPLETE", "invoice_history": "COMPLETE"},
            "currency_scales": {"USD": 2},
            "policy": {"quantity_tolerance_milliunits": 0, "price_tolerance_minor": 0, "max_snapshot_age_seconds": 3600},
            "purchase_orders": [{"po_line_id": "PO-1", "supplier_id": "SUP-7", "currency": "USD", "uom": "EA",
                                 "quantity_milliunits": 10000, "unit_price_minor": 125, "status": "OPEN",
                                 "match_mode": "THREE_WAY", "source_ref": "synthetic:po-export:1"}],
            "receipts": [{"receipt_id": "REC-1", "po_line_id": "PO-1", "quantity_milliunits": 10000,
                          "source_ref": "synthetic:receipt-export:1"}],
            "history": [], "invoices": [invoice()]}


def reseal(report):
    value = deepcopy(report)
    value.pop("receipt_sha256", None)
    value["receipt_sha256"] = m.digest(value)
    return value


class Reconciliation(unittest.TestCase):
    def review(self, p=None, as_of=AS_OF):
        return m.compile_review(snapshot() if p is None else p, as_of=as_of)

    def has(self, p, reason, index=0):
        result = self.review(p)
        self.assertIn(reason, result["invoices"][index]["reasons"])
        self.assertEqual(result["state"], "HOLD_REVIEW")
        return result

    def test_clear_snapshot(self):
        result = self.review()
        self.assertEqual(result["state"], "REVIEW_CLEAR")
        self.assertEqual(result["summary_by_currency"]["USD"]["review_clear_gross_minor"], 250)
        self.assertTrue(all(value is False for value in result["authority"].values()))
        self.assertTrue(m.verify_report(snapshot(), result))

    def test_partial_invoices_are_legitimate(self):
        p = snapshot(); p["history"] = [history()]
        p["invoices"] = [invoice("I-1", 4000), invoice("I-2", 3000)]
        r = self.review(p)
        self.assertEqual(r["state"], "REVIEW_CLEAR")
        self.assertEqual(r["po_capacities"][0]["historical_quantity_milliunits"], 3000)
        self.assertEqual(r["po_capacities"][0]["candidate_quantity_milliunits"], 7000)

    def test_batch_overcommit_holds_all_not_first_winner(self):
        p = snapshot(); p["history"] = [history()]
        p["invoices"] = [invoice("I-1", 4000), invoice("I-2", 4000)]
        r = self.review(p)
        for row in r["invoices"]:
            self.assertIn("PO_QUANTITY_OVERCOMMITTED", row["reasons"])
            self.assertIn("RECEIPT_OVERCOMMITTED", row["reasons"])
        p["invoices"].reverse()
        self.assertEqual(m.canonical(r), m.canonical(self.review(p)))

    def test_duplicate_normalized_invoice_number_holds_both(self):
        for left, right in [("abc-17", "ABC-17"), ("ＡＢＣ-17", "abc-17"), ("ab  cd", "AB CD")]:
            with self.subTest(left=left):
                p = snapshot(); p["invoices"] = [invoice("I-1", number=left), invoice("I-2", number=right)]
                self.assertTrue(all("POSSIBLE_DUPLICATE_BATCH" in row["reasons"] for row in self.review(p)["invoices"]))

    def test_invoice_number_punctuation_preserved(self):
        p = snapshot(); p["invoices"] = [invoice("I-1", number="ABC-1"), invoice("I-2", number="ABC1")]
        self.assertEqual(self.review(p)["state"], "REVIEW_CLEAR")

    def test_duplicate_document_across_suppliers(self):
        p = snapshot(); p["invoices"].append(invoice("I-2", supplier="SUP-8"))
        p["invoices"][1]["document_sha256"] = p["invoices"][0]["document_sha256"]
        for row in self.review(p)["invoices"]:
            self.assertIn("POSSIBLE_DUPLICATE_BATCH", row["reasons"])

    def test_same_number_different_suppliers_not_duplicate(self):
        p = snapshot(); po = deepcopy(p["purchase_orders"][0]); po.update(po_line_id="PO-2", supplier_id="SUP-8")
        p["purchase_orders"].append(po)
        p["receipts"].append({"receipt_id":"REC-2", "po_line_id":"PO-2", "quantity_milliunits":10000, "source_ref":"synthetic:r2"})
        p["invoices"] = [invoice("I-1", number="ONE"), invoice("I-2", number="ONE", supplier="SUP-8", po="PO-2", receipt="REC-2")]
        self.assertEqual(self.review(p)["state"], "REVIEW_CLEAR")

    def test_history_duplicate_number(self):
        p = snapshot(); p["history"] = [history()]; p["invoices"][0]["invoice_number"] = "hist-1"
        self.has(p, "POSSIBLE_DUPLICATE_HISTORY")

    def test_history_duplicate_doc(self):
        p = snapshot(); p["history"] = [history()]; p["invoices"][0]["document_sha256"] = p["history"][0]["document_sha256"]
        self.has(p, "POSSIBLE_DUPLICATE_HISTORY")

    def test_history_duplicate_id(self):
        p = snapshot(); p["history"] = [history()]; p["invoices"][0]["invoice_id"] = "HIST-1"
        self.has(p, "POSSIBLE_DUPLICATE_HISTORY")

    def test_duplicate_history_holds_whole_snapshot(self):
        p = snapshot(); h = history(1000); h2 = deepcopy(h); h2["invoice_id"] = "HIST-2"
        p["history"] = [h, h2]
        self.has(p, "POSSIBLE_DUPLICATE_IN_HISTORY")

    def test_history_overallocated(self):
        p = snapshot(); p["history"] = [history(11000)]
        r = self.has(p, "HISTORY_PO_OVERALLOCATED")
        self.assertIn("HISTORY_RECEIPT_OVERALLOCATED", r["snapshot_issues"])

    def test_history_amount_overallocated(self):
        p = snapshot(); p["history"] = [history(1000)]; p["history"][0]["allocations"][0]["net_minor"] = 2000
        self.has(p, "HISTORY_PO_OVERALLOCATED")

    def test_receipt_reuse_holds_every_participant(self):
        p = snapshot(); p["receipts"][0]["quantity_milliunits"] = 3000
        p["invoices"] = [invoice("I-1"), invoice("I-2")]
        self.assertTrue(all("RECEIPT_OVERCOMMITTED" in r["reasons"] for r in self.review(p)["invoices"]))

    def test_history_consumes_receipt_capacity(self):
        p = snapshot(); p["receipts"][0]["quantity_milliunits"] = 4000; p["history"] = [history(3000)]
        self.has(p, "RECEIPT_OVERCOMMITTED")

    def test_quantity_tolerance_is_per_po_not_per_invoice(self):
        p = snapshot(); p["policy"]["quantity_tolerance_milliunits"] = 1000
        p["receipts"][0]["quantity_milliunits"] = 12000
        p["invoices"] = [invoice("I-1", 6000), invoice("I-2", 5000)]
        self.assertEqual(self.review(p)["state"], "REVIEW_CLEAR")
        p["invoices"] = [invoice("I-1", 6000), invoice("I-2", 6000)]
        self.assertTrue(all("PO_QUANTITY_OVERCOMMITTED" in r["reasons"] for r in self.review(p)["invoices"]))

    def test_split_line_rounding_does_not_silently_expand_amount(self):
        p = snapshot(); p["policy"]["quantity_tolerance_milliunits"] = 1000
        p["receipts"][0]["quantity_milliunits"] = 12000
        p["invoices"] = [invoice("I-1", 5500), invoice("I-2", 5500)]
        r = self.review(p)
        self.assertEqual(r["po_capacities"][0]["candidate_net_minor"], 1376)
        self.assertEqual(r["po_capacities"][0]["net_limit_minor"], 1375)
        self.assertTrue(all("PO_AMOUNT_OVERCOMMITTED" in row["reasons"] for row in r["invoices"]))

    def test_po_tolerance_never_expands_receipt(self):
        p = snapshot(); p["policy"]["quantity_tolerance_milliunits"] = 2000; p["invoices"] = [invoice(quantity=11000)]
        self.has(p, "RECEIPT_OVERCOMMITTED")

    def test_unit_price_exact_and_tolerance(self):
        p = snapshot(); p["invoices"] = [invoice(price=126)]
        self.has(p, "UNIT_PRICE_EXCEEDED")
        p["policy"]["price_tolerance_minor"] = 1
        self.assertEqual(self.review(p)["state"], "REVIEW_CLEAR")

    def test_two_way_no_receipt_required(self):
        p = snapshot(); p["purchase_orders"][0]["match_mode"] = "TWO_WAY"
        p["invoices"][0]["lines"][0]["receipts"] = []
        self.assertEqual(self.review(p)["state"], "REVIEW_CLEAR")

    def test_three_way_receipt_required(self):
        p = snapshot(); p["invoices"][0]["lines"][0]["receipts"] = []
        self.has(p, "RECEIPT_ALLOCATION_MISMATCH")

    def test_two_way_provided_receipt_still_reconciles(self):
        p = snapshot(); p["purchase_orders"][0]["match_mode"] = "TWO_WAY"
        p["invoices"][0]["lines"][0]["receipts"][0]["quantity_milliunits"] = 1000
        self.has(p, "RECEIPT_ALLOCATION_MISMATCH")

    def test_split_receipts(self):
        p = snapshot(); p["receipts"][0]["quantity_milliunits"] = 1000
        p["receipts"].append({"receipt_id":"REC-2", "po_line_id":"PO-1", "quantity_milliunits":1000, "source_ref":"synthetic:r2"})
        p["invoices"][0]["lines"][0]["receipts"] = [{"receipt_id":"REC-2","quantity_milliunits":1000},{"receipt_id":"REC-1","quantity_milliunits":1000}]
        r = self.review(p)
        self.assertEqual(r["state"], "REVIEW_CLEAR")
        p["receipts"].reverse(); p["invoices"][0]["lines"][0]["receipts"].reverse()
        self.assertEqual(r, self.review(p))

    def test_missing_receipt(self):
        p = snapshot(); p["invoices"][0]["lines"][0]["receipts"][0]["receipt_id"] = "MISSING"
        self.has(p, "MISSING_RECEIPT")

    def test_wrong_receipt_po(self):
        p = snapshot(); po = deepcopy(p["purchase_orders"][0]); po["po_line_id"] = "PO-2"; p["purchase_orders"].append(po)
        p["receipts"][0]["po_line_id"] = "PO-2"
        self.has(p, "RECEIPT_PO_MISMATCH")

    def test_nonpo_manual(self):
        p = snapshot(); p["invoices"][0]["lines"][0]["po_line_id"] = None
        self.has(p, "NON_PO_REQUIRES_REVIEW")

    def test_missing_po(self):
        p = snapshot(); p["invoices"][0]["lines"][0]["po_line_id"] = "MISSING"
        self.has(p, "MISSING_PO")

    def test_closed_po(self):
        p = snapshot(); p["purchase_orders"][0]["status"] = "CLOSED"
        self.has(p, "PO_CLOSED")

    def test_identity_mismatches_never_mix_capacity(self):
        for kind in ("supplier", "currency", "uom"):
            with self.subTest(kind=kind):
                p = snapshot()
                if kind == "supplier": p["invoices"][0]["supplier_id"] = "OTHER"
                if kind == "currency": p["currency_scales"]["EUR"] = 2; p["invoices"][0]["currency"] = "EUR"
                if kind == "uom": p["invoices"][0]["lines"][0]["uom"] = "BOX"
                r = self.has(p, "PO_IDENTITY_MISMATCH")
                self.assertEqual(r["po_capacities"][0]["candidate_quantity_milliunits"], 0)

    def test_line_rounding_half_up(self):
        self.assertEqual(m.amount(1, 500), 1)
        self.assertEqual(m.amount(1, 499), 0)
        self.assertEqual(m.amount(-1, 500), -1)
        p = snapshot(); p["invoices"] = [invoice(quantity=333)]
        self.assertEqual(self.review(p)["state"], "REVIEW_CLEAR")

    def test_line_arithmetic(self):
        p = snapshot(); p["invoices"][0]["lines"][0]["net_minor"] += 1
        self.has(p, "LINE_ARITHMETIC_MISMATCH")

    def test_net_header(self):
        p = snapshot(); p["invoices"][0]["net_total_minor"] += 1
        self.has(p, "NET_HEADER_MISMATCH")

    def test_gross_header(self):
        p = snapshot(); p["invoices"][0]["gross_total_minor"] += 1
        self.has(p, "GROSS_HEADER_MISMATCH")

    def test_explicit_tax_and_charges_reconcile_but_are_not_validated(self):
        p = snapshot(); p["invoices"][0].update(tax_minor=20, freight_minor=30, other_minor=5, gross_total_minor=305)
        self.assertEqual(self.review(p)["state"], "REVIEW_CLEAR")

    def test_approval(self):
        for state in ("PENDING", "REJECTED"):
            p = snapshot(); p["invoices"][0]["approval"] = state
            self.has(p, "APPROVAL_" + state)

    def test_credit_never_frees_capacity(self):
        p = snapshot(); p["invoices"] = [invoice("I-1", 11000)]
        credit = invoice("C-1", 2000); credit.update(document_type="CREDIT", net_total_minor=-250, gross_total_minor=-250)
        credit["lines"][0].update(quantity_milliunits=-2000, net_minor=-250, receipts=[])
        p["invoices"].append(credit)
        r = self.review(p)
        states = {x["invoice_id"]:x for x in r["invoices"]}
        self.assertIn("CREDIT_REQUIRES_LINKED_REVIEW", states["C-1"]["reasons"])
        self.assertIn("PO_QUANTITY_OVERCOMMITTED", states["I-1"]["reasons"])
        self.assertEqual(r["po_capacities"][0]["candidate_quantity_milliunits"], 11000)

    def test_currencies_separate(self):
        p = snapshot(); p["currency_scales"]["JPY"] = 0
        po = deepcopy(p["purchase_orders"][0]); po.update(po_line_id="PO-2", currency="JPY")
        p["purchase_orders"].append(po)
        p["receipts"].append({"receipt_id":"REC-2", "po_line_id":"PO-2", "quantity_milliunits":10000, "source_ref":"synthetic:r2"})
        p["invoices"].append(invoice("I-2", po="PO-2", receipt="REC-2", currency="JPY"))
        r = self.review(p)
        self.assertEqual(r["state"], "REVIEW_CLEAR")
        self.assertEqual(set(r["summary_by_currency"]), {"USD", "JPY"})
        self.assertEqual(r["summary_by_currency"]["JPY"]["scale"], 0)
        self.assertNotIn("total", r)

    def test_coverage_is_explicit(self):
        for key in snapshot()["coverage"]:
            for state in ("PARTIAL", "UNKNOWN"):
                p = snapshot(); p["coverage"][key] = state
                self.has(p, "INCOMPLETE_DECLARED_COVERAGE")

    def test_stale_boundary(self):
        self.assertEqual(self.review(as_of="2026-09-18T02:30:00Z")["state"], "REVIEW_CLEAR")
        self.assertIn("STALE_SNAPSHOT", self.review(as_of="2026-09-18T02:30:01Z")["snapshot_issues"])

    def test_future_snapshot(self):
        self.assertIn("FUTURE_SNAPSHOT", self.review(as_of="2026-09-18T01:29:59Z")["snapshot_issues"])

    def test_future_invoice(self):
        p = snapshot(); p["invoices"][0]["invoice_date"] = "2026-09-19"
        self.has(p, "INVOICE_AFTER_SNAPSHOT")

    def test_missing_history_join_is_invalid(self):
        p = snapshot(); p["history"] = [history()]; p["history"][0]["allocations"][0]["po_line_id"] = "MISSING"
        with self.assertRaises(m.ContractError): self.review(p)

    def test_history_receipt_quantity_mismatch_invalid(self):
        p = snapshot(); p["history"] = [history()]; p["history"][0]["allocations"][0]["receipts"][0]["quantity_milliunits"] = 2000
        with self.assertRaises(m.ContractError): self.review(p)

    def test_history_receipt_missing_invalid(self):
        p = snapshot(); p["history"] = [history()]; p["history"][0]["allocations"][0]["receipts"][0]["receipt_id"] = "MISSING"
        with self.assertRaises(m.ContractError): self.review(p)

    def test_receipt_missing_po_invalid(self):
        p = snapshot(); p["receipts"][0]["po_line_id"] = "MISSING"
        with self.assertRaises(m.ContractError): self.review(p)

    def test_duplicate_structural_ids_invalid(self):
        for table in ("invoices", "purchase_orders", "receipts"):
            p = snapshot(); p[table].append(deepcopy(p[table][0]))
            with self.subTest(table=table), self.assertRaises(m.ContractError): self.review(p)

    def test_duplicate_lines_invalid(self):
        p = snapshot(); p["invoices"][0]["lines"].append(deepcopy(p["invoices"][0]["lines"][0]))
        with self.assertRaises(m.ContractError): self.review(p)

    def test_duplicate_allocation_invalid(self):
        p = snapshot(); r = p["invoices"][0]["lines"][0]["receipts"]; r.append(deepcopy(r[0]))
        with self.assertRaises(m.ContractError): self.review(p)

    def test_order_invariance_all_permutations(self):
        p = snapshot(); p["invoices"] = [invoice("I-1"), invoice("I-2"), invoice("I-3")]
        expected = m.canonical(self.review(p))
        for permutation in itertools.permutations(p["invoices"]):
            q = deepcopy(p); q["invoices"] = list(permutation)
            self.assertEqual(m.canonical(self.review(q)), expected)

    def test_caller_input_is_unchanged(self):
        p = snapshot(); before = deepcopy(p)
        self.review(p); self.assertEqual(p, before)

    def test_input_generation_binding(self):
        p = snapshot(); before = self.review(p)
        p["snapshot_id"] = "DEMO-SNAPSHOT-2"
        self.assertNotEqual(before["receipt_sha256"], self.review(p)["receipt_sha256"])
        with self.assertRaises(m.ContractError): m.verify_report(p, before)

    def test_full_invoice_receipt_binding(self):
        p = snapshot(); old = self.review(p)
        p["invoices"] = [invoice(quantity=3000)]
        new = self.review(p)
        self.assertNotEqual(old["receipt_sha256"], new["receipt_sha256"])
        self.assertNotEqual(old["invoices"][0]["invoice_sha256"], new["invoices"][0]["invoice_sha256"])

    def test_resealed_report_tampering_fails(self):
        p = snapshot(); r = self.review(p); r["summary_by_currency"]["USD"]["review_clear_gross_minor"] += 1
        with self.assertRaises(m.ContractError): m.verify_report(p, reseal(r))

    def test_bool_int_report_alias_fails(self):
        p = snapshot(); r = self.review(p); r["authority"]["payment"] = 0
        with self.assertRaises(m.ContractError): m.verify_report(p, reseal(r))

    def test_historical_verifier_not_current_freshness(self):
        p = snapshot(); r = self.review(p)
        self.assertTrue(m.verify_report(p, r))
        self.assertEqual(self.review(p, as_of="2026-09-19T01:45:00Z")["state"], "HOLD_REVIEW")

    def test_missing_or_extra_report_field_fails(self):
        for mutation in (lambda r:r.pop("invoices"), lambda r:r.update(extra="x")):
            r = self.review(); mutation(r)
            with self.assertRaises(m.ContractError): m.verify_report(snapshot(), reseal(r))


class StrictInput(unittest.TestCase):
    def bad(self, value):
        with self.assertRaises(m.ContractError): m.canonical(value)

    def test_duplicate_json_key(self):
        with self.assertRaises(m.ContractError): m.load_json('{"x":1,"x":2}')

    def test_nonfinite_and_decimal_json(self):
        for token in ("NaN", "Infinity", "-Infinity", "1.0", "1e0"):
            with self.subTest(token=token), self.assertRaises(m.ContractError): m.load_json('{"x":'+token+'}')

    def test_large_integer_tokens(self):
        for token in ("9"*5000, str(m.MAX_INT+1), "-"+"9"*20):
            with self.assertRaises(m.ContractError): m.load_json('{"x":'+token+'}')

    def test_lone_surrogates(self):
        self.bad({"x":"\ud800"}); self.bad({"\udfff":"x"})
        with self.assertRaises(m.ContractError): m.load_json('"\\ud800"')

    def test_invalid_utf8(self):
        with self.assertRaises(m.ContractError): m.load_json(b'"\xff"')

    def test_subclass_containers_and_scalars(self):
        class D(dict): pass
        class L(list): pass
        class S(str): pass
        class I(int): pass
        for v in (D(), L(), S("x"), I(1)):
            self.bad(v)

    def test_type_checks_do_not_invoke_metaclass_equality(self):
        class Trap(type):
            def __eq__(self, other):
                raise RuntimeError("type equality hook must not execute")
        class Strange(metaclass=Trap): pass
        self.bad(Strange())
        with self.assertRaises(m.ContractError): m.load_json(Strange())

    def test_floats_and_unknown_objects(self):
        for v in (1.0, float("nan"), object(), (1,2), {1:"x"}): self.bad(v)

    def test_cycles(self):
        v=[]; v.append(v); self.bad(v)
        d={}; d["self"]=d; self.bad(d)

    def test_depth(self):
        x=0
        for _ in range(m.MAX_DEPTH+2): x=[x]
        self.bad(x)
        with self.assertRaises(m.ContractError): m.load_json("["*2000+"0"+"]"*2000)

    def test_node_limit(self): self.bad([None]*(m.MAX_NODES+1))

    def test_single_scalar_bound(self): self.bad("x"*(m.MAX_BYTES+1))

    def test_repeated_alias_byte_work(self):
        x="x"*1_000_000
        self.bad([x]*5)

    def test_escaped_byte_work(self): self.bad("\x01"*700_000)

    def test_unsafe_integer(self): self.bad(m.MAX_INT+1)

    def test_bool_is_not_version_or_money(self):
        for mutate in (lambda p:p.update(schema_version=True), lambda p:p["invoices"][0].update(gross_total_minor=True)):
            p=snapshot(); mutate(p)
            with self.assertRaises(m.ContractError): m.compile_review(p, as_of=AS_OF)

    def test_unknown_and_missing_fields(self):
        for mutate in (lambda p:p.update(unexpected=1), lambda p:p.pop("policy")):
            p=snapshot(); mutate(p)
            with self.assertRaises(m.ContractError): m.compile_review(p, as_of=AS_OF)

    def test_control_and_whitespace_ids(self):
        for identity in ("x\n", " x", "x\u200b", "", "x"*129):
            p=snapshot(); p["entity_id"]=identity
            with self.assertRaises(m.ContractError): m.compile_review(p, as_of=AS_OF)

    def test_time_formats(self):
        for when in ("2026-09-18", "2026-09-18T01:45:00+00:00", "2026-09-18T01:45:00.0Z", "2026-02-30T00:00:00Z", "x"):
            with self.subTest(when=when), self.assertRaises(m.ContractError): m.compile_review(snapshot(), as_of=when)

    def test_bad_calendar_date(self):
        p=snapshot(); p["invoices"][0]["invoice_date"]="2026-02-30"
        with self.assertRaises(m.ContractError): m.compile_review(p, as_of=AS_OF)

    def test_undeclared_currency(self):
        p=snapshot(); p["invoices"][0]["currency"]="EUR"
        with self.assertRaises(m.ContractError): m.compile_review(p, as_of=AS_OF)

    def test_negative_invoice_quantity(self):
        p=snapshot(); p["invoices"][0]["lines"][0]["quantity_milliunits"]=-1
        with self.assertRaises(m.ContractError): m.compile_review(p, as_of=AS_OF)

    def test_empty_batch(self):
        p=snapshot(); p["invoices"]=[]
        with self.assertRaises(m.ContractError): m.compile_review(p, as_of=AS_OF)

    def test_arithmetic_overflow(self):
        with self.assertRaises(m.ContractError): m.amount(m.MAX_INT,m.MAX_INT)

    def test_json_roundtrip(self): self.assertEqual(m.load_json(m.canonical(snapshot())), snapshot())


class FilesAndCLI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name); self.input=self.root/"snapshot.json"
        self.input.write_bytes(m.canonical(snapshot()))

    def cli(self,*args):
        return subprocess.run([sys.executable, *(["-O"] if sys.flags.optimize else []), str(HERE/"batch_reconcile.py"), *map(str,args)], capture_output=True,text=True, timeout=15)

    def test_read_regular_file(self): self.assertEqual(m.load_json(m.read_file(self.input)), snapshot())

    def test_read_symlink_refused(self):
        link=self.root/"link.json"; link.symlink_to(self.input)
        with self.assertRaises(m.ContractError): m.read_file(link)

    def test_read_directory_refused(self):
        with self.assertRaises(m.ContractError): m.read_file(self.root)

    @unittest.skipUnless(hasattr(os,"mkfifo"), "POSIX fifo unavailable")
    def test_fifo_refused_without_block(self):
        fifo=self.root/"fifo"; os.mkfifo(fifo)
        with self.assertRaises(m.ContractError): m.read_file(fifo)

    def test_oversized_file(self):
        self.input.write_bytes(b"x"*(m.MAX_BYTES+1))
        with self.assertRaises(m.ContractError): m.read_file(self.input)

    def test_cli_review_clear_verify_and_manifest(self):
        out=self.root/"out"
        result=self.cli("review",self.input,"--out-dir",out,"--as-of",AS_OF)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn("REVIEW_CLEAR",result.stdout)
        manifest=json.loads((out/"manifest.json").read_text())
        for filename,expected in manifest.items(): self.assertEqual(hashlib.sha256((out/filename).read_bytes()).hexdigest(),expected)
        verify=self.cli("verify",self.input,out/"report.json")
        self.assertEqual(verify.returncode,0,verify.stderr)
        self.assertEqual(verify.stdout.strip(),"VERIFIED_HISTORICAL_INTEGRITY_ONLY")

    def test_cli_hold_writes_diagnostic_exit_one(self):
        p=snapshot(); p["coverage"]["invoice_history"]="UNKNOWN"; self.input.write_bytes(m.canonical(p))
        out=self.root/"out"; result=self.cli("review",self.input,"--out-dir",out,"--as-of",AS_OF)
        self.assertEqual(result.returncode,1,result.stderr)
        self.assertTrue((out/"manifest.json").exists())

    def test_cli_invalid_exit_two_no_traceback(self):
        self.input.write_text('{"x":1,"x":2}')
        out=self.root/"out"; result=self.cli("review",self.input,"--out-dir",out,"--as-of",AS_OF)
        self.assertEqual(result.returncode,2)
        self.assertNotIn("Traceback",result.stderr)
        self.assertFalse(out.exists())

    def test_no_output_overwrite(self):
        out=self.root/"out"; out.mkdir(); sentinel=out/"report.json"; sentinel.write_text("DO NOT REPLACE")
        result=self.cli("review",self.input,"--out-dir",out,"--as-of",AS_OF)
        self.assertEqual(result.returncode,2)
        self.assertEqual(sentinel.read_text(),"DO NOT REPLACE")

    def test_output_symlink_refused(self):
        target=self.root/"target"; target.mkdir(); link=self.root/"out"; link.symlink_to(target,target_is_directory=True)
        result=self.cli("review",self.input,"--out-dir",link,"--as-of",AS_OF)
        self.assertEqual(result.returncode,2)
        self.assertEqual(list(target.iterdir()),[])

    def test_csv_formula_escaping_only_presentation(self):
        p=snapshot(); p["invoices"][0]["invoice_number"]="=1+1"
        r=m.compile_review(p,as_of=AS_OF)
        self.assertIn("'=1+1",m.csv_report(r).decode())
        self.assertEqual(r["invoices"][0]["invoice_number"],"=1+1")

    def test_cli_tamper_verify_refused(self):
        r=m.compile_review(snapshot(),as_of=AS_OF); r["authority"]["payment"]=True
        output=self.root/"report.json"; output.write_bytes(m.canonical(reseal(r)))
        result=self.cli("verify",self.input,output)
        self.assertEqual(result.returncode,2)
        self.assertNotIn("Traceback",result.stderr)

    def test_cli_process_clock_not_snapshot_time(self):
        out=self.root/"out"; before=datetime.now(timezone.utc)
        result=self.cli("review",self.input,"--out-dir",out)
        after=datetime.now(timezone.utc)
        self.assertIn(result.returncode,(0,1),result.stderr)
        report=json.loads((out/"report.json").read_text())
        observed=m.utc(report["evaluated_at"],"evaluated_at")
        self.assertLessEqual(before.replace(microsecond=0),observed)
        self.assertLessEqual(observed,after)


if __name__ == "__main__": unittest.main()
