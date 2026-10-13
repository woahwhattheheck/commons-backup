#!/usr/bin/env python3
"""Convert a retained recurring-service CSV into the waste desk's manifest.

This module never opens a database or records service, drafts, or payments.
One CSV record represents one recurring plan, not a completed pickup.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
from pathlib import Path
from typing import Any

from desk_common import DeskError, ValidationError, business_timezone, currency, ident, money, text
from desk_state import WasteRouteState

COLUMNS = (
    "customer_id", "customer_name", "currency", "site_id", "site_name",
    "container_id", "container_label", "container_type", "plan_id", "weekday",
    "service_code", "price_minor",
)
WEEKDAYS = {name: number for number, name in enumerate(
    ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
)}
MAX_BYTES = 1024 * 1024
MAX_ROWS = 10000


class CSVIntakeError(ValidationError):
    """The complete input is rejected; no partial manifest is returned."""


def weekday(value: str) -> int:
    if value in {str(n) for n in range(7)}:
        return int(value)
    if value.casefold() in WEEKDAYS:
        return WEEKDAYS[value.casefold()]
    raise CSVIntakeError("weekday must be 0..6 (Monday=0) or a full English weekday name")


def minor_units(value: str) -> int:
    if not value or not value.isascii() or not value.isdigit() or len(value) > 19:
        raise CSVIntakeError("price_minor must contain only ASCII integer digits, not decimals, separators, signs or currency symbols")
    return money(int(value), "price_minor")


def build_manifest(csv_text: str, timezone_policy: str) -> dict[str, Any]:
    """Validate all records and return a complete, engine-compatible manifest."""
    if not isinstance(csv_text, str):
        raise CSVIntakeError("CSV input must be UTF-8 text")
    if len(csv_text.encode("utf-8")) > MAX_BYTES:
        raise CSVIntakeError("CSV exceeds the 1 MiB intake limit")
    timezone_policy = business_timezone(timezone_policy)
    reader = csv.DictReader(io.StringIO(csv_text.removeprefix("\ufeff"), newline=""), strict=True)
    try:
        original_headers = reader.fieldnames
        if not original_headers:
            raise CSVIntakeError("CSV requires a header and at least one plan row")
        headers = [name.strip().casefold() for name in original_headers]
        if len(headers) != len(set(headers)):
            raise CSVIntakeError("CSV contains duplicate column names after whitespace/case normalization")
        missing, extra = sorted(set(COLUMNS) - set(headers)), sorted(set(headers) - set(COLUMNS))
        if missing or extra:
            raise CSVIntakeError(f"CSV columns do not match the contract; missing={missing}, extra={extra}")
        reader.fieldnames = headers
        customers: dict[str, dict[str, Any]] = {}
        sites: dict[str, tuple[str, dict[str, Any], int]] = {}
        containers: dict[str, tuple[str, dict[str, Any], int]] = {}
        plans: dict[str, int] = {}
        row_count = 0
        for row in reader:
            row_count += 1
            line = reader.line_num
            if row_count > MAX_ROWS:
                raise CSVIntakeError(f"CSV exceeds the {MAX_ROWS}-plan limit")
            try:
                if None in row or any(row.get(name) is None for name in COLUMNS):
                    raise CSVIntakeError("row has too many or too few fields")
                values = {name: row[name].strip() for name in COLUMNS}
                blank = [name for name, value in values.items() if not value]
                if blank:
                    raise CSVIntakeError(f"required values are blank: {', '.join(blank)}")
                cid = ident(values["customer_id"], "customer_id")
                cname = text(values["customer_name"], "customer_name")
                unit = currency(values["currency"])
                sid = ident(values["site_id"], "site_id")
                sname = text(values["site_name"], "site_name")
                kid = ident(values["container_id"], "container_id")
                label = text(values["container_label"], "container_label")
                kind = text(values["container_type"], "container_type")
                pid = ident(values["plan_id"], "plan_id")
                plan = {
                    "id": pid,
                    "weekday": weekday(values["weekday"]),
                    "service_code": text(values["service_code"], "service_code"),
                    "price_minor": minor_units(values["price_minor"]),
                }
                if pid in plans:
                    raise CSVIntakeError(f"plan_id {pid!r} already appeared at CSV line {plans[pid]}; even identical duplicate rows require explicit correction")
                if cid in customers:
                    customer = customers[cid]
                    if (customer["name"], customer["currency"]) != (cname, unit):
                        raise CSVIntakeError(f"customer_id {cid!r} has conflicting name or currency")
                else:
                    customer = {"id": cid, "name": cname, "currency": unit, "sites": []}
                    customers[cid] = customer
                if sid in sites:
                    parent, site, first_line = sites[sid]
                    if parent != cid or site["name"] != sname:
                        raise CSVIntakeError(f"site_id {sid!r} conflicts with its customer/name at CSV line {first_line}")
                else:
                    site = {"id": sid, "name": sname, "containers": []}
                    sites[sid] = (cid, site, line)
                    customer["sites"].append(site)
                if kid in containers:
                    parent, container, first_line = containers[kid]
                    if parent != sid or (container["label"], container["container_type"]) != (label, kind):
                        raise CSVIntakeError(f"container_id {kid!r} conflicts with its site/label/type at CSV line {first_line}")
                else:
                    container = {"id": kid, "label": label, "container_type": kind, "plans": []}
                    containers[kid] = (sid, container, line)
                    site["containers"].append(container)
                container["plans"].append(plan)
                plans[pid] = line
            except DeskError as exc:
                raise CSVIntakeError(f"CSV record ending at line {line}: {exc}") from exc
        if row_count == 0:
            raise CSVIntakeError("CSV has no recurring-plan rows")
    except csv.Error as exc:
        raise CSVIntakeError(f"Malformed CSV near line {reader.line_num}: {exc}") from exc
    # Keep the engine's closed manifest grammar as the final compatibility boundary.
    return WasteRouteState._normalize_manifest({
        "business_timezone": timezone_policy,
        "customers": list(customers.values()),
    })


def preview(csv_text: str, timezone_policy: str) -> dict[str, Any]:
    """Browser adapters should copy manifest_text verbatim, never Number-round it."""
    manifest = build_manifest(csv_text, timezone_policy)
    customers = manifest["customers"]
    sites = [site for customer in customers for site in customer["sites"]]
    containers = [container for site in sites for container in site["containers"]]
    plans = [plan for container in containers for plan in container["plans"]]
    return {
        "business_timezone": manifest["business_timezone"],
        "counts": {"customers": len(customers), "sites": len(sites),
                   "containers": len(containers), "plans": len(plans)},
        "manifest_text": json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
    }


def read_csv(path: Path) -> str:
    if not path.is_file():
        raise CSVIntakeError("input must be an existing regular CSV file")
    with path.open("rb") as source:
        raw = source.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise CSVIntakeError("CSV exceeds the 1 MiB intake limit")
    try:
        return raw.decode("utf-8-sig", errors="strict")
    except UnicodeError as exc:
        raise CSVIntakeError("CSV must be UTF-8 (a UTF-8 BOM is accepted)") from exc


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path, help="Retained CSV containing one recurring plan per row")
    parser.add_argument("--business-timezone", required=True, help="Explicit SYSTEM_LOCAL, UTC, or installed IANA timezone")
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--out", type=Path, help="Create a new manifest file; never overwrite an existing file")
    target.add_argument("--preview", action="store_true", help="Print counts plus original integer-preserving manifest_text as JSON")
    args = parser.parse_args(argv)
    try:
        result = preview(read_csv(args.csv), args.business_timezone)
        if args.out:
            # Exclusive creation: a typo cannot replace a retained source or prior manifest.
            fd = os.open(args.out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as output:
                output.write(result["manifest_text"])
                output.flush()
                os.fsync(output.fileno())
            print(json.dumps({"created": str(args.out), "counts": result["counts"],
                              "business_timezone": result["business_timezone"]}, sort_keys=True))
        elif args.preview:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            sys.stdout.write(result["manifest_text"])
        return 0
    except (DeskError, OSError, UnicodeError) as exc:
        print(json.dumps({"error": type(exc).__name__, "message": str(exc)}, ensure_ascii=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
