#!/usr/bin/env python3
"""Convert the editable UIOWA-047 CSV catalog for the existing JSON assessor."""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
import math
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Sequence

REQUIRED = {"dataset_id", "service", "purpose"}
TEXT = REQUIRED | {
    "owner_role", "data_origin", "handling_reference",
    "fixture_interface_version", "current_interface_version",
}
DATES = {"last_refreshed", "cleanup_last_verified"}
DAYS = {"refresh_cadence_days", "retention_days"}
LISTS = {"required_boundary_cases", "covered_boundary_cases"}
KNOWN = TEXT | DATES | DAYS | LISTS | {"cleanup_required", "estimated_refresh_hours"}
MAX_INPUT_BYTES = 8 * 1024 * 1024


def calendar_date(value: str) -> str:
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise ValueError("expected an ASCII YYYY-MM-DD calendar date")
    date.fromisoformat(value)
    return value


def typed_cell(column: str, cell: str) -> Any:
    if column in TEXT:
        if not cell.strip():
            raise ValueError("a supplied text value cannot be whitespace only")
        if column == "service" and cell not in {"ESS", "RIS", "IAM"}:
            raise ValueError("service must be exactly ESS, RIS or IAM")
        return cell
    if column in DATES:
        return calendar_date(cell)
    if column in DAYS:
        if not re.fullmatch(r"[0-9]+", cell):
            raise ValueError("expected a nonnegative integer, not a boolean or decimal")
        value = int(cell)
        if column == "refresh_cadence_days" and value == 0:
            raise ValueError("refresh cadence must be greater than zero")
        return value
    if column in LISTS:
        if cell == "[]":
            return []
        cases = cell.split(";")
        if any(not item.strip() for item in cases):
            raise ValueError("empty case identity; use [] for an explicitly empty list")
        return cases
    if column == "cleanup_required":
        if cell not in {"true", "false"}:
            raise ValueError("expected lowercase true or false; leave unknown blank")
        return cell == "true"
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?", cell):
        raise ValueError("expected finite nonnegative estimated hours")
    # Refuse a lossy decimal-to-JSON conversion instead of inventing precision.
    if re.fullmatch(r"[0-9]+", cell):
        return int(cell)
    number = float(cell)
    try:
        exact = math.isfinite(number) and Decimal(str(number)) == Decimal(cell)
    except InvalidOperation:
        exact = False
    if not exact:
        raise ValueError("estimated hours cannot be represented without decimal loss")
    return number


def convert_csv(raw: bytes, *, as_of: str, label: str = "") -> dict[str, Any]:
    """Preserve exact bytes and logical records; never rewrite the source CSV."""
    calendar_date(as_of)
    if len(raw) > MAX_INPUT_BYTES:
        raise ValueError("CSV exceeds the 8 MiB input limit")
    reader = csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""), strict=True)
    try:
        headers = next(reader)
    except StopIteration:
        raise ValueError("CSV has no header") from None
    if not headers or any(not name.strip() or name != name.strip() for name in headers):
        raise ValueError("headers must be nonblank and have no surrounding whitespace")
    if len(set(headers)) != len(headers):
        raise ValueError("duplicate CSV headers are not allowed")
    missing = REQUIRED - set(headers)
    if missing:
        raise ValueError("missing required columns: " + ", ".join(sorted(missing)))
    datasets, records = [], []
    previous_line = reader.line_num
    for record_number, cells in enumerate(reader, 1):
        start_line, end_line = previous_line + 1, reader.line_num
        previous_line = end_line
        where = f"record {record_number} (lines {start_line}-{end_line})"
        if len(cells) != len(headers):
            raise ValueError(f"{where}: expected {len(headers)} cells, got {len(cells)}")
        lexical = dict(zip(headers, cells))
        dataset: dict[str, Any] = {}
        for column, cell in lexical.items():
            if column not in KNOWN:
                continue  # Retained, not evaluated: see _csv_source.records below.
            if cell == "":
                if column in REQUIRED:
                    raise ValueError(f"{where}, {column}: required value is blank")
                continue
            try:
                dataset[column] = typed_cell(column, cell)
            except ValueError as exc:
                raise ValueError(f"{where}, {column}: {exc}") from exc
        datasets.append(dataset)
        records.append({
            "record": record_number, "dataset_index": len(datasets) - 1,
            "start_line": start_line, "end_line": end_line, "cells": lexical,
        })
    if not datasets:
        raise ValueError("CSV contains no dataset records")
    return {
        "as_of": as_of, "label": label, "datasets": datasets,
        "_csv_source": {
            "encoding": "utf-8", "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes_base64": base64.b64encode(raw).decode("ascii"),
            "headers": headers, "unevaluated_columns": [h for h in headers if h not in KNOWN],
            "records": records,
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", type=Path, help="UTF-8 CSV using catalog_template.csv headers")
    parser.add_argument("--as-of", required=True, help="Explicit YYYY-MM-DD assessment date")
    parser.add_argument("--label", default="", help="Caller-supplied catalog label")
    parser.add_argument("--output", required=True, type=Path, help="New JSON file; never overwritten")
    args = parser.parse_args(argv)
    try:
        with args.catalog.open("rb") as source:
            raw = source.read(MAX_INPUT_BYTES + 1)
        payload = convert_csv(raw, as_of=args.as_of, label=args.label)
        rendered = json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    except (OSError, ValueError, csv.Error) as exc:
        parser.error(str(exc))
    try:
        # Exclusive creation refuses existing files, directories and link aliases.
        # A partial newly created file is retained on an I/O error, never deleted.
        with args.output.open("x", encoding="utf-8", newline="\n") as target:
            target.write(rendered)
    except OSError as exc:
        parser.error(f"cannot publish {args.output}: {exc}; any new partial file is retained")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
