"""Offline AP batch reconciliation. Standard library only; never posts or pays.

Accept a normalized export, compare candidate invoices plus prior consumption
against order/receipt capacities, and produce an exception queue. A clear result
means only that the supplied snapshot satisfies the documented review rules.
It neither authenticates source exports nor proves completeness or ERP execution.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from datetime import date, datetime, timezone
import hashlib
import hmac
import io
import json
import os
from pathlib import Path
import re
import stat
import sys
import unicodedata
from typing import Any

VERSION = "ap-batch-review/1.0"
MAX_BYTES = 4_000_000
MAX_NODES = 180_000
MAX_DEPTH = 20
MAX_ROWS = 5_000
MAX_INT = 9_007_199_254_740_991
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
UTC_TEXT = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")


class ContractError(ValueError):
    """Malformed, ambiguous, oversized, or unsupported input."""


def _error(message: str) -> None:
    raise ContractError(message)


def _admit(value: Any) -> None:
    """Bound canonical serialization work, including repeated shared objects."""
    nodes, budget = 0, 0
    active: set[int] = set()

    def walk(obj: Any, depth: int) -> None:
        nonlocal nodes, budget
        nodes += 1
        if nodes > MAX_NODES or depth > MAX_DEPTH:
            _error("JSON depth/node limit exceeded")
        kind = type(obj)
        if kind is str:
            if len(obj) > MAX_BYTES:
                _error("JSON scalar too large")
            try:
                encoded = obj.encode("utf-8")
            except UnicodeError as exc:
                raise ContractError("invalid Unicode scalar") from exc
            # Exact JSON UTF-8 size: quotes/backslash/control escaping.
            budget += 2 + len(encoded)
            for char in obj:
                n = ord(char)
                if char in ('"', '\\') or char in ('\b', '\t', '\n', '\f', '\r'):
                    budget += 1
                elif n < 32:
                    budget += 5
        elif kind is int:
            if abs(obj) > MAX_INT:
                _error("integer exceeds exact supported range")
            budget += len(str(obj))
        elif kind is bool:
            budget += 4 if obj else 5
        elif obj is None:
            budget += 4
        elif kind is dict or kind is list:
            identity = id(obj)
            if identity in active:
                _error("cyclic input")
            if len(obj) > MAX_NODES:
                _error("oversized container")
            active.add(identity)
            budget += 2 + max(0, len(obj) - 1)
            if kind is dict:
                budget += len(obj)  # colons
                for key, child in obj.items():
                    if type(key) is not str:
                        _error("object keys must be exact strings")
                    walk(key, depth + 1)
                    walk(child, depth + 1)
            else:
                for child in obj:
                    walk(child, depth + 1)
            active.remove(identity)
        else:
            _error("only exact JSON types are supported; floats/subclasses rejected")
        if budget > MAX_BYTES:
            _error("canonical JSON byte-work limit exceeded")

    walk(value, 0)


def canonical(value: Any) -> bytes:
    _admit(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def load_json(raw: bytes | str) -> Any:
    if (type(raw) is not bytes and type(raw) is not str) or len(raw) > MAX_BYTES:
        _error("input must be bounded UTF-8 JSON")
    try:
        text = raw.decode("utf-8") if type(raw) is bytes else raw
        if len(text.encode("utf-8")) > MAX_BYTES:
            _error("input exceeds byte limit")
    except UnicodeError as exc:
        raise ContractError("invalid UTF-8") from exc

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        obj: dict[str, Any] = {}
        for key, val in items:
            if key in obj:
                _error("duplicate JSON key")
            obj[key] = val
        return obj

    def integer(token: str) -> int:
        if len(token.lstrip("-")) > 16:
            _error("integer token too large")
        val = int(token)
        if abs(val) > MAX_INT:
            _error("integer token outside supported range")
        return val

    try:
        value = json.loads(text, object_pairs_hook=pairs, parse_int=integer,
                           parse_float=lambda _: _error("decimal JSON numbers unsupported"),
                           parse_constant=lambda _: _error("nonfinite JSON unsupported"))
    except (ValueError, RecursionError) as exc:
        if isinstance(exc, ContractError):
            raise
        raise ContractError("invalid or excessively nested JSON") from exc
    _admit(value)
    return value


def obj(value: Any, keys: str, label: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != set(keys.split()):
        _error(label + ": exact object keys required")
    return value


def text(value: Any, label: str, limit: int = 128) -> str:
    if type(value) is not str or not value.strip() or len(value) > limit:
        _error(label + ": nonempty bounded text required")
    if any(unicodedata.category(c).startswith("C") for c in value):
        _error(label + ": control/format characters unsupported")
    if value != value.strip():
        _error(label + ": leading/trailing whitespace unsupported")
    return value


def number(value: Any, label: str, minimum: int = 0, maximum: int = MAX_INT) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        _error(label + ": exact bounded integer required")
    return value


def choice(value: Any, allowed: tuple[str, ...], label: str) -> str:
    if type(value) is not str or value not in allowed:
        _error(label + ": unsupported value")
    return value


def rows(value: Any, label: str, *, nonempty: bool = False) -> list[Any]:
    if type(value) is not list or len(value) > MAX_ROWS or (nonempty and not value):
        _error(label + ": bounded list required")
    return value


def utc(value: Any, label: str) -> datetime:
    if type(value) is not str or not UTC_TEXT.fullmatch(value):
        _error(label + ": whole-second UTC required")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ContractError(label + ": invalid calendar time") from exc


def unique(items: list[Any], key: str, label: str) -> None:
    seen: set[str] = set()
    for item in items:
        identity = text(item[key], label + "." + key)
        if identity in seen:
            _error(label + ": duplicate identity")
        seen.add(identity)


def amount(quantity: int, unit_price: int) -> int:
    """Half-up at a line boundary. Quantity is thousandths of the stated UOM."""
    product = quantity * unit_price
    sign = -1 if product < 0 else 1
    result = sign * ((abs(product) + 500) // 1000)
    if abs(result) > MAX_INT:
        _error("computed line amount exceeds supported range")
    return result


def invoice_key(supplier: str, invoice_number: str) -> tuple[str, str]:
    # Conservative possible-duplicate comparison: preserve punctuation/digits.
    normalized = " ".join(unicodedata.normalize("NFKC", invoice_number).split()).casefold()
    return supplier, normalized


def validate(packet: Any) -> dict[str, Any]:
    _admit(packet)
    obj(packet, "schema_version entity_id snapshot_id captured_at coverage currency_scales policy purchase_orders receipts history invoices", "packet")
    number(packet["schema_version"], "schema_version", 1, 1)
    for key in ("entity_id", "snapshot_id"):
        text(packet[key], key)
    utc(packet["captured_at"], "captured_at")
    obj(packet["coverage"], "po_register receipt_register invoice_history", "coverage")
    for key, value in packet["coverage"].items():
        choice(value, ("COMPLETE", "PARTIAL", "UNKNOWN"), "coverage." + key)
    scales = packet["currency_scales"]
    if type(scales) is not dict or not scales or len(scales) > 20:
        _error("currency_scales must declare 1..20 currency codes")
    for code, scale in scales.items():
        if not re.fullmatch(r"[A-Z]{3}", code):
            _error("currency must be three uppercase letters")
        number(scale, "currency scale", 0, 4)
    obj(packet["policy"], "quantity_tolerance_milliunits price_tolerance_minor max_snapshot_age_seconds", "policy")
    number(packet["policy"]["quantity_tolerance_milliunits"], "quantity tolerance", 0, 1_000_000)
    number(packet["policy"]["price_tolerance_minor"], "price tolerance", 0, 1_000_000)
    number(packet["policy"]["max_snapshot_age_seconds"], "snapshot age", 1, 604_800)

    def currency(row: dict[str, Any]) -> None:
        if type(row["currency"]) is not str or row["currency"] not in scales:
            _error("currency has no explicit scale declaration")

    def sha(row: dict[str, Any]) -> None:
        if type(row["document_sha256"]) is not str or not HEX64.fullmatch(row["document_sha256"]):
            _error("document_sha256 must be lowercase SHA-256")

    def allocations(value: Any) -> None:
        for allocation in rows(value, "receipt allocations"):
            obj(allocation, "receipt_id quantity_milliunits", "receipt allocation")
            text(allocation["receipt_id"], "receipt_id")
            number(allocation["quantity_milliunits"], "receipt quantity", 1)
        unique(value, "receipt_id", "receipt allocations")

    for po in rows(packet["purchase_orders"], "purchase_orders"):
        obj(po, "po_line_id supplier_id currency uom quantity_milliunits unit_price_minor status match_mode source_ref", "PO")
        for key in ("po_line_id", "supplier_id", "uom", "source_ref"):
            text(po[key], "PO." + key)
        currency(po)
        number(po["quantity_milliunits"], "PO quantity", 1)
        number(po["unit_price_minor"], "PO price", 0)
        choice(po["status"], ("OPEN", "CLOSED"), "PO status")
        choice(po["match_mode"], ("TWO_WAY", "THREE_WAY"), "PO match_mode")
    unique(packet["purchase_orders"], "po_line_id", "PO")
    for row in rows(packet["receipts"], "receipts"):
        obj(row, "receipt_id po_line_id quantity_milliunits source_ref", "receipt")
        for key in ("receipt_id", "po_line_id", "source_ref"):
            text(row[key], "receipt." + key)
        number(row["quantity_milliunits"], "received quantity", 0)
    unique(packet["receipts"], "receipt_id", "receipts")
    for row in rows(packet["history"], "history"):
        obj(row, "invoice_id supplier_id invoice_number currency document_sha256 allocations", "history")
        for key in ("invoice_id", "supplier_id", "invoice_number"):
            text(row[key], "history." + key)
        currency(row)
        sha(row)
        for alloc in rows(row["allocations"], "history allocations"):
            obj(alloc, "allocation_id po_line_id quantity_milliunits net_minor receipts", "history allocation")
            text(alloc["allocation_id"], "allocation_id")
            text(alloc["po_line_id"], "historical PO line")
            number(alloc["quantity_milliunits"], "historical quantity", 1)
            number(alloc["net_minor"], "historical amount")
            allocations(alloc["receipts"])
        unique(row["allocations"], "allocation_id", "history allocations")
    unique(packet["history"], "invoice_id", "history")
    for inv in rows(packet["invoices"], "invoices", nonempty=True):
        obj(inv, "invoice_id supplier_id invoice_number currency document_sha256 invoice_date document_type approval net_total_minor tax_minor freight_minor other_minor gross_total_minor lines", "invoice")
        for key in ("invoice_id", "supplier_id", "invoice_number"):
            text(inv[key], key)
        currency(inv)
        sha(inv)
        if type(inv["invoice_date"]) is not str or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", inv["invoice_date"]):
            _error("invoice_date must be YYYY-MM-DD")
        try:
            date.fromisoformat(inv["invoice_date"])
        except ValueError as exc:
            raise ContractError("invalid invoice date") from exc
        choice(inv["document_type"], ("INVOICE", "CREDIT"), "document_type")
        choice(inv["approval"], ("APPROVED", "PENDING", "REJECTED"), "approval")
        minimum = -MAX_INT if inv["document_type"] == "CREDIT" else 0
        for key in ("net_total_minor", "tax_minor", "freight_minor", "other_minor", "gross_total_minor"):
            number(inv[key], key, minimum)
        for line in rows(inv["lines"], "invoice lines", nonempty=True):
            obj(line, "line_id po_line_id uom quantity_milliunits unit_price_minor net_minor receipts", "invoice line")
            text(line["line_id"], "line_id")
            if line["po_line_id"] is not None:
                text(line["po_line_id"], "po_line_id")
            text(line["uom"], "uom")
            number(line["quantity_milliunits"], "line quantity", minimum if minimum else 1)
            number(line["unit_price_minor"], "line price")
            number(line["net_minor"], "line amount", minimum)
            allocations(line["receipts"])
        unique(inv["lines"], "line_id", "invoice lines")
    unique(packet["invoices"], "invoice_id", "candidate invoices")
    # Canonical ordering for tables/sets; caller objects remain unchanged.
    result = json.loads(canonical(packet))
    for table, key in (("purchase_orders", "po_line_id"), ("receipts", "receipt_id"), ("history", "invoice_id"), ("invoices", "invoice_id")):
        result[table].sort(key=lambda r: r[key])
    for inv in result["invoices"]:
        inv["lines"].sort(key=lambda r: r["line_id"])
        for line in inv["lines"]:
            line["receipts"].sort(key=lambda r: r["receipt_id"])
    for inv in result["history"]:
        inv["allocations"].sort(key=lambda r: r["allocation_id"])
        for alloc in inv["allocations"]:
            alloc["receipts"].sort(key=lambda r: r["receipt_id"])
    return result


def compile_review(packet: Any, *, as_of: str) -> dict[str, Any]:
    """Review a snapshot at an explicit time; no claim of independently verified data."""
    p = validate(packet)
    evaluated = utc(as_of, "as_of")
    captured = utc(p["captured_at"], "captured_at")
    snapshot_issues: set[str] = set()
    if captured > evaluated:
        snapshot_issues.add("FUTURE_SNAPSHOT")
    elif (evaluated - captured).total_seconds() > p["policy"]["max_snapshot_age_seconds"]:
        snapshot_issues.add("STALE_SNAPSHOT")
    if any(v != "COMPLETE" for v in p["coverage"].values()):
        snapshot_issues.add("INCOMPLETE_DECLARED_COVERAGE")
    pos = {r["po_line_id"]: r for r in p["purchase_orders"]}
    receipts = {r["receipt_id"]: r for r in p["receipts"]}
    for rec in receipts.values():
        if rec["po_line_id"] not in pos:
            _error("receipt references a missing PO line")
    hist_qty: dict[str, int] = defaultdict(int)
    hist_net: dict[str, int] = defaultdict(int)
    hist_rec: dict[str, int] = defaultdict(int)
    historical_keys: set[tuple[str, str]] = set()
    historical_docs: set[str] = set()
    historical_ids: set[str] = set()
    for inv in p["history"]:
        key = invoice_key(inv["supplier_id"], inv["invoice_number"])
        if key in historical_keys or inv["document_sha256"] in historical_docs:
            snapshot_issues.add("POSSIBLE_DUPLICATE_IN_HISTORY")
        historical_keys.add(key)
        historical_docs.add(inv["document_sha256"])
        historical_ids.add(inv["invoice_id"])
        for alloc in inv["allocations"]:
            po = pos.get(alloc["po_line_id"])
            if po is None or (po["supplier_id"], po["currency"]) != (inv["supplier_id"], inv["currency"]):
                _error("historical allocation has missing or mismatched PO identity")
            hist_qty[po["po_line_id"]] += alloc["quantity_milliunits"]
            hist_net[po["po_line_id"]] += alloc["net_minor"]
            allocated = 0
            for ref in alloc["receipts"]:
                rec = receipts.get(ref["receipt_id"])
                if rec is None or rec["po_line_id"] != po["po_line_id"]:
                    _error("historical receipt allocation has missing or mismatched identity")
                allocated += ref["quantity_milliunits"]
                hist_rec[rec["receipt_id"]] += ref["quantity_milliunits"]
            if (po["match_mode"] == "THREE_WAY" or alloc["receipts"]) and allocated != alloc["quantity_milliunits"]:
                _error("historical receipt quantities do not reconcile")

    candidate_qty: dict[str, int] = defaultdict(int)
    candidate_net: dict[str, int] = defaultdict(int)
    candidate_rec: dict[str, int] = defaultdict(int)
    po_users: dict[str, set[str]] = defaultdict(set)
    rec_users: dict[str, set[str]] = defaultdict(set)
    issues: dict[str, set[str]] = {inv["invoice_id"]: set() for inv in p["invoices"]}
    key_users: dict[tuple[str, str], list[str]] = defaultdict(list)
    doc_users: dict[str, list[str]] = defaultdict(list)
    qtol = p["policy"]["quantity_tolerance_milliunits"]
    ptol = p["policy"]["price_tolerance_minor"]
    for inv in p["invoices"]:
        identity = inv["invoice_id"]
        problem = issues[identity]
        key = invoice_key(inv["supplier_id"], inv["invoice_number"])
        key_users[key].append(identity)
        doc_users[inv["document_sha256"]].append(identity)
        if key in historical_keys or inv["document_sha256"] in historical_docs or identity in historical_ids:
            problem.add("POSSIBLE_DUPLICATE_HISTORY")
        if inv["approval"] != "APPROVED":
            problem.add("APPROVAL_" + inv["approval"])
        if date.fromisoformat(inv["invoice_date"]) > captured.date():
            problem.add("INVOICE_AFTER_SNAPSHOT")
        if sum(r["net_minor"] for r in inv["lines"]) != inv["net_total_minor"]:
            problem.add("NET_HEADER_MISMATCH")
        if sum(inv[k] for k in ("net_total_minor", "tax_minor", "freight_minor", "other_minor")) != inv["gross_total_minor"]:
            problem.add("GROSS_HEADER_MISMATCH")
        if inv["document_type"] == "CREDIT":
            # No offsetting a charge with an unlinked credit. Preserve it visibly.
            problem.add("CREDIT_REQUIRES_LINKED_REVIEW")
            continue
        for line in inv["lines"]:
            if amount(line["quantity_milliunits"], line["unit_price_minor"]) != line["net_minor"]:
                problem.add("LINE_ARITHMETIC_MISMATCH")
            if line["po_line_id"] is None:
                problem.add("NON_PO_REQUIRES_REVIEW")
                continue
            po = pos.get(line["po_line_id"])
            if po is None:
                problem.add("MISSING_PO")
                continue
            if (po["supplier_id"], po["currency"], po["uom"]) != (inv["supplier_id"], inv["currency"], line["uom"]):
                problem.add("PO_IDENTITY_MISMATCH")
                continue  # Never add values across unlike currencies or UOMs.
            if po["status"] != "OPEN":
                problem.add("PO_CLOSED")
            if line["unit_price_minor"] > po["unit_price_minor"] + ptol:
                problem.add("UNIT_PRICE_EXCEEDED")
            po_id = po["po_line_id"]
            candidate_qty[po_id] += line["quantity_milliunits"]
            candidate_net[po_id] += line["net_minor"]
            po_users[po_id].add(identity)
            allocated = 0
            for ref in line["receipts"]:
                rec = receipts.get(ref["receipt_id"])
                if rec is None:
                    problem.add("MISSING_RECEIPT")
                    continue
                if rec["po_line_id"] != po_id:
                    problem.add("RECEIPT_PO_MISMATCH")
                    continue
                allocated += ref["quantity_milliunits"]
                candidate_rec[rec["receipt_id"]] += ref["quantity_milliunits"]
                rec_users[rec["receipt_id"]].add(identity)
            if (po["match_mode"] == "THREE_WAY" or line["receipts"]) and allocated != line["quantity_milliunits"]:
                problem.add("RECEIPT_ALLOCATION_MISMATCH")
    for group in list(key_users.values()) + list(doc_users.values()):
        if len(group) > 1:
            for identity in group:
                issues[identity].add("POSSIBLE_DUPLICATE_BATCH")

    capacities = []
    for po_id, po in pos.items():
        qty_limit = po["quantity_milliunits"] + qtol
        money_limit = amount(qty_limit, po["unit_price_minor"] + ptol)
        if hist_qty[po_id] > qty_limit or hist_net[po_id] > money_limit:
            snapshot_issues.add("HISTORY_PO_OVERALLOCATED")
        if hist_qty[po_id] + candidate_qty[po_id] > qty_limit:
            for identity in po_users[po_id]:
                issues[identity].add("PO_QUANTITY_OVERCOMMITTED")
        if hist_net[po_id] + candidate_net[po_id] > money_limit:
            for identity in po_users[po_id]:
                issues[identity].add("PO_AMOUNT_OVERCOMMITTED")
        capacities.append({"po_line_id": po_id, "currency": po["currency"],
                           "quantity_limit_milliunits": qty_limit,
                           "historical_quantity_milliunits": hist_qty[po_id],
                           "candidate_quantity_milliunits": candidate_qty[po_id],
                           "net_limit_minor": money_limit,
                           "historical_net_minor": hist_net[po_id],
                           "candidate_net_minor": candidate_net[po_id]})
    receipt_capacities = []
    for rec_id, rec in receipts.items():
        # Receipts have a *hard* physical ceiling; PO quantity tolerance does not
        # get multiplied by the count of receipt records.
        limit = rec["quantity_milliunits"]
        if hist_rec[rec_id] > limit:
            snapshot_issues.add("HISTORY_RECEIPT_OVERALLOCATED")
        if hist_rec[rec_id] + candidate_rec[rec_id] > limit:
            for identity in rec_users[rec_id]:
                issues[identity].add("RECEIPT_OVERCOMMITTED")
        receipt_capacities.append({"receipt_id": rec_id, "quantity_limit_milliunits": limit,
                                   "historical_quantity_milliunits": hist_rec[rec_id],
                                   "candidate_quantity_milliunits": candidate_rec[rec_id]})
    summary: dict[str, dict[str, int]] = {}
    output_rows = []
    for inv in p["invoices"]:
        reasons = sorted(issues[inv["invoice_id"]] | snapshot_issues)
        state = "HOLD_REVIEW" if reasons else "REVIEW_CLEAR"
        curr = inv["currency"]
        totals = summary.setdefault(curr, {"scale": p["currency_scales"][curr],
                                          "submitted_gross_minor": 0,
                                          "held_gross_minor": 0,
                                          "review_clear_gross_minor": 0})
        totals["submitted_gross_minor"] += inv["gross_total_minor"]
        bucket = "held_gross_minor" if reasons else "review_clear_gross_minor"
        totals[bucket] += inv["gross_total_minor"]
        output_rows.append({"invoice_id": inv["invoice_id"], "supplier_id": inv["supplier_id"],
                            "invoice_number": inv["invoice_number"], "currency": curr,
                            "gross_total_minor": inv["gross_total_minor"], "state": state,
                            "reasons": reasons, "invoice_sha256": digest(inv)})
    result = {"schema_version": 1, "engine_version": VERSION, "entity_id": p["entity_id"],
              "snapshot_id": p["snapshot_id"], "captured_at": p["captured_at"], "evaluated_at": as_of,
              "input_sha256": digest(p), "declared_coverage": p["coverage"],
              "state": "HOLD_REVIEW" if any(r["reasons"] for r in output_rows) else "REVIEW_CLEAR",
              "snapshot_issues": sorted(snapshot_issues), "invoices": output_rows,
              "po_capacities": capacities, "receipt_capacities": receipt_capacities,
              "summary_by_currency": summary,
              "evidence_class": "SUPPLIED_SNAPSHOT_RECONCILIATION_ONLY",
              "authority": {"erp_write": False, "payment": False, "submission": False,
                            "outbound": False, "revenue_recognition": False,
                            "source_authenticated": False, "completeness_proven": False}}
    result["receipt_sha256"] = digest(result)
    return result


def verify_report(packet: Any, report: Any) -> bool:
    """Recompile exact historical report, not current freshness or provider truth."""
    _admit(report)
    if type(report) is not dict or "evaluated_at" not in report:
        _error("report has no evaluation time")
    expected = compile_review(packet, as_of=report["evaluated_at"])
    if not hmac.compare_digest(canonical(expected), canonical(report)):
        _error("report differs from exact recomputation")
    return True


def read_file(path: Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
                _error("input must be a bounded regular file")
            data = stream.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                _error("input grew beyond limit")
            return data
    except OSError as exc:
        raise ContractError("cannot read regular input file: " + str(exc)) from exc


def csv_report(report: dict[str, Any]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["invoice_id", "supplier_id", "invoice_number", "currency", "gross_total_minor", "state", "reasons"])
    for row in report["invoices"]:
        cells = [row[k] for k in ("invoice_id", "supplier_id", "invoice_number", "currency", "gross_total_minor", "state")]
        cells.append(";".join(row["reasons"]))
        # Numeric values stay numeric; user-controlled spreadsheet formula text
        # is neutralized only in CSV presentation, never in the canonical data.
        writer.writerow(["'" + x if type(x) is str and x.startswith(("=", "+", "-", "@")) else x for x in cells])
    return output.getvalue().encode("utf-8")


def write_bundle(path: Path, report: dict[str, Any]) -> None:
    json_data = canonical(report) + b"\n"
    queue = csv_report(report)
    manifest = {"report.json": hashlib.sha256(json_data).hexdigest(),
                "exceptions.csv": hashlib.sha256(queue).hexdigest()}
    # A fresh output directory prevents silent replacement or symlink writes.
    os.mkdir(path, mode=0o700)
    for name, data in (("report.json", json_data), ("exceptions.csv", queue),
                       ("manifest.json", canonical(manifest) + b"\n")):
        fd = os.open(path / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
    # manifest.json is deliberately last; incomplete output has no manifest.


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    review = commands.add_parser("review", help="review a normalized export")
    review.add_argument("snapshot", type=Path)
    review.add_argument("--out-dir", type=Path, required=True)
    review.add_argument("--as-of", help="explicit historical/scenario UTC; defaults to process UTC")
    verify = commands.add_parser("verify", help="verify exact historical report")
    verify.add_argument("snapshot", type=Path)
    verify.add_argument("report", type=Path)
    args = parser.parse_args(argv)
    try:
        packet = load_json(read_file(args.snapshot))
        if args.command == "verify":
            verify_report(packet, load_json(read_file(args.report)))
            print("VERIFIED_HISTORICAL_INTEGRITY_ONLY")
            return 0
        as_of = args.as_of or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        report = compile_review(packet, as_of=as_of)
        write_bundle(args.out_dir, report)
        print(report["state"], report["receipt_sha256"])
        return 1 if report["state"] == "HOLD_REVIEW" else 0
    except (ContractError, OSError) as exc:
        print("ERROR:", str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
