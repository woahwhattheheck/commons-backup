#!/usr/bin/env python3
"""Unsent supplier-enquiry exports for the canonical Hive parts sourcing desk.

Consumes SPRUCE catalog rows. No network operations, orders, fit decisions,
catalog mutations, or database writes. Python standard library only.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import html
import json
import re
import sys
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

VERSION = 1
MAX_INPUT_BYTES = 5_000_000
MAX_ROWS = 500
class EnquiryError(ValueError):
    """Input cannot be rendered without losing its meaning."""

def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")

def sha(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()

def text(value: Any, name: str, *, required: bool = False, limit: int = 8000) -> str:
    if not isinstance(value, str):
        raise EnquiryError(f"{name} must be text")
    if len(value) > limit or any(ord(c) < 32 and c not in "\n\t" for c in value):
        raise EnquiryError(f"{name} contains invalid control characters or is too long")
    if required and not value.strip():
        raise EnquiryError(f"{name} is required")
    return value

def iso_date(value: Any, name: str) -> date:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise EnquiryError(f"{name} must be YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise EnquiryError(f"{name} is not a calendar date") from exc

def amount(value: Any, name: str) -> str | None:
    # Explicit decimal text avoids recovering money from binary floats.
    if value is None or value == "":
        return None
    if not isinstance(value, str) or not re.fullmatch(r"\d+(?:\.\d{1,2})?", value):
        raise EnquiryError(f"{name} must be nonnegative decimal text with <=2 places")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise EnquiryError(f"{name} is not a valid amount") from exc
    if not result.is_finite() or result > Decimal("1000000000000"):
        raise EnquiryError(f"{name} is outside the supported numeric range")
    return value

def source_url(value: Any) -> str:
    value = text(value, "source_url", required=True, limit=4000)
    try:
        parsed = urlsplit(value)
        invalid = (
            parsed.scheme not in ("http", "https") or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or any(c.isspace() for c in value)
        )
        # Force validation of malformed ports; no connection is made.
        _ = parsed.port
    except ValueError as exc:
        raise EnquiryError("source_url must be an HTTP(S) reference") from exc
    if invalid:
        raise EnquiryError("source_url must be an HTTP(S) reference without credentials")
    return value

def catalog_row(raw: Any) -> dict[str, Any]:
    """Validate the exported canonical catalog contract without rewriting it.

    Extra JSON metadata and the original source_note are retained in the source
    snapshot/hash. The exporter does not replace the desk's catalog_data().
    """
    if not isinstance(raw, dict):
        raise EnquiryError("Each catalog row must be an object")
    row = copy.deepcopy(raw)
    for field in ("id", "supplier", "supplier_sku", "part_number", "description",
                  "source_url", "checked_on", "currency"):
        text(row.get(field), field, required=True)
    row["source_url"] = source_url(row["source_url"])
    iso_date(row["checked_on"], "checked_on")
    if not re.fullmatch(r"[A-Z]{3}", row["currency"]):
        raise EnquiryError("currency must be a three-letter uppercase code")
    for field in ("make", "model", "serial_scope", "lead_time", "source_note"):
        text(row.get(field, ""), field)
    aliases = row.get("aliases", [])
    if not isinstance(aliases, (list, str)) or (
        isinstance(aliases, list) and any(not isinstance(x, str) for x in aliases)
    ):
        raise EnquiryError("aliases must be a text list or semicolon text")
    for field in ("unit_price", "shipping"):
        amount(row.get(field), field)
    if row.get("stock_status", "unknown") not in ("unknown", "in_stock", "out_of_stock"):
        raise EnquiryError("stock_status must be unknown, in_stock or out_of_stock")
    quantity = row.get("stock_qty")
    if quantity is not None and (type(quantity) is not int or quantity < 0):
        raise EnquiryError("stock_qty must be a nonnegative integer or null")
    metadata = row.get("desk_option")
    if metadata is not None:
        if not isinstance(metadata, dict):
            raise EnquiryError("desk_option metadata must be an object")
        if not isinstance(metadata.get("effective_fit"), str) or metadata["effective_fit"] not in {"stale", "unreviewed", "compatible", "uncertain", "incompatible"}:
            raise EnquiryError("desk_option.effective_fit must be a saved desk state")
        if not isinstance(metadata.get("review"), dict):
            raise EnquiryError("desk_option.review must be an object")
        for field in ("note", "technician"):
            text(metadata["review"].get(field, ""), "desk_option.review." + field)
    # Also rejects NaN in extra metadata rather than silently emitting it.
    try:
        canonical(row)
    except (ValueError, TypeError, OverflowError) as exc:
        raise EnquiryError("Catalog metadata must contain finite JSON values") from exc
    return row

def request_data(raw: Any) -> dict[str, Any]:
    """A deliberately small adapter input, not a second stored request schema."""
    if not isinstance(raw, dict):
        raise EnquiryError("request must be an object")
    request = copy.deepcopy(raw)
    text(request.get("id"), "request.id", required=True, limit=500)
    for key in ("job_ref", "make", "model", "serial", "requested_part", "notes", "description"):
        text(request.get(key, ""), "request." + key)
    q = request.get("quantity")
    if type(q) is not int or not 1 <= q <= 1_000_000:
        raise EnquiryError("request.quantity must be an integer from 1 to 1000000")
    try:
        canonical(request)
    except (ValueError, TypeError, OverflowError) as exc:
        raise EnquiryError("Request metadata must contain finite JSON values") from exc
    return request

def issues_for(row: dict[str, Any], request: dict[str, Any], as_of: date,
               max_age_days: int) -> list[dict[str, str]]:
    """Describe missing confirmations, never establish compatibility or availability."""
    findings = []
    def add(code: str, question: str) -> None:
        findings.append({"code": code, "question": question})
    age = (as_of - iso_date(row["checked_on"], "checked_on")).days
    if age < 0:
        add("future_source_date", "The source date is in the future. Please correct or explain it.")
    elif age > max_age_days:
        add("aged_source", f"The source is {age} days old. Please reconfirm price, stock and lead time.")
    desk_option = row.get("desk_option")
    if desk_option is not None:
        fit = desk_option["effective_fit"]
        if fit == "stale":
            add("stale_desk_review", "The saved desk review is stale after a catalog or request change. "
                "Please resolve the changed details before this option is used.")
        elif fit == "incompatible":
            add("incompatible_desk_review", "The saved desk review identifies this option as incompatible. "
                "Do not ship this SKU; identify any different alternative and its fit reference separately.")
        elif fit == "compatible":
            add("recorded_compatible_review", "The saved technician review records compatibility. "
                "Please confirm the supplied SKU is that same part, not a substituted variant.")
    add("fit_confirmation", "Please provide the catalog/manufacturer reference for this exact model, "
        "serial range and requested part. Do not substitute a different part without an explicit reply.")
    if not request.get("model", "").strip():
        add("missing_model", "The equipment model is missing; it must be supplied before fit can be assessed.")
    if not request.get("serial", "").strip():
        add("missing_serial", "Please state whether a serial number or serial range is required to establish fit.")
    if row.get("serial_scope", "").strip():
        add("serial_scope", "Please confirm the supplied serial falls within the recorded scope: "
            + row["serial_scope"])
    if row.get("stock_status", "unknown") == "out_of_stock":
        add("out_of_stock", "Please quote a replenishment date or identify an alternative separately.")
    elif row.get("stock_status", "unknown") == "unknown":
        add("unknown_stock", "Please confirm current stock and the quantity available to reserve.")
    quantity = row.get("stock_qty")
    if quantity is None:
        add("unknown_stock_quantity", f"Please confirm availability of {request['quantity']} units.")
    elif quantity < request["quantity"]:
        add("insufficient_stock_quantity", f"Recorded stock is {quantity}; please confirm a plan for "
            f"the full {request['quantity']} units.")
    if row.get("stock_status") == "out_of_stock" and quantity is not None and quantity > 0:
        add("stock_conflict", "The source says out_of_stock but records a positive quantity; please reconcile it.")
    if row.get("stock_status") == "in_stock" and quantity == 0:
        add("stock_conflict", "The source says in_stock but records zero units; please reconcile it.")
    if amount(row.get("unit_price"), "unit_price") is None:
        add("missing_price", "Please provide the unit price and currency.")
    if amount(row.get("shipping"), "shipping") is None:
        add("missing_shipping", "Please quote shipping separately, including its basis and destination assumptions.")
    if not row.get("lead_time", "").strip():
        add("missing_lead_time", "Please confirm dispatch and estimated delivery timing.")
    add("tax_and_validity", "Please identify any taxes, fees, minimum order, pack-size constraints "
        "and the quote-valid-until date. None are assumed included.")
    return findings

def enquiry_text(group: dict[str, Any]) -> str:
    r = group["request"]
    lines = [
        f"UNSENT ENQUIRY — {group['supplier']}",
        f"Reference: {group['id']}",
        "",
        "Please confirm the following sourcing options. This is not a purchase order,",
        "an instruction to ship, or an acceptance of a quote.",
        "",
        f"Request: {r['id']}",
        f"Job reference: {r.get('job_ref', '') or '(not supplied)'}",
        f"Equipment: {r.get('make', '') or '(make missing)'} / "
        f"{r.get('model', '') or '(model missing)'}",
        f"Serial: {r.get('serial', '') or '(not supplied)'}",
        f"Requested part: {r.get('requested_part', '') or '(not supplied)'}",
        f"Requested description: {r.get('description', '') or '(not supplied)'}",
        f"Required quantity: {r['quantity']}",
        "",
        "The entries below are ALTERNATIVES for this one request, not additive order lines.",
        "Provide a separate reply for each option. No aggregate purchase total is asserted.",
    ]
    if r.get("existing_order_count", 0):
        lines.extend(["", "EXISTING ORDER/DRAFT: the desk already records an active order or draft for this job.",
                      "This enquiry does not create another order. Do not ship or duplicate the existing order."])
    if r.get("notes"):
        lines.extend(["", "Request notes: " + r["notes"]])
    for position, option in enumerate(group["options"], 1):
        row = option["catalog"]
        p = row.get("unit_price")
        shipping = row.get("shipping")
        lines.extend([
            "", f"OPTION {position} — catalog {row['id']}",
            f"Part: {row['part_number']} / supplier SKU: {row['supplier_sku']}",
            f"Description: {row['description']}",
            f"Source: {row['source_url']}",
            f"Source date: {row['checked_on']}",
            f"Source note: {row.get('source_note', '') or '(none supplied)'}",
            f"Recorded unit price: {row['currency']} {p if p not in (None, '') else 'UNKNOWN'}",
            f"Quantity × recorded unit price: {row['currency']} "
            f"{option['line_amount'] if option['line_amount'] is not None else 'UNKNOWN'}",
            f"Recorded shipping value (basis unverified): {row['currency']} "
            f"{shipping if shipping not in (None, '') else 'UNKNOWN'}",
            f"Recorded stock: {row.get('stock_status', 'unknown')} / "
            f"{row.get('stock_qty') if row.get('stock_qty') is not None else 'quantity unknown'}",
            f"Recorded lead time: {row.get('lead_time', '') or '(unknown)'}",
            "Questions:",
        ])
        if row.get("desk_option"):
            metadata = row["desk_option"]
            lines.insert(len(lines) - 1, "Saved desk fit state: " + metadata["effective_fit"])
            lines.insert(len(lines) - 1, "Saved fit note: " + metadata["review"].get("note", ""))
        lines.extend("- " + finding["question"] for finding in option["questions"])
    lines.extend(["", "Prepared from supplied references only. No live catalog lookup, supplier",
                  "contact, fit approval, reservation, order or payment has occurred.", ""])
    return "\n".join(lines)

def build_enquiries(request: dict[str, Any], rows: list[dict[str, Any]], *,
                    as_of: date | None = None, max_age_days: int = 7) -> dict[str, Any]:
    """Generate one unsent draft per exact supplier identifier/name.

    Multiple options are alternatives, not purchase lines. Amounts are only
    per-option unit-price multiplication; shipping/tax semantics are not guessed.
    """
    if type(max_age_days) is not int or not 0 <= max_age_days <= 36500:
        raise EnquiryError("max_age_days must be an integer from 0 to 36500")
    if as_of is None:
        as_of = datetime.now(timezone.utc).date()
    if type(as_of) is not date:
        raise EnquiryError("as_of must be a date, without a time component")
    request = request_data(request)
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_ROWS:
        raise EnquiryError(f"rows must contain 1 to {MAX_ROWS} selected catalog entries")
    by_id: dict[str, dict[str, Any]] = {}
    for raw in rows:
        row = catalog_row(raw)
        previous = by_id.get(row["id"])
        if previous is not None and canonical(previous) != canonical(row):
            raise EnquiryError(f"Conflicting catalog snapshots for id {row['id']}")
        by_id[row["id"]] = row  # Exact repeats coalesce, not duplicate inquiry lines.
    ordered_rows = [by_id[k] for k in sorted(by_id)]
    inputs = {"request": request, "rows": ordered_rows,
              "as_of": as_of.isoformat(), "max_age_days": max_age_days}
    result: dict[str, Any] = {
        "version": VERSION, "status": "unsent", "network_actions": 0,
        "as_of": as_of.isoformat(), "max_age_days": max_age_days,
        "request": request, "input_sha256": sha(inputs), "enquiries": [],
        "notice": "Source-date age is an operator-selected reminder policy, not a fit or availability guarantee.",
    }
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in ordered_rows:
        unit_price = amount(row.get("unit_price"), "unit_price")
        line = None if unit_price is None else format(
            Decimal(unit_price) * request["quantity"], ".2f")
        groups.setdefault(row["supplier"], []).append({
            "catalog": row, "catalog_sha256": sha(row),
            "line_amount": line, "questions": issues_for(row, request, as_of, max_age_days),
        })
    for supplier in sorted(groups):
        group = {"supplier": supplier, "request": request, "options": groups[supplier],
                 "as_of": as_of.isoformat(), "max_age_days": max_age_days, "status": "unsent"}
        group["id"] = "enquiry-" + sha(group)[:24]
        group["text"] = enquiry_text(group)
        result["enquiries"].append(group)
    return result


def build_from_desk_request(snapshot: dict[str, Any], option_ids: list[str] | None = None,
                            *, as_of: date | None = None,
                            max_age_days: int = 7) -> dict[str, Any]:
    """Consume Desk.request(id)/GET /api/requests/{id}, without opening its DB.

    Existing snapshots and fit records remain observations, not exporter-made
    decisions. Only chosen options reach supplier drafts. Event history and rival
    supplier options are not copied into an individual draft.
    """
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("data"), dict):
        raise EnquiryError("Expected a saved desk request with a data object")
    rid = text(snapshot.get("id"), "desk request id", required=True)
    revision = snapshot.get("revision")
    if type(revision) is not int or revision < 1:
        raise EnquiryError("Desk request revision must be a positive integer")
    options = snapshot.get("options")
    if not isinstance(options, list) or len(options) > MAX_ROWS:
        raise EnquiryError("Saved desk options must be a list within the export size limit")
    if option_ids is not None and (
        not isinstance(option_ids, list) or not option_ids
        or any(not isinstance(x, str) or not x for x in option_ids)
    ):
        raise EnquiryError("option_ids must be a nonempty list of saved option IDs")
    selected = None if option_ids is None else set(option_ids)
    available = {}
    for option in options:
        if not isinstance(option, dict):
            raise EnquiryError("Saved option must be an object")
        oid = text(option.get("id"), "option id", required=True)
        if oid in available:
            raise EnquiryError("Saved option IDs must be unique")
        if option.get("request_id") != rid:
            raise EnquiryError("Saved option refers to a different request")
        available[oid] = option
    if selected is not None and not selected.issubset(available):
        raise EnquiryError("A selected option was not found in the saved request")
    rows = []
    for oid in sorted(selected if selected is not None else available):
        option = available[oid]
        row = catalog_row(option.get("snapshot"))
        if option.get("catalog_id") != row["id"]:
            raise EnquiryError("Saved catalog identity and option snapshot disagree")
        if type(option.get("catalog_version")) is not int or option["catalog_version"] < 1:
            raise EnquiryError("Saved catalog version must be positive")
        for flag in ("catalog_changed", "request_changed"):
            if type(option.get(flag)) is not bool:
                raise EnquiryError(f"{flag} must be an explicit boolean")
        fit = option.get("effective_fit")
        if not isinstance(fit, str) or fit not in {"stale", "unreviewed", "compatible", "uncertain", "incompatible"}:
            raise EnquiryError("Saved effective_fit is not a recognized desk state")
        review = option.get("review")
        if not isinstance(review, dict):
            raise EnquiryError("Saved review must be an object")
        for field in ("note", "technician"):
            text(review.get(field, ""), "review." + field)
        row["desk_option"] = {key: copy.deepcopy(option[key]) for key in
                              ("id", "catalog_id", "catalog_version", "catalog_changed",
                               "request_changed", "effective_fit", "review")}
        rows.append(row)
    orders = snapshot.get("orders", [])
    if not isinstance(orders, list):
        raise EnquiryError("Saved orders must be a list")
    active = 0
    for order in orders:
        if not isinstance(order, dict) or order.get("request_id") != rid:
            raise EnquiryError("Saved order refers to a different request")
        if order.get("status") not in {"draft", "placed", "cancelled"}:
            raise EnquiryError("Saved order status is not recognized")
        active += order["status"] != "cancelled"
    data = snapshot["data"]
    request = {key: copy.deepcopy(data.get(key, "")) for key in
               ("job_ref", "make", "model", "serial", "notes", "description")}
    request.update(id=rid, quantity=data.get("quantity"),
                   requested_part=data.get("part_number", ""),
                   source_request_revision=revision, existing_order_count=active)
    # The hash binds the input record without copying other suppliers' quote
    # values, technician event history or order documents into a vendor draft.
    try:
        request["desk_snapshot_sha256"] = sha(snapshot)
    except (TypeError, ValueError, OverflowError) as exc:
        raise EnquiryError("Saved request contains nonfinite or non-JSON metadata") from exc
    return build_enquiries(request, rows, as_of=as_of, max_age_days=max_age_days)

def read_json(path: Path) -> Any:
    def pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
        result = {}
        for key, value in values:
            if key in result:
                raise EnquiryError(f"Duplicate JSON field: {key}")
            result[key] = value
        return result
    def constant(value: str) -> None:
        raise EnquiryError(f"Nonfinite JSON value: {value}")
    with path.open("rb") as source:
        raw = source.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        raise EnquiryError(f"{path.name}: input exceeds {MAX_INPUT_BYTES} bytes")
    try:
        return json.loads(raw.decode("utf-8-sig"), object_pairs_hook=pairs, parse_constant=constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise EnquiryError(f"{path.name}: invalid UTF-8 JSON: {exc}") from exc

def write_pack(result: dict[str, Any], destination: Path) -> dict[str, Any]:
    """Create a new directory. Never overwrite an earlier pack or saved desk data."""
    if not isinstance(result, dict) or not isinstance(result.get("enquiries"), list):
        raise EnquiryError("Expected the result of build_enquiries")
    if not isinstance(result.get("input_sha256"), str) or not re.fullmatch(r"[a-f0-9]{64}", result["input_sha256"]):
        raise EnquiryError("Pack needs its input SHA256")
    ids = set()
    for group in result["enquiries"]:
        if not isinstance(group, dict) or not isinstance(group.get("id"), str) or not re.fullmatch(r"enquiry-[a-f0-9]{24}", group["id"]):
            raise EnquiryError("Pack enquiry identifier must be a generated ID")
        if group["id"] in ids:
            raise EnquiryError("Duplicate enquiry identifier in pack")
        ids.add(group["id"])
        text(group.get("supplier"), "supplier", required=True)
        text(group.get("text"), "enquiry text", required=True, limit=MAX_INPUT_BYTES)
    try:
        canonical(result)
    except (TypeError, ValueError, OverflowError) as exc:
        raise EnquiryError("Pack must contain finite JSON data") from exc
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive directory creation preserves any previous operator-created pack.
    try:
        destination.mkdir()
    except FileExistsError as exc:
        raise EnquiryError("Output directory already exists; use a new pack name") from exc
    files: dict[str, bytes] = {}
    files["enquiries.json"] = json.dumps(result, ensure_ascii=False, indent=2,
                                        allow_nan=False).encode("utf-8") + b"\n"
    articles = []
    for group in result["enquiries"]:
        name = group["id"] + ".txt"  # Data-derived fixed hex IDs, never supplier paths.
        files[name] = group["text"].encode("utf-8")
        articles.append("<article><h2>" + html.escape(group["supplier"]) +
                        "</h2><pre>" + html.escape(group["text"]) + "</pre></article>")
    page = """<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Unsent supplier enquiries</title><style>
