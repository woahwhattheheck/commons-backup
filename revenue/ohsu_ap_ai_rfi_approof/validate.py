"""Strict APProof packet validation and semantic canonicalization."""
from __future__ import annotations
import json
from typing import Any
from .common import (
    APProofError, SCHEMA, canonical_json_bytes, currency, ident, integer,
    iso_date, list_, obj, source, string,
)

def _line(value: Any, name: str) -> dict[str, Any]:
    line = obj(
        value, name, {"line_id", "sku", "quantity", "unit_price_cents"},
        {"cost_center"},
    )
    ident(line["line_id"], f"{name}.line_id")
    ident(line["sku"], f"{name}.sku")
    integer(line["quantity"], f"{name}.quantity", lo=1, hi=10**9)
    integer(line["unit_price_cents"], f"{name}.unit_price_cents", hi=10**12)
    if "cost_center" in line:
        ident(line["cost_center"], f"{name}.cost_center")
    return line


def validate_packet(packet: Any) -> dict[str, Any]:
    p = obj(
        packet, "packet",
        {"schema", "as_of", "invoices", "purchase_orders", "receipts",
         "approvals", "supplier_statements"},
    )
    if p["schema"] != SCHEMA:
        raise APProofError(f"packet.schema must equal {SCHEMA}")
    iso_date(p["as_of"], "packet.as_of")
    invoices = list_(p["invoices"], "packet.invoices")
    pos = list_(p["purchase_orders"], "packet.purchase_orders")
    receipts = list_(p["receipts"], "packet.receipts")
    approvals = list_(p["approvals"], "packet.approvals")
    statements = list_(p["supplier_statements"], "packet.supplier_statements")
    if len(invoices) > 10000 or len(pos) > 10000 or len(receipts) > 50000:
        raise APProofError("packet collection limit exceeded")

    seen: set[str] = set()
    for i, raw in enumerate(invoices):
        n = f"invoice[{i}]"
        inv = obj(
            raw, n,
            {"invoice_id", "vendor_id", "invoice_number", "invoice_date",
             "currency", "total_cents", "po_id", "lines", "source_sha256"},
        )
        iid = ident(inv["invoice_id"], f"{n}.invoice_id")
        if iid in seen:
            raise APProofError("duplicate invoice_id")
        seen.add(iid)
        ident(inv["vendor_id"], f"{n}.vendor_id")
        string(inv["invoice_number"], f"{n}.invoice_number")
        iso_date(inv["invoice_date"], f"{n}.invoice_date")
        currency(inv["currency"], f"{n}.currency")
        integer(inv["total_cents"], f"{n}.total_cents")
        if inv["po_id"] is not None:
            ident(inv["po_id"], f"{n}.po_id")
        lines = list_(inv["lines"], f"{n}.lines")
        if not lines:
            raise APProofError(f"{n}.lines must be nonempty")
        lids: set[str] = set()
        computed = 0
        for j, raw_line in enumerate(lines):
            line = _line(raw_line, f"{n}.lines[{j}]")
            if line["line_id"] in lids:
                raise APProofError(f"{n} duplicate line_id")
            lids.add(line["line_id"])
            computed += line["quantity"] * line["unit_price_cents"]
            if computed > 10**15:
                raise APProofError(f"{n} line total overflow")
        if computed != inv["total_cents"]:
            raise APProofError(f"{n}.total_cents != sum(lines)")
        source(inv, n)

    seen = set()
    for i, raw in enumerate(pos):
        n = f"purchase_order[{i}]"
        po = obj(raw, n, {"po_id", "vendor_id", "currency", "lines", "source_sha256"})
        pid = ident(po["po_id"], f"{n}.po_id")
        if pid in seen:
            raise APProofError("duplicate po_id")
        seen.add(pid)
        ident(po["vendor_id"], f"{n}.vendor_id")
        currency(po["currency"], f"{n}.currency")
        lines = list_(po["lines"], f"{n}.lines")
        if not lines:
            raise APProofError(f"{n}.lines must be nonempty")
        lids: set[str] = set()
        for j, raw_line in enumerate(lines):
            line = _line(raw_line, f"{n}.lines[{j}]")
            if line["line_id"] in lids:
                raise APProofError(f"{n} duplicate line_id")
            lids.add(line["line_id"])
        source(po, n)

    seen = set()
    for i, raw in enumerate(receipts):
        n = f"receipt[{i}]"
        rec = obj(raw, n, {"receipt_id", "po_id", "line_id", "quantity", "source_sha256"})
        rid = ident(rec["receipt_id"], f"{n}.receipt_id")
        if rid in seen:
            raise APProofError("duplicate receipt_id")
        seen.add(rid)
        ident(rec["po_id"], f"{n}.po_id")
        ident(rec["line_id"], f"{n}.line_id")
        integer(rec["quantity"], f"{n}.quantity", lo=1, hi=10**9)
        source(rec, n)

    seen = set()
    for i, raw in enumerate(approvals):
        n = f"approval[{i}]"
        app = obj(raw, n, {"approval_id", "invoice_id", "status", "source_sha256"})
        aid = ident(app["approval_id"], f"{n}.approval_id")
        if aid in seen:
            raise APProofError("duplicate approval_id")
        seen.add(aid)
        ident(app["invoice_id"], f"{n}.invoice_id")
        if string(app["status"], f"{n}.status") not in {"APPROVED", "REJECTED", "PENDING"}:
            raise APProofError(f"{n}.status invalid")
        source(app, n)

    seen = set()
    for i, raw in enumerate(statements):
        n = f"supplier_statement[{i}]"
        st = obj(
            raw, n,
            {"statement_id", "vendor_id", "currency", "invoice_numbers",
             "statement_total_cents", "source_sha256"},
        )
        sid = ident(st["statement_id"], f"{n}.statement_id")
        if sid in seen:
            raise APProofError("duplicate statement_id")
        seen.add(sid)
        ident(st["vendor_id"], f"{n}.vendor_id")
        currency(st["currency"], f"{n}.currency")
        nums = [string(v, f"{n}.invoice_numbers") for v in list_(st["invoice_numbers"], f"{n}.invoice_numbers")]
        if len(nums) != len(set(nums)):
            raise APProofError(f"{n} duplicate invoice number")
        integer(st["statement_total_cents"], f"{n}.statement_total_cents")
        source(st, n)
    return p


def semantic_packet(packet: Any) -> dict[str, Any]:
    p = json.loads(canonical_json_bytes(validate_packet(packet)).decode("utf-8"))
    for inv in p["invoices"]:
        inv["lines"] = sorted(inv["lines"], key=lambda x: x["line_id"])
    for po in p["purchase_orders"]:
        po["lines"] = sorted(po["lines"], key=lambda x: x["line_id"])
    for st in p["supplier_statements"]:
        st["invoice_numbers"] = sorted(st["invoice_numbers"])
    p["invoices"] = sorted(p["invoices"], key=lambda x: x["invoice_id"])
    p["purchase_orders"] = sorted(p["purchase_orders"], key=lambda x: x["po_id"])
    p["receipts"] = sorted(p["receipts"], key=lambda x: x["receipt_id"])
    p["approvals"] = sorted(p["approvals"], key=lambda x: x["approval_id"])
    p["supplier_statements"] = sorted(p["supplier_statements"], key=lambda x: x["statement_id"])
    return p
