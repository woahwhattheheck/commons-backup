#!/usr/bin/env python3
"""Dependency-free supplier reorder planning and receipt application."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable


SCHEMA = "commons-supplier-reorder-v1"


class ReorderError(ValueError):
    """Raised when an input cannot produce a trustworthy draft."""


def _decimal(value: str, field: str, *, minimum: Decimal = Decimal("0")) -> Decimal:
    try:
        parsed = Decimal(value)
    except (InvalidOperation, TypeError) as exc:
        raise ReorderError(f"{field} must be a decimal") from exc
    if not parsed.is_finite() or parsed < minimum:
        raise ReorderError(f"{field} must be finite and >= {minimum}")
    return parsed


def _integer(value: str, field: str, *, minimum: int = 0) -> int:
    number = _decimal(value, field, minimum=Decimal(minimum))
    if number != number.to_integral_value():
        raise ReorderError(f"{field} must be an integer")
    return int(number)


def _money(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")), "f")


def _read_csv(path: Path, required: set[str]) -> list[dict[str, str]]:
    try:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.reader(handle, strict=True)
            fieldnames = next(reader, [])
            fields = set(fieldnames)
            missing = required - fields
            if missing:
                raise ReorderError(f"{path}: missing columns {sorted(missing)}")
            if any(not field.strip() for field in fieldnames):
                raise ReorderError(f"{path}: blank column name")
            seen: set[str] = set()
            duplicates: set[str] = set()
            for field in fieldnames:
                if field in seen:
                    duplicates.add(field)
                seen.add(field)
            if duplicates:
                raise ReorderError(f"{path}: duplicate column names {sorted(duplicates)}")
            rows = []
            while True:
                # Capture the start before parsing: one CSV record may span
                # several physical lines, and blank records still consume one.
                line = reader.line_num + 1
                try:
                    values = next(reader)
                except StopIteration:
                    break
                except csv.Error as exc:
                    raise ReorderError(f"cannot read {path}:{line}: {exc}") from exc
                if not values:
                    continue
                if len(values) > len(fieldnames):
                    raise ReorderError(f"{path}:{line}: extra field(s) beyond the header")
                if len(values) < len(fieldnames):
                    absent = fieldnames[len(values):]
                    raise ReorderError(f"{path}:{line}: missing field(s) {absent}")
                normalized = {key: value.strip() for key, value in zip(fieldnames, values)}
                normalized["_line"] = str(line)
                rows.append(normalized)
            return rows
    except (OSError, UnicodeError, csv.Error) as exc:
        raise ReorderError(f"cannot read {path}: {exc}") from exc


@dataclass(frozen=True)
class Stock:
    sku: str
    name: str
    on_hand: int
    on_order: int
    allocated: int
    unit: str

    @property
    def position(self) -> int:
        return self.on_hand + self.on_order - self.allocated


@dataclass(frozen=True)
class Rule:
    sku: str
    reorder_at: int
    target_stock: int
    preferred_supplier: str


@dataclass(frozen=True)
class Offer:
    supplier_id: str
    supplier_sku: str
    sku: str
    description: str
    unit_cost: Decimal
    available_qty: int
    lead_days: int
    alternative_for_sku: str


def load_stock(path: Path) -> dict[str, Stock]:
    rows = _read_csv(path, {"sku", "name", "on_hand", "on_order", "allocated", "unit"})
    result: dict[str, Stock] = {}
    for row in rows:
        sku = row["sku"]
        if not sku or sku in result:
            raise ReorderError(f"{path}:{row['_line']}: blank or duplicate sku {sku!r}")
        result[sku] = Stock(
            sku=sku,
            name=row["name"],
            on_hand=_integer(row["on_hand"], f"{sku}.on_hand"),
            on_order=_integer(row["on_order"], f"{sku}.on_order"),
            allocated=_integer(row["allocated"], f"{sku}.allocated"),
            unit=row["unit"],
        )
    return result


def load_rules(path: Path) -> dict[str, Rule]:
    rows = _read_csv(path, {"sku", "reorder_at", "target_stock", "preferred_supplier"})
    result: dict[str, Rule] = {}
    for row in rows:
        sku = row["sku"]
        if not sku or sku in result:
            raise ReorderError(f"{path}:{row['_line']}: blank or duplicate rule sku {sku!r}")
        reorder_at = _integer(row["reorder_at"], f"{sku}.reorder_at")
        target = _integer(row["target_stock"], f"{sku}.target_stock")
        if target <= reorder_at:
            raise ReorderError(f"{sku}.target_stock must exceed reorder_at")
        result[sku] = Rule(sku, reorder_at, target, row["preferred_supplier"])
    return result


def load_catalog(path: Path) -> list[Offer]:
    rows = _read_csv(
        path,
        {
            "supplier_id",
            "supplier_sku",
            "sku",
            "description",
            "unit_cost",
            "available_qty",
            "lead_days",
            "alternative_for_sku",
        },
    )
    seen: set[tuple[str, str]] = set()
    offers = []
    for row in rows:
        key = (row["supplier_id"], row["supplier_sku"])
        if not all(key) or key in seen:
            raise ReorderError(f"{path}:{row['_line']}: blank or duplicate supplier item {key}")
        seen.add(key)
        offers.append(
            Offer(
                supplier_id=key[0],
                supplier_sku=key[1],
                sku=row["sku"],
                description=row["description"],
                unit_cost=_decimal(row["unit_cost"], f"{key}.unit_cost"),
                available_qty=_integer(row["available_qty"], f"{key}.available_qty"),
                lead_days=_integer(row["lead_days"], f"{key}.lead_days"),
                alternative_for_sku=row["alternative_for_sku"],
            )
        )
    return offers


def build_plan(
    stock: dict[str, Stock], rules: dict[str, Rule], offers: Iterable[Offer], as_of: str
) -> dict[str, object]:
    try:
        date.fromisoformat(as_of)
    except ValueError as exc:
        raise ReorderError("as_of must be an ISO date (YYYY-MM-DD)") from exc

    unknown_rules = sorted(set(rules) - set(stock))
    if unknown_rules:
        raise ReorderError(f"rules reference unknown stock skus: {unknown_rules}")

    exact: dict[str, list[Offer]] = defaultdict(list)
    alternatives: dict[str, list[Offer]] = defaultdict(list)
    for offer in offers:
        if offer.sku:
            exact[offer.sku].append(offer)
        if offer.alternative_for_sku:
            alternatives[offer.alternative_for_sku].append(offer)

    po_lines: dict[str, list[dict[str, object]]] = defaultdict(list)
    exceptions: list[dict[str, object]] = []
    evaluated: list[dict[str, object]] = []

    for sku in sorted(rules):
        item, rule = stock[sku], rules[sku]
        needed = max(0, rule.target_stock - item.position) if item.position <= rule.reorder_at else 0
        evaluated.append(
            {
                "sku": sku,
                "inventory_position": item.position,
                "reorder_at": rule.reorder_at,
                "target_stock": rule.target_stock,
                "requested_qty": needed,
            }
        )
        if not needed:
            continue

        candidates = sorted(
            exact.get(sku, []),
            key=lambda offer: (
                offer.supplier_id != rule.preferred_supplier,
                offer.unit_cost,
                offer.lead_days,
                offer.supplier_id,
                offer.supplier_sku,
            ),
        )
        remaining = needed
        for offer in candidates:
            quantity = min(remaining, offer.available_qty)
            if quantity <= 0:
                continue
            po_lines[offer.supplier_id].append(
                {
                    "sku": sku,
                    "supplier_sku": offer.supplier_sku,
                    "description": offer.description or item.name,
                    "quantity": quantity,
                    "unit": item.unit,
                    "unit_cost": _money(offer.unit_cost),
                    "line_total": _money(offer.unit_cost * quantity),
                }
            )
            remaining -= quantity
            if remaining == 0:
                break

        if remaining:
            suggestions = []
            for offer in sorted(
                alternatives.get(sku, []),
                key=lambda candidate: (
                    candidate.supplier_id != rule.preferred_supplier,
                    candidate.unit_cost,
                    candidate.lead_days,
                    candidate.supplier_id,
                    candidate.supplier_sku,
                ),
            ):
                if offer.available_qty <= 0:
                    continue
                suggestions.append(
                    {
                        "supplier_id": offer.supplier_id,
                        "supplier_sku": offer.supplier_sku,
                        "description": offer.description,
                        "available_qty": offer.available_qty,
                        "unit_cost": _money(offer.unit_cost),
                        "lead_days": offer.lead_days,
                        "requires_approval": True,
                    }
                )
            exceptions.append(
                {
                    "sku": sku,
                    "unfilled_qty": remaining,
                    "reason": "exact_item_unavailable",
                    "alternative_suggestions": suggestions,
                    "action": "review_required_no_order_created",
                }
            )

    purchase_orders = []
    for supplier in sorted(po_lines):
        lines = sorted(po_lines[supplier], key=lambda line: (str(line["sku"]), str(line["supplier_sku"])))
        total = sum((Decimal(str(line["line_total"])) for line in lines), Decimal("0"))
        purchase_orders.append(
            {
                "draft_id": f"DRAFT-{as_of.replace('-', '')}-{supplier}",
                "supplier_id": supplier,
                "status": "DRAFT_NOT_SENT",
                "lines": lines,
                "total": _money(total),
            }
        )

    return {
        "schema": SCHEMA,
        "as_of": as_of,
        "purchase_orders": purchase_orders,
        "exceptions": exceptions,
        "evaluated": evaluated,
        "summary": {
            "draft_purchase_orders": len(purchase_orders),
            "draft_lines": sum(len(order["lines"]) for order in purchase_orders),
            "review_required": len(exceptions),
            "orders_sent": 0,
        },
    }


def _receipt_record(row: dict[str, object]) -> dict[str, object]:
    """Normalize business fields; CSV line numbers are not receipt identity."""
    if not isinstance(row, dict):
        raise ReorderError("receipt must be an object")
    record: dict[str, object] = {}
    for field in ("receipt_id", "received_at", "supplier_id", "supplier_sku", "sku"):
        value = row.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ReorderError(f"receipt {field} must be nonblank text")
        record[field] = value.strip()
    record["quantity"] = _integer(
        str(row.get("quantity", "")), f"{record['receipt_id']}.quantity", minimum=1
    )
    return record


def _plan_sha256(plan: dict[str, object]) -> str:
    """Bind cumulative receipts to the saved plan, not a reused draft ID."""
    try:
        encoded = json.dumps(plan, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ReorderError("plan must contain finite JSON values") from exc
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _drafted_quantities(plan: object) -> dict[tuple[str, str, str], int]:
    """Validate the imported draft before any receipt is applied."""
    if not isinstance(plan, dict):
        raise ReorderError("plan must be an object")
    if plan.get("schema") != SCHEMA:
        raise ReorderError("plan schema is not supported")
    orders = plan.get("purchase_orders", [])
    if not isinstance(orders, list):
        raise ReorderError("plan.purchase_orders must be an array")

    def identifier(value: object, field: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ReorderError(f"{field} must be a nonblank string")
        return value

    drafted: dict[tuple[str, str, str], int] = {}
    for order_index, order in enumerate(orders):
        order_field = f"plan.purchase_orders[{order_index}]"
        if not isinstance(order, dict):
            raise ReorderError(f"{order_field} must be an object")
        supplier = identifier(order.get("supplier_id"), f"{order_field}.supplier_id")
        lines = order.get("lines")
        if not isinstance(lines, list):
            raise ReorderError(f"{order_field}.lines must be an array")
        for line_index, line in enumerate(lines):
            line_field = f"{order_field}.lines[{line_index}]"
            if not isinstance(line, dict):
                raise ReorderError(f"{line_field} must be an object")
            supplier_sku = identifier(line.get("supplier_sku"), f"{line_field}.supplier_sku")
            sku = identifier(line.get("sku"), f"{line_field}.sku")
            value = line.get("quantity")
            if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
                raise ReorderError(f"{line_field}.quantity must be an integer")
            quantity = _integer(value, f"{line_field}.quantity", minimum=1)
            key = (supplier, supplier_sku, sku)
            drafted[key] = drafted.get(key, 0) + quantity
    return drafted


def apply_receipts(
    stock: dict[str, Stock],
    plan: dict[str, object],
    receipt_rows: list[dict[str, str]],
    *,
    pipeline_includes_draft: bool = False,
    prior_log: dict[str, object] | None = None,
) -> tuple[dict[str, Stock], dict[str, object]]:
    if type(pipeline_includes_draft) is not bool:
        raise ReorderError("pipeline_includes_draft must be a boolean")
    drafted = _drafted_quantities(plan)

    plan_sha256 = _plan_sha256(plan)
    updated = dict(stock)
    applied: list[dict[str, object]] = []
    history: dict[str, dict[str, object]] = {}
    cumulative: dict[tuple[str, str, str], int] = defaultdict(int)
    if prior_log is not None:
        if not isinstance(prior_log, dict) or prior_log.get("schema") != SCHEMA:
            raise ReorderError("prior log schema is not supported")
        version = prior_log.get("receipt_history_version")
        if type(version) is not int or version != 1:
            raise ReorderError("prior log must contain versioned receipt history")
        if prior_log.get("plan_sha256") != plan_sha256:
            raise ReorderError("prior log belongs to a different saved plan")
        prior_mode = prior_log.get("pipeline_includes_draft")
        if type(prior_mode) is not bool:
            raise ReorderError("prior log pipeline_includes_draft must be a boolean")
        if prior_mode != pipeline_includes_draft:
            raise ReorderError("prior log pipeline mode does not match this receipt run")
        prior_rows = prior_log.get("applied_receipts")
        if not isinstance(prior_rows, list):
            raise ReorderError("prior log applied_receipts must be a list")
        for prior_row in prior_rows:
            record = _receipt_record(prior_row)
            receipt_id = record["receipt_id"]
            if receipt_id in history:
                raise ReorderError(f"prior log has duplicate receipt_id {receipt_id!r}")
            key = (record["supplier_id"], record["supplier_sku"], record["sku"])
            if key not in drafted:
                raise ReorderError(f"{receipt_id}: prior receipt item was not present in the draft plan")
            cumulative[key] += record["quantity"]
            if cumulative[key] > drafted[key]:
                raise ReorderError(f"{receipt_id}: prior received quantity exceeds drafted quantity")
            history[receipt_id] = record
            applied.append(record)

    previous_count = len(applied)
    replayed: list[str] = []
    seen_receipts: set[str] = set()
    for row in receipt_rows:
        record = _receipt_record(row)
        receipt_id = record["receipt_id"]
        if receipt_id in seen_receipts:
            raise ReorderError(f"blank or duplicate receipt_id {receipt_id!r}")
        seen_receipts.add(receipt_id)
        if receipt_id in history:
            if record != history[receipt_id]:
                raise ReorderError(f"{receipt_id}: receipt conflicts with prior history")
            replayed.append(receipt_id)
            continue
        key = (record["supplier_id"], record["supplier_sku"], record["sku"])
        quantity = record["quantity"]
        if key not in drafted:
            raise ReorderError(f"{receipt_id}: receipt item was not present in the draft plan")
        cumulative[key] += quantity
        if cumulative[key] > drafted[key]:
            raise ReorderError(f"{receipt_id}: received quantity exceeds drafted quantity")
        if key[2] not in updated:
            raise ReorderError(f"{receipt_id}: unknown stock sku {key[2]}")
        item = updated[key[2]]
        updated[key[2]] = Stock(
            sku=item.sku,
            name=item.name,
            on_hand=item.on_hand + quantity,
            # Drafting never adds units to the imported pipeline. Decrement
            # only when the caller confirms its newer export already did.
            on_order=max(0, item.on_order - quantity) if pipeline_includes_draft else item.on_order,
            allocated=item.allocated,
            unit=item.unit,
        )
        applied.append(record)
    return updated, {
        "schema": SCHEMA,
        "receipt_history_version": 1,
        "plan_sha256": plan_sha256,
        "applied_receipts": applied,
        "count": len(applied),
        "new_count": len(applied) - previous_count,
        "replayed_receipt_ids": replayed,
        "pipeline_includes_draft": pipeline_includes_draft,
    }


def write_stock(path: Path, stock: dict[str, Stock]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["sku", "name", "on_hand", "on_order", "allocated", "unit"])
        writer.writeheader()
        for sku in sorted(stock):
            item = stock[sku]
            writer.writerow(item.__dict__)


def command_plan(args: argparse.Namespace) -> None:
    plan = build_plan(load_stock(args.stock), load_rules(args.rules), load_catalog(args.catalog), args.as_of)
    args.out.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def command_receive(args: argparse.Namespace) -> None:
    # The CSV and JSON are separate deliverables. Resolve spelling/symlink
    # aliases and existing hardlinks before either output can be truncated.
    same_output = args.out_stock.resolve() == args.out_log.resolve()
    if not same_output and args.out_stock.exists() and args.out_log.exists():
        same_output = args.out_stock.samefile(args.out_log)
    if same_output:
        raise ReorderError("receipt stock and log outputs must refer to different files")
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    prior_path = getattr(args, "prior_log", None)
    try:
        prior_log = json.loads(prior_path.read_text(encoding="utf-8")) if prior_path is not None else None
    except UnicodeError as exc:
        raise ReorderError(f"cannot read prior log {prior_path}: {exc}") from exc
    if prior_path is not None and not isinstance(prior_log, dict):
        raise ReorderError("prior log must be a JSON object")
    receipts = _read_csv(
        args.receipts,
        {"receipt_id", "received_at", "supplier_id", "supplier_sku", "sku", "quantity"},
    )
    updated, log = apply_receipts(
        load_stock(args.stock),
        plan,
        receipts,
        pipeline_includes_draft=args.pipeline_includes_draft,
        prior_log=prior_log,
    )
    write_stock(args.out_stock, updated)
    args.out_log.write_text(json.dumps(log, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan", help="create unsent draft purchase orders")
    plan.add_argument("--stock", type=Path, required=True)
    plan.add_argument("--rules", type=Path, required=True)
    plan.add_argument("--catalog", type=Path, required=True)
    plan.add_argument("--as-of", required=True, help="ISO date used in deterministic draft IDs")
    plan.add_argument("--out", type=Path, required=True)
    plan.set_defaults(func=command_plan)

    receive = sub.add_parser("receive", help="apply supplier receipts to stock")
    receive.add_argument("--stock", type=Path, required=True)
    receive.add_argument("--plan", type=Path, required=True)
    receive.add_argument("--receipts", type=Path, required=True)
    receive.add_argument("--out-stock", type=Path, required=True)
    receive.add_argument("--out-log", type=Path, required=True)
    receive.add_argument(
        "--prior-log",
        type=Path,
        help="cumulative receipt log already reflected in --stock for this exact saved plan",
    )
    receive.add_argument(
        "--pipeline-includes-draft",
        action="store_true",
        help="decrement on_order because the imported stock already includes this draft",
    )
    receive.set_defaults(func=command_receive)
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        args.func(args)
    except (ReorderError, OSError, json.JSONDecodeError) as exc:
        parser().error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
