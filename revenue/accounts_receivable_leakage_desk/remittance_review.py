"""Offline explicit-remittance review. No posting, matching guesses, or network I/O.

This sidecar consumes remaining-balance snapshots, not the aging engine's raw
invoice/event ledger. All allocation outputs are proposals for human review.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import stat
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any

SCHEMA = "ar-explicit-remittance/v1"
REPORT_SCHEMA = "ar-explicit-remittance-review/v1"
MAX_BYTES = 8 * 1024 * 1024
MAX_ARTIFACT_BYTES = 32 * 1024 * 1024
MAX_MINOR = 10**15
LIMITS = {"invoices": 5000, "payments": 10000, "allocations": 20000}
COLUMNS = {
    "invoices": ("snapshot_id", "invoice_id", "account_id", "currency", "issue_date", "remaining_minor", "status", "source_event_id"),
    "payments": ("snapshot_id", "payment_id", "account_id", "currency", "received_date", "available_minor", "source_event_id"),
    "allocations": ("snapshot_id", "allocation_id", "payment_id", "invoice_id", "amount_minor", "remittance_ref"),
}
ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,63}\Z", re.ASCII)


class ReviewError(ValueError):
    """A stable, data-free validation failure suitable for CLI output."""


def _fail(code: str) -> None:
    raise ReviewError(code)


def _plain(value: Any, depth: int = 0, budget: list[int] | None = None) -> None:
    if budget is None:
        budget = [3000000]
    budget[0] -= 1
    if depth > 16 or budget[0] < 0:
        _fail("DOCUMENT_COMPLEXITY_LIMIT")
    kind = type(value)
    if kind is dict:
        for key, child in value.items():
            if type(key) is not str:
                _fail("NON_STRING_KEY")
            _plain(key, depth + 1, budget)
            _plain(child, depth + 1, budget)
    elif kind is list:
        for child in value:
            _plain(child, depth + 1, budget)
    elif kind is str:
        if len(value) > 256:
            _fail("STRING_LENGTH_LIMIT")
        try:
            value.encode("utf-8")
        except UnicodeError:
            _fail("INVALID_UNICODE")
    elif kind is int:
        # Aggregate totals may exceed a single row, but remain exact Python ints.
        if abs(value) > MAX_MINOR * 20000:
            _fail("INTEGER_LIMIT")
    elif value is not None and kind is not bool:
        _fail("NON_PLAIN_JSON_VALUE")


def canonical(value: Any) -> bytes:
    _plain(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _number(text: str) -> int:
    if len(text) > 20:
        _fail("INTEGER_TOKEN_LIMIT")
    return int(text)


def _no_number(_: str) -> None:
    _fail("FLOAT_OR_NONFINITE_FORBIDDEN")


def loads(raw: bytes, *, artifact: bool = False) -> Any:
    if type(raw) is not bytes:
        _fail("BYTES_REQUIRED")
    if len(raw) > (MAX_ARTIFACT_BYTES if artifact else MAX_BYTES):
        _fail("DOCUMENT_BYTE_LIMIT")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_int=_number,
                           parse_float=_no_number, parse_constant=_no_number)
        _plain(value)
        return value
    except ReviewError:
        raise
    except (UnicodeError, ValueError, TypeError, RecursionError, OverflowError):
        raise ReviewError("INVALID_JSON") from None


def _keys(obj: Any, expected: set[str]) -> None:
    if type(obj) is not dict or set(obj) != expected:
        _fail("SCHEMA_KEYS_MISMATCH")


def _identifier(value: Any) -> str:
    if type(value) is not str or not ID_PATTERN.fullmatch(value):
        _fail("OPAQUE_IDENTIFIER_REQUIRED")
    return value


def _day(value: Any) -> str:
    if type(value) is not str or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        _fail("CANONICAL_DATE_REQUIRED")
    try:
        if date.fromisoformat(value).isoformat() != value:
            _fail("CANONICAL_DATE_REQUIRED")
    except ValueError:
        raise ReviewError("CANONICAL_DATE_REQUIRED") from None
    return value


def _minor(value: Any, *, positive: bool = False) -> int:
    if type(value) is not int or not (int(positive) <= value <= MAX_MINOR):
        _fail("MINOR_UNIT_INTEGER_REQUIRED")
    return value


def normalize(packet: Any) -> dict[str, Any]:
    _plain(packet)
    _keys(packet, {"schema", "snapshot_id", "analysis_date", "currency", *COLUMNS})
    if packet["schema"] != SCHEMA or type(packet["schema"]) is not str:
        _fail("SCHEMA_VERSION_MISMATCH")
    snapshot = _identifier(packet["snapshot_id"])
    horizon = _day(packet["analysis_date"])
    if packet["currency"] != "USD":
        _fail("USD_ONLY_NO_FX")
    result = {"schema": SCHEMA, "snapshot_id": snapshot, "analysis_date": horizon, "currency": "USD"}
    for kind, columns in COLUMNS.items():
        rows = packet[kind]
        if type(rows) is not list or len(rows) > LIMITS[kind]:
            _fail("ROW_LIMIT_OR_ARRAY_TYPE")
        identities: set[str] = set()
        native: set[str] = set()
        key = {"invoices": "invoice_id", "payments": "payment_id", "allocations": "allocation_id"}[kind]
        cleaned = []
        for row in rows:
            _keys(row, set(columns))
            if row["snapshot_id"] != snapshot:
                _fail("ROW_SNAPSHOT_MISMATCH")
            for field in columns:
                if field.endswith("_id") or field == "remittance_ref":
                    _identifier(row[field])
            if row[key] in identities:
                _fail("DUPLICATE_STABLE_ID")
            identities.add(row[key])
            if kind != "allocations":
                if row["currency"] != "USD":
                    _fail("USD_ONLY_NO_FX")
                if row["source_event_id"] in native:
                    _fail("DUPLICATE_SOURCE_EVENT")
                native.add(row["source_event_id"])
            if kind == "invoices":
                _day(row["issue_date"])
                _minor(row["remaining_minor"])
                if row["status"] not in ("OPEN", "DISPUTED", "VOID", "CONFLICT"):
                    _fail("INVOICE_STATUS_UNKNOWN")
            elif kind == "payments":
                _day(row["received_date"])
                _minor(row["available_minor"])
            else:
                _minor(row["amount_minor"], positive=True)
            cleaned.append(dict(row))
        result[kind] = sorted(cleaned, key=lambda row: row[key])
    if len(canonical(result)) > MAX_BYTES:
        _fail("DOCUMENT_BYTE_LIMIT")
    return result


def from_csv(snapshot_id: str, analysis_date: str, inputs: dict[str, bytes]) -> dict[str, Any]:
    _keys(inputs, set(COLUMNS))
    packet: dict[str, Any] = {"schema": SCHEMA, "snapshot_id": snapshot_id,
                              "analysis_date": analysis_date, "currency": "USD"}
    if sum(len(raw) for raw in inputs.values() if type(raw) is bytes) > MAX_BYTES:
        _fail("DOCUMENT_BYTE_LIMIT")
    for kind, columns in COLUMNS.items():
        raw = inputs[kind]
        if type(raw) is not bytes or len(raw) > MAX_BYTES:
            _fail("CSV_BYTES_REQUIRED")
        try:
            reader = csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""), strict=True)
            header = next(reader, None)
            if header is None or len(header) != len(set(header)) or set(header) != set(columns):
                _fail("CSV_HEADER_MISMATCH")
            rows = []
            for values in reader:
                if len(values) != len(header):
                    _fail("CSV_RAGGED_ROW")
                row: dict[str, Any] = dict(zip(header, values))
                for key in ("remaining_minor", "available_minor", "amount_minor"):
                    if key in row:
                        text = row[key]
                        if not re.fullmatch(r"0|[1-9][0-9]{0,15}", text, flags=re.ASCII):
                            _fail("CSV_INTEGER_REQUIRED")
                        row[key] = int(text)
                rows.append(row)
                if len(rows) > LIMITS[kind]:
                    _fail("ROW_LIMIT_OR_ARRAY_TYPE")
            packet[kind] = rows
        except ReviewError:
            raise
        except (csv.Error, UnicodeError, ValueError, TypeError):
            raise ReviewError("INVALID_CSV") from None
    return normalize(packet)


def compile_review(packet: Any) -> dict[str, Any]:
    source = normalize(packet)
    invoices = {r["invoice_id"]: r for r in source["invoices"]}
    payments = {r["payment_id"]: r for r in source["payments"]}
    rows = source["allocations"]
    parent: dict[tuple[str, str], tuple[str, str]] = {}

    def find(node: tuple[str, str]) -> tuple[str, str]:
        parent.setdefault(node, node)
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(a: tuple[str, str], b: tuple[str, str]) -> None:
        a, b = find(a), find(b)
        if a != b:
            parent[max(a, b)] = min(a, b)

    for row in rows:
        union(("PAYMENT", row["payment_id"]), ("INVOICE", row["invoice_id"]))
    for value in payments:
        find(("PAYMENT", value))
    for value in invoices:
        find(("INVOICE", value))
    nodes: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)
    for node in sorted(parent):
        nodes[find(node)].append(node)
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for root, members in nodes.items():
        groups[root] = {"component_id": digest(canonical([list(n) for n in members])),
                        "payment_ids": [n[1] for n in members if n[0] == "PAYMENT"],
                        "invoice_ids": [n[1] for n in members if n[0] == "INVOICE"], "findings": []}

    def issue(kind: str, key: str, code: str) -> None:
        group = groups[find((kind, key))]
        finding = {"code": code, "row_kind": kind, "row_id": key}
        group["findings"].append(finding)

    for key, inv in invoices.items():
        if inv["status"] != "OPEN":
            issue("INVOICE", key, "INVOICE_" + inv["status"])
        if inv["issue_date"] > source["analysis_date"]:
            issue("INVOICE", key, "INVOICE_AFTER_HORIZON")
    for key, pay in payments.items():
        if pay["received_date"] > source["analysis_date"]:
            issue("PAYMENT", key, "PAYMENT_AFTER_HORIZON")
    payment_requested: Counter[str] = Counter()
    invoice_requested: Counter[str] = Counter()
    pair_counts = Counter((r["payment_id"], r["invoice_id"]) for r in rows)
    for row in rows:
        p, i = row["payment_id"], row["invoice_id"]
        payment_requested[p] += row["amount_minor"]
        invoice_requested[i] += row["amount_minor"]
        group = groups[find(("PAYMENT", p))]
        codes = []
        if p not in payments:
            codes.append("UNKNOWN_PAYMENT")
        if i not in invoices:
            codes.append("UNKNOWN_INVOICE")
        if pair_counts[p, i] > 1:
            codes.append("DUPLICATE_PAIR_REVIEW")
        if p in payments and i in invoices:
            if payments[p]["account_id"] != invoices[i]["account_id"]:
                codes.append("ACCOUNT_MISMATCH")
            if payments[p]["received_date"] < invoices[i]["issue_date"]:
                codes.append("PRE_INVOICE_RECEIPT_REVIEW")
        for code in codes:
            group["findings"].append({"code": code, "row_kind": "ALLOCATION", "row_id": row["allocation_id"]})
    for key, amount in payment_requested.items():
        if key in payments and amount > payments[key]["available_minor"]:
            issue("PAYMENT", key, "PAYMENT_OVER_ALLOCATED")
    for key, amount in invoice_requested.items():
        if key in invoices and amount > invoices[key]["remaining_minor"]:
            issue("INVOICE", key, "INVOICE_OVER_ALLOCATED")
    for group in groups.values():
        group["findings"].sort(key=lambda r: (r["row_kind"], r["row_id"], r["code"]))
        group["state"] = "REVIEW_HOLD" if group["findings"] else "CONSISTENT_PROPOSAL_ONLY"
    allocations = []
    proposed_payments: Counter[str] = Counter()
    proposed_invoices: Counter[str] = Counter()
    for row in rows:
        group = groups[find(("PAYMENT", row["payment_id"]))]
        proposed = 0 if group["findings"] else row["amount_minor"]
        proposed_payments[row["payment_id"]] += proposed
        proposed_invoices[row["invoice_id"]] += proposed
        allocations.append({**row, "component_id": group["component_id"],
                            "state": "REVIEW_HOLD" if group["findings"] else "PROPOSED_ONLY",
                            "proposed_minor": proposed})
    payment_rows = []
    for key, row in payments.items():
        group = groups[find(("PAYMENT", key))]
        proposal = proposed_payments[key]
        payment_rows.append({**row, "component_id": group["component_id"],
                             "state": group["state"], "requested_minor": payment_requested[key],
                             "proposed_minor": proposal,
                             "hypothetical_unapplied_minor": row["available_minor"] - proposal})
    invoice_rows = []
    for key, row in invoices.items():
        group = groups[find(("INVOICE", key))]
        proposal = proposed_invoices[key]
        invoice_rows.append({**row, "component_id": group["component_id"],
                             "review_state": group["state"], "requested_minor": invoice_requested[key],
                             "proposed_minor": proposal,
                             "hypothetical_remaining_minor": row["remaining_minor"] - proposal})
    available = sum(r["available_minor"] for r in payment_rows)
    remaining = sum(r["remaining_minor"] for r in invoice_rows)
    proposed = sum(r["proposed_minor"] for r in allocations)
    # These are explicit runtime invariants, not assertions disabled by python -O.
    if (proposed != sum(proposed_payments.values()) or proposed != sum(proposed_invoices.values())
            or available - proposed != sum(r["hypothetical_unapplied_minor"] for r in payment_rows)
            or remaining - proposed != sum(r["hypothetical_remaining_minor"] for r in invoice_rows)):
        _fail("INTERNAL_CONSERVATION_FAILURE")
    body = {"schema": REPORT_SCHEMA, "snapshot_id": source["snapshot_id"],
            "analysis_date": source["analysis_date"], "currency": "USD",
            "evidence_class": "OWNER_SUPPLIED_SNAPSHOT_UNAUTHENTICATED",
            "mode": "ANALYTICAL_PROPOSAL_NOT_POSTED",
            "input_sha256": digest(canonical(source)),
            "authority": {"posting": False, "customer_contact": False, "funds_movement": False,
                          "source_authentication": False, "accounting_conclusion": False, "revenue_recognition": False},
            "totals": {"source_payment_available_minor": available, "source_invoice_remaining_minor": remaining,
                       "proposed_minor": proposed, "hypothetical_unapplied_minor": available - proposed,
                       "hypothetical_remaining_minor": remaining - proposed},
            "components": sorted(groups.values(), key=lambda r: r["component_id"]),
            "allocations": allocations, "payments": payment_rows, "invoices": invoice_rows}
    return {**body, "receipt_sha256": digest(canonical(body))}


def verify_review(packet: Any, report: Any) -> bool:
    expected = compile_review(packet)
    if canonical(report) != canonical(expected):
        _fail("REPORT_RECOMPILE_MISMATCH")
    return True


def _csv_bytes(columns: tuple[str, ...], rows: list[dict[str, Any]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(columns)
    writer.writerows([row[key] for key in columns] for row in rows)
    return stream.getvalue().encode("utf-8")


def render(report: dict[str, Any]) -> dict[str, bytes]:
    a = ("allocation_id", "payment_id", "invoice_id", "amount_minor", "proposed_minor", "state", "remittance_ref", "component_id")
    p = ("payment_id", "account_id", "available_minor", "requested_minor", "proposed_minor", "hypothetical_unapplied_minor", "state", "component_id")
    i = ("invoice_id", "account_id", "remaining_minor", "requested_minor", "proposed_minor", "hypothetical_remaining_minor", "review_state", "component_id")
    t = report["totals"]
    lines = ["# Explicit remittance review", "", "**PROPOSALS ONLY — nothing posted or collected.**", "",
             f"Snapshot: `{report['snapshot_id']}`. Analytical horizon: {report['analysis_date']}. USD integer cents.",
             "Owner-supplied evidence is not authenticated or proven complete. No live balance is asserted.", "",
             "| Quantity | Minor units (USD cents) |", "| --- | ---: |"]
    lines.extend(f"| {key} | {value} |" for key, value in t.items())
    lines += ["", "A consistent proposal still requires human review. Held components propose zero; source balances remain unchanged.",
              "", "## Findings", "", "| Component | Row kind | Row ID | Reason |", "| --- | --- | --- | --- |"]
    count = 0
    for group in report["components"]:
        for finding in group["findings"]:
            lines.append(f"| {group['component_id']} | {finding['row_kind']} | {finding['row_id']} | {finding['code']} |")
            count += 1
    if not count:
        lines.append("| — | — | — | No conflicts in supplied instructions |")
    lines += ["", "Unreferenced receipts remain in payments.csv. Unknown references remain in allocations.csv and the findings above.",
              "No FIFO, amount-only match, discount, write-off, reversal, FX, credit transfer, collection or posting is performed.",
              "", f"Receipt: `{report['receipt_sha256']}`", ""]
    return {"allocations.csv": _csv_bytes(a, report["allocations"]),
            "payments.csv": _csv_bytes(p, report["payments"]),
            "invoices.csv": _csv_bytes(i, report["invoices"]),
            "review.md": "\n".join(lines).encode("utf-8")}


def read_regular(path: Path, limit: int = MAX_ARTIFACT_BYTES) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            _fail("REGULAR_BOUNDED_FILE_REQUIRED")
        chunks = []
        total = 0
        while True:
            part = os.read(fd, min(65536, limit + 1 - total))
            if not part:
                break
            chunks.append(part)
            total += len(part)
            if total > limit:
                _fail("DOCUMENT_BYTE_LIMIT")
        after = os.fstat(fd)
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            _fail("INPUT_CHANGED_DURING_READ")
        return b"".join(chunks)
    finally:
        os.close(fd)


def bundle_members(packet: Any, raw_inputs: dict[str, bytes], source_format: str) -> dict[str, bytes]:
    normalized = normalize(packet)
    if source_format == "json":
        _keys(raw_inputs, {"input.json"})
        recovered = normalize(loads(raw_inputs["input.json"]))
    elif source_format == "csv":
        _keys(raw_inputs, {f"input_{kind}.csv" for kind in COLUMNS})
        recovered = from_csv(normalized["snapshot_id"], normalized["analysis_date"],
                             {kind: raw_inputs[f"input_{kind}.csv"] for kind in COLUMNS})
    else:
        _fail("SOURCE_FORMAT_UNKNOWN")
    if canonical(recovered) != canonical(normalized):
        _fail("RAW_SOURCE_MISMATCH")
    report = compile_review(normalized)
    members = {**raw_inputs, "source.json": canonical(normalized) + b"\n",
               "review.json": canonical(report) + b"\n", **render(report)}
    manifest = {"schema": "ar-remittance-bundle/v1", "source_format": source_format,
                "integrity_only_not_authentication": True,
                "members": [{"name": name, "sha256": digest(raw), "bytes": len(raw)}
                            for name, raw in sorted(members.items())]}
    members["manifest.json"] = canonical(manifest) + b"\n"
    return members


def write_bundle(destination: Path, members: dict[str, bytes]) -> None:
    # Exclusive directory, fixed member names, descriptor-relative writes. Manifest last.
    os.mkdir(destination, mode=0o700)
    dfd = os.open(destination, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
    try:
        generation = os.fstat(dfd)
        for name in sorted(members, key=lambda n: (n == "manifest.json", n)):
            if "/" in name or "\\" in name or name in (".", ".."):
                _fail("INVALID_BUNDLE_MEMBER")
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=dfd)
            with os.fdopen(fd, "wb") as stream:
                stream.write(members[name])
                stream.flush()
                os.fsync(stream.fileno())
        current = os.stat(destination, follow_symlinks=False)
        if (current.st_dev, current.st_ino) != (generation.st_dev, generation.st_ino):
            _fail("OUTPUT_DIRECTORY_CHANGED")
        os.fsync(dfd)
    finally:
        os.close(dfd)
    # Failed writes leave evidence in the exclusively created directory, never delete
    # unrelated paths. No success is printed unless the complete write returned.


def verify_bundle(directory: Path) -> bool:
    if directory.is_symlink() or not directory.is_dir():
        _fail("REGULAR_DIRECTORY_REQUIRED")
    manifest = loads(read_regular(directory / "manifest.json"), artifact=True)
    _keys(manifest, {"schema", "source_format", "integrity_only_not_authentication", "members"})
    source_format = manifest["source_format"]
    names = {"input.json"} if source_format == "json" else {f"input_{kind}.csv" for kind in COLUMNS}
    if source_format not in ("json", "csv"):
        _fail("SOURCE_FORMAT_UNKNOWN")
    packet = loads(read_regular(directory / "source.json", MAX_BYTES))
    raw_inputs = {name: read_regular(directory / name, MAX_BYTES) for name in names}
    expected = bundle_members(packet, raw_inputs, source_format)
    if set(os.listdir(directory)) != set(expected):
        _fail("BUNDLE_MEMBER_SET_MISMATCH")
    for name, raw in expected.items():
        if read_regular(directory / name) != raw:
            _fail("BUNDLE_RECOMPILE_MISMATCH")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    js = sub.add_parser("compile", help="Review a strict JSON snapshot")
    js.add_argument("--input", required=True, type=Path)
    js.add_argument("--out", required=True, type=Path)
    cs = sub.add_parser("compile-csv", help="Review three normalized CSV exports")
    cs.add_argument("--snapshot-id", required=True)
    cs.add_argument("--analysis-date", required=True)
    for kind in COLUMNS:
        cs.add_argument("--" + kind, required=True, type=Path)
    cs.add_argument("--out", required=True, type=Path)
    vb = sub.add_parser("verify-bundle", help="Recompile retained inputs and every review artifact")
    vb.add_argument("--directory", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "verify-bundle":
            verify_bundle(args.directory)
            print("VERIFIED_INTEGRITY_ONLY_NOT_AUTHENTICATED")
            return 0
        if args.command == "compile":
            raw_inputs = {"input.json": read_regular(args.input, MAX_BYTES)}
            packet = loads(raw_inputs["input.json"])
            source_format = "json"
        else:
            raw = {kind: read_regular(getattr(args, kind), MAX_BYTES) for kind in COLUMNS}
            packet = from_csv(args.snapshot_id, args.analysis_date, raw)
            raw_inputs = {f"input_{kind}.csv": value for kind, value in raw.items()}
            source_format = "csv"
        members = bundle_members(packet, raw_inputs, source_format)
        write_bundle(args.out, members)
        print("REVIEW_BUNDLE_CREATED_NO_POSTING")
        return 0
    except (ReviewError, OSError, ValueError, RecursionError, OverflowError) as exc:
        code = str(exc) if isinstance(exc, ReviewError) else "FILE_OR_RUNTIME_ERROR"
        print("ERROR: " + code, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
