#!/usr/bin/env python3
"""Dependency-free purchase-order and invoice reconciliation operator."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import unicodedata
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path


SCHEMA = "commons-purchasing-paperwork-v1"
ACCOUNTING_FIELDS = [
    "invoice_number",
    "invoice_date",
    "due_date",
    "supplier_id",
    "po_number",
    "po_line",
    "sku",
    "description",
    "quantity",
    "unit_price",
    "line_total",
    "currency",
    "status",
    "invoice_source",
    "invoice_source_sha256",
    "po_source",
    "po_source_sha256",
]


class PurchasingError(ValueError):
    """Raised when input data cannot be reconciled safely."""


def _decimal(value: str, field: str, *, positive: bool = False) -> Decimal:
    try:
        number = Decimal(value)
    except (InvalidOperation, TypeError) as exc:
        raise PurchasingError(f"{field} must be a decimal") from exc
    minimum = Decimal("0.0000001") if positive else Decimal("0")
    if not number.is_finite() or number < minimum:
        comparator = "> 0" if positive else ">= 0"
        raise PurchasingError(f"{field} must be finite and {comparator}")
    return number


def _money(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")), "f")


def _quantity(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _name_key(value: str) -> str:
    # Canonical equivalence is not transliteration: accents and script marks
    # still distinguish vendors; case and punctuation retain their old folding.
    canonical = unicodedata.normalize("NFC", value)
    folded = unicodedata.normalize("NFC", canonical.casefold())
    separated = "".join(
        char if char.isalnum() or unicodedata.category(char).startswith("M") else " "
        for char in folded
    )
    return " ".join(word for word in separated.split() if any(char.isalnum() for char in word))


def _source(path: Path) -> dict[str, str]:
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise PurchasingError(f"cannot read {path}: {exc}") from exc
    return {"path": str(path), "sha256": digest}


def _read_csv(path: Path, required: set[str]) -> list[dict[str, str]]:
    try:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.reader(handle, strict=True)
            fields = next(reader, [])
            if any(not field.strip() for field in fields):
                raise PurchasingError(f"{path}: blank column names are not allowed")
            if len(fields) != len(set(fields)):
                raise PurchasingError(f"{path}: duplicate columns are not allowed")
            if "_line" in fields:
                raise PurchasingError(f"{path}: reserved column _line is not allowed")
            missing = required - set(fields)
            if missing:
                raise PurchasingError(f"{path}: missing columns {sorted(missing)}")
            rows = []
            while True:
                # Capture the start, not the end, of a quoted multiline record.
                line = reader.line_num + 1
                try:
                    values = next(reader)
                except StopIteration:
                    break
                if not values:
                    continue
                if len(values) != len(fields):
                    raise PurchasingError(
                        f"{path}:{line}: expected {len(fields)} columns, got {len(values)}"
                    )
                normalized = {key: value.strip() for key, value in zip(fields, values)}
                normalized["_line"] = str(line)
                rows.append(normalized)
            return rows
    except (csv.Error, UnicodeError) as exc:
        raise PurchasingError(f"{path}: invalid CSV: {exc}") from exc
    except OSError as exc:
        raise PurchasingError(f"cannot read {path}: {exc}") from exc


@dataclass(frozen=True)
class Vendor:
    supplier_id: str
    canonical_name: str
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class POLine:
    po_number: str
    po_line: str
    supplier_id: str
    po_date: str
    currency: str
    sku: str
    description: str
    quantity: Decimal
    unit_price: Decimal
    source_line: int


@dataclass(frozen=True)
class InvoiceLine:
    invoice_number: str
    line_number: str
    vendor_name: str
    invoice_date: str
    due_date: str
    currency: str
    po_number: str
    po_line: str
    sku: str
    description: str
    quantity: Decimal
    unit_price: Decimal
    source_line: int


def load_vendors(path: Path) -> tuple[dict[str, Vendor], dict[str, set[str]]]:
    rows = _read_csv(path, {"supplier_id", "canonical_name", "aliases"})
    vendors: dict[str, Vendor] = {}
    names: dict[str, set[str]] = {}
    for row in rows:
        supplier_id = row["supplier_id"]
        if not supplier_id or supplier_id in vendors:
            raise PurchasingError(f"{path}:{row['_line']}: blank or duplicate supplier_id")
        aliases = tuple(value.strip() for value in row["aliases"].split("|") if value.strip())
        vendor = Vendor(supplier_id, row["canonical_name"], aliases)
        if not vendor.canonical_name:
            raise PurchasingError(f"{path}:{row['_line']}: canonical_name is required")
        vendors[supplier_id] = vendor
        for name in (vendor.canonical_name, *vendor.aliases):
            key = _name_key(name)
            if key:
                names.setdefault(key, set()).add(supplier_id)
    return vendors, names


def load_purchase_orders(path: Path) -> dict[tuple[str, str], POLine]:
    rows = _read_csv(
        path,
        {"po_number", "po_line", "supplier_id", "po_date", "currency", "sku", "description", "quantity", "unit_price"},
    )
    result: dict[tuple[str, str], POLine] = {}
    for row in rows:
        key = (row["po_number"], row["po_line"])
        if not all(key) or key in result:
            raise PurchasingError(f"{path}:{row['_line']}: blank or duplicate PO line {key}")
        result[key] = POLine(
            po_number=key[0],
            po_line=key[1],
            supplier_id=row["supplier_id"],
            po_date=row["po_date"],
            currency=row["currency"].upper(),
            sku=row["sku"],
            description=row["description"],
            quantity=_decimal(row["quantity"], f"{key}.quantity", positive=True),
            unit_price=_decimal(row["unit_price"], f"{key}.unit_price"),
            source_line=int(row["_line"]),
        )
    return result


def load_invoices(path: Path) -> list[InvoiceLine]:
    rows = _read_csv(
        path,
        {"invoice_number", "line_number", "vendor_name", "invoice_date", "due_date", "currency", "po_number", "po_line", "sku", "description", "quantity", "unit_price"},
    )
    seen: set[tuple[str, str]] = set()
    result = []
    for row in rows:
        key = (row["invoice_number"], row["line_number"])
        if not all(key) or key in seen:
            raise PurchasingError(f"{path}:{row['_line']}: blank or duplicate invoice line {key}")
        seen.add(key)
        result.append(
            InvoiceLine(
                invoice_number=key[0], line_number=key[1], vendor_name=row["vendor_name"],
                invoice_date=row["invoice_date"], due_date=row["due_date"], currency=row["currency"].upper(),
                po_number=row["po_number"], po_line=row["po_line"], sku=row["sku"], description=row["description"],
                quantity=_decimal(row["quantity"], f"{key}.quantity", positive=True),
                unit_price=_decimal(row["unit_price"], f"{key}.unit_price"), source_line=int(row["_line"]),
            )
        )
    return result


def _draft(line: InvoiceLine, issues: list[str], invoice_ref: dict[str, str], po_ref: dict[str, str] | None) -> dict[str, object]:
    issue_text = ", ".join(issues)
    sources = [{**invoice_ref, "line": line.source_line}]
    if po_ref:
        sources.append(po_ref)
    return {
        "draft_id": f"{line.invoice_number}-line-{line.line_number}",
        "status": "DRAFT_NOT_SENT",
        "invoice_number": line.invoice_number,
        "invoice_line": line.line_number,
        "issues": issues,
        "subject": f"Review needed: invoice {line.invoice_number}, line {line.line_number}",
        "body": f"Please review invoice {line.invoice_number}, line {line.line_number}: {issue_text}. No posting has been made.",
        "recommended_action": "review sources, correct or approve, then rerun reconciliation",
        "sources": sources,
    }


def reconcile(
    vendors: dict[str, Vendor], names: dict[str, set[str]], purchase_orders: dict[tuple[str, str], POLine],
    invoices: list[InvoiceLine], *, vendors_source: dict[str, str], po_source: dict[str, str], invoice_source: dict[str, str],
) -> tuple[dict[str, object], list[dict[str, str]], list[dict[str, object]]]:
    records: list[dict[str, object]] = []
    accounting: list[dict[str, str]] = []
    drafts: list[dict[str, object]] = []
    # Matching is full-line, not a partial-invoice allocation or payment ledger.
    # Review every repeated reference rather than choosing an order-dependent winner.
    po_uses = Counter((line.po_number, line.po_line) for line in invoices)

    for line in invoices:
        candidates = sorted(names.get(_name_key(line.vendor_name), set()))
        issues: list[str] = []
        supplier_id = candidates[0] if len(candidates) == 1 else ""
        if not candidates:
            issues.append("vendor_unmatched")
        elif len(candidates) > 1:
            issues.append("vendor_ambiguous:" + "|".join(candidates))

        po = purchase_orders.get((line.po_number, line.po_line))
        if po is None:
            issues.append("po_line_not_found")
        else:
            uses = po_uses[(line.po_number, line.po_line)]
            if uses > 1:
                issues.append(f"po_line_reused_in_batch:count={uses}")
            if supplier_id and supplier_id != po.supplier_id:
                issues.append(f"vendor_mismatch:invoice={supplier_id},po={po.supplier_id}")
            if line.currency != po.currency:
                issues.append(f"currency_mismatch:invoice={line.currency},po={po.currency}")
            if line.sku != po.sku:
                issues.append(f"sku_mismatch:invoice={line.sku},po={po.sku}")
            if line.quantity != po.quantity:
                issues.append(f"quantity_mismatch:invoice={_quantity(line.quantity)},po={_quantity(po.quantity)}")
            if line.unit_price != po.unit_price:
                issues.append(f"unit_price_mismatch:invoice={_money(line.unit_price)},po={_money(po.unit_price)}")

        status = "MATCHED_REVIEW_READY" if not issues else "EXCEPTION_REVIEW_REQUIRED"
        record = {
            "invoice_number": line.invoice_number, "invoice_line": line.line_number, "status": status,
            "supplier_id": supplier_id, "po_number": line.po_number, "po_line": line.po_line, "sku": line.sku,
            "quantity": _quantity(line.quantity), "unit_price": _money(line.unit_price),
            "line_total": _money(line.quantity * line.unit_price), "currency": line.currency, "issues": issues,
            "invoice_source": {**invoice_source, "line": line.source_line},
            "po_source": ({**po_source, "line": po.source_line} if po else None),
        }
        records.append(record)
        if issues:
            drafts.append(_draft(line, issues, {**invoice_source}, ({**po_source, "line": po.source_line} if po else None)))
            continue
        accounting.append(
            {
                "invoice_number": line.invoice_number, "invoice_date": line.invoice_date, "due_date": line.due_date,
                "supplier_id": supplier_id, "po_number": line.po_number, "po_line": line.po_line, "sku": line.sku,
                "description": line.description, "quantity": _quantity(line.quantity), "unit_price": _money(line.unit_price),
                "line_total": _money(line.quantity * line.unit_price), "currency": line.currency,
                "status": "REVIEW_READY_NOT_POSTED", "invoice_source": invoice_source["path"],
                "invoice_source_sha256": invoice_source["sha256"], "po_source": po_source["path"],
                "po_source_sha256": po_source["sha256"],
            }
        )

    report = {
        "schema": SCHEMA,
        "status": "RECONCILED_NOT_POSTED",
        "sources": {"vendors": vendors_source, "purchase_orders": po_source, "invoices": invoice_source},
        "summary": {
            "invoice_lines": len(invoices), "matched_lines": len(accounting), "exception_lines": len(drafts),
            "accounting_rows_posted": 0, "drafts_sent": 0,
        },
        "records": records,
    }
    return report, accounting, drafts


def _check_output_paths(inputs: tuple[Path, ...], outputs: tuple[Path, ...]) -> None:
    """Detect existing aliases before writes; this is not a filesystem lock."""
    def identity(path: Path):
        resolved = path.resolve()
        try:
            info = path.stat()
        except FileNotFoundError:
            inode = None
        else:
            inode = (info.st_dev, info.st_ino)
        return resolved, inode

    try:
        sources = [(path, *identity(path)) for path in inputs]
        targets = [(path, *identity(path)) for path in outputs]
    except (OSError, RuntimeError) as exc:
        raise PurchasingError(f"cannot inspect output paths: {exc}") from exc

    for index, (target, resolved, inode) in enumerate(targets):
        for source, source_resolved, source_inode in sources:
            if resolved == source_resolved or (inode is not None and inode == source_inode):
                raise PurchasingError(f"output {target} overlaps input {source}")
        for previous, previous_resolved, previous_inode in targets[:index]:
            if resolved == previous_resolved or (inode is not None and inode == previous_inode):
                raise PurchasingError(f"output {target} overlaps output {previous}")


def run(vendors_path: Path, po_path: Path, invoice_path: Path, out_dir: Path) -> dict[str, Path]:
    report_path = out_dir / "reconciliation.json"
    accounting_path = out_dir / "accounting_import.csv"
    drafts_path = out_dir / "exception_drafts.json"
    _check_output_paths(
        (vendors_path, po_path, invoice_path), (report_path, accounting_path, drafts_path),
    )
    vendor_ref, po_ref, invoice_ref = _source(vendors_path), _source(po_path), _source(invoice_path)
    vendors, names = load_vendors(vendors_path)
    report, accounting, drafts = reconcile(
        vendors, names, load_purchase_orders(po_path), load_invoices(invoice_path),
        vendors_source=vendor_ref, po_source=po_ref, invoice_source=invoice_ref,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    drafts_path.write_text(json.dumps({"schema": SCHEMA, "drafts": drafts}, indent=2) + "\n", encoding="utf-8")
    with accounting_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=ACCOUNTING_FIELDS)
        writer.writeheader()
        writer.writerows(accounting)
    return {"report": report_path, "accounting": accounting_path, "drafts": drafts_path}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vendors", type=Path, required=True)
    parser.add_argument("--purchase-orders", type=Path, required=True)
    parser.add_argument("--invoices", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        paths = run(args.vendors, args.purchase_orders, args.invoices, args.out_dir)
    except PurchasingError as exc:
        parser.exit(2, f"error: {exc}\n")
    print(json.dumps({key: str(value) for key, value in paths.items()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