body{font:16px system-ui;max-width:960px;margin:2rem auto;padding:0 1rem;color:#183b37;background:#f8faf9}
article{background:white;border:1px solid #c8d9d4;padding:1.3rem;margin:1.4rem 0;break-after:page}
pre{font:inherit;white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.5}
@media print{body{margin:0;background:white}article{border:0}}
</style><h1>Unsent supplier enquiries</h1><p>Review-only export. No order or message has been sent.</p>
""" + "".join(articles) + "</html>"
    files["index.html"] = page.encode("utf-8")
    manifest = {"version": VERSION, "input_sha256": result["input_sha256"],
                "files": {name: {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
                          for name, data in sorted(files.items())}}
    # If an I/O failure interrupts this loop, no manifest is written; the partial
    # directory is retained and the next invocation must use a new destination.
    for name, data in files.items():
        (destination / name).write_bytes(data)
    (destination / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--request", type=Path,
                        help="Small adapter JSON: id, quantity; optional equipment/job notes")
    inputs.add_argument("--desk-request", type=Path,
                        help="Exact saved Desk.request(id)/GET /api/requests/{id} JSON")
    parser.add_argument("--option-id", action="append",
                        help="Saved option ID to include; repeat to select several (desk mode only)")
    parser.add_argument("--catalog", type=Path,
                        help="Selected canonical row list, or the desk's {items:[...]} import payload")
    parser.add_argument("--out", type=Path, required=True, help="New directory; never overwritten")
    parser.add_argument("--as-of", help="YYYY-MM-DD; default is the current UTC date")
    parser.add_argument("--max-age-days", type=int, default=7,
                        help="Explicit reminder policy, not a supplier validity guarantee")
    args = parser.parse_args(argv)
    try:
        effective_date = iso_date(args.as_of, "as_of") if args.as_of else None
        if args.desk_request:
            if args.catalog:
                raise EnquiryError("--catalog is not used with --desk-request")
            result = build_from_desk_request(read_json(args.desk_request), args.option_id,
                                            as_of=effective_date, max_age_days=args.max_age_days)
        else:
            if args.option_id or not args.catalog:
                raise EnquiryError("--request needs --catalog and does not take --option-id")
            request = read_json(args.request)
            document = read_json(args.catalog)
            rows = document["items"] if isinstance(document, dict) and "items" in document else document
            result = build_enquiries(request, rows, as_of=effective_date, max_age_days=args.max_age_days)
        manifest = write_pack(result, args.out)
        print(json.dumps({"status": "unsent", "enquiries": len(result["enquiries"]),
                          "input_sha256": manifest["input_sha256"], "out": str(args.out)}))
        return 0
    except (EnquiryError, OSError) as exc:
        print(f"enquiry export: {exc}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
