#!/usr/bin/env python3
"""Explicit-field CSV bridge; retain source rows in an audit, publish only a complete conversion."""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import io
import json
import sys
from pathlib import Path
from typing import Any

if __package__:
    from .timestamp_adapter import InputError, canonical, normalize
else:
    from timestamp_adapter import InputError, canonical, normalize

DELIVERY_FIELDS = ("commit_at", "deployed_at", "recovered_at")


def _parse_rows(data: bytes) -> tuple[list[str], list[dict[str, str]]]:
    """Parse a retained byte snapshot; preserve embedded CSV newline values."""
    with io.StringIO(data.decode("utf-8"), newline="") as stream:
        reader = csv.DictReader(stream, strict=True)
        fields = reader.fieldnames or []
        if not fields or any(not field.strip() for field in fields) or len(set(fields)) != len(fields):
            raise InputError("CSV needs nonempty, unique headers")
        rows = []
        for index, row in enumerate(reader, 2):
            if None in row or any(value is None for value in row.values()):
                raise InputError(f"CSV record {index}: field count differs from header")
            rows.append(row)
    return fields, rows


def read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    """Retain the existing public return contract for callers."""
    return _parse_rows(path.read_bytes())


def convert_rows(rows: list[dict], *, timestamp_fields: tuple[str, ...] = DELIVERY_FIELDS,
                 required_fields: tuple[str, ...] = ("deployed_at",),
                 id_field: str = "deployment_id") -> dict:
    """Use <field>_zone and <field>_fold sidecars only when explicitly supplied.

    Other fields and row order are untouched. No partial normalized_rows are released
    if ANY nonblank timestamp is unresolved/invalid or a required timestamp is absent.
    Optional blank timestamps remain blank and receive an explicit missing diagnostic.
    """
    if (not isinstance(timestamp_fields, (list, tuple)) or not timestamp_fields
            or any(not isinstance(f, str) or not f for f in timestamp_fields)
            or not isinstance(required_fields, (list, tuple))
            or any(not isinstance(f, str) or not f for f in required_fields)
            or not isinstance(id_field, str) or not id_field
            or len(set(timestamp_fields)) != len(timestamp_fields)
            or len(set(required_fields)) != len(required_fields)
            or not set(required_fields) <= set(timestamp_fields)
            or id_field in timestamp_fields):
        raise InputError("invalid timestamp field mapping; required fields must be a subset and IDs cannot be timestamps")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise InputError("rows must be a list of objects")
    try:
        source_digest = hashlib.sha256(canonical(rows).encode("utf-8")).hexdigest()
    except (TypeError, ValueError) as exc:
        raise InputError("rows must contain finite JSON values") from exc
    converted, audit, seen, blocked = copy.deepcopy(rows), [], set(), []
    for index, row in enumerate(rows):
        identifier = row.get(id_field)
        if not isinstance(identifier, str) or not identifier.strip() or identifier in seen:
            raise InputError(f"row {index + 2}: missing/non-string/duplicate {id_field}")
        seen.add(identifier)
        for field in timestamp_fields:
            spec: dict[str, Any] = {"value": row.get(field)}
            key = row.get(f"{field}_zone")
            if key is not None and key != "":
                spec["zone"] = key
            fold = row.get(f"{field}_fold")
            if fold is not None and fold != "":
                spec["fold"] = int(fold) if isinstance(fold, str) and fold in ("0", "1") else fold
            result = normalize(spec)
            required = field in required_fields
            entry = {"record_id": identifier, "record_number": index + 2, "field": field,
                     "required": required, "source_field_present": field in row,
                     "source_zone": copy.deepcopy(key), "source_fold": copy.deepcopy(fold),
                     "normalization": result}
            audit.append(entry)
            if result["status"] == "resolved":
                converted[index][field] = result["instant_utc"]
            elif result["status"] != "missing" or required:
                blocked.append(entry)
    status = "invalid" if any(x["normalization"]["status"] == "invalid" for x in blocked) else "unresolved" if blocked else "ready"
    return {"schema_version": 1, "status": status, "source_rows": copy.deepcopy(rows),
            "source_rows_sha256": source_digest, "normalized_rows": converted if not blocked else None,
            "audit": audit, "blocked_fields": len(blocked), "input_row_count": len(rows),
            "field_mapping": {"id": id_field, "timestamps": list(timestamp_fields), "required": list(required_fields)},
            "boundary": "Time conversion only. Readiness does not establish row completeness, authenticity or metric eligibility."}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--id-field", default="deployment_id")
    parser.add_argument("--fields", default=",".join(DELIVERY_FIELDS))
    parser.add_argument("--required", default="deployed_at")
    args = parser.parse_args(argv)
    try:
        paths = [p.resolve() for p in (args.csv_path, args.output, args.audit)]
        if len(set(paths)) != 3:
            raise InputError("source, output and audit must be distinct paths")
        if args.output.exists() or args.audit.exists():
            raise InputError("output/audit already exists; choose new paths to avoid stale or overwritten evidence")
        # Parse and hash the same bytes even if the export is refreshed while
        # conversion is in progress. This is provenance, not a file lock.
        source_bytes = args.csv_path.read_bytes()
        fields, rows = _parse_rows(source_bytes)
        timestamps = tuple(args.fields.split(","))
        required = tuple(args.required.split(",")) if args.required else ()
        if not {args.id_field, *timestamps} <= set(fields):
            raise InputError("the CSV header is missing an explicitly mapped ID/timestamp column")
        report = convert_rows(rows, timestamp_fields=timestamps, required_fields=required, id_field=args.id_field)
        report["input_file_sha256"] = hashlib.sha256(source_bytes).hexdigest()
        with args.audit.open("x", encoding="utf-8", newline="") as stream:
            stream.write(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n")
        if report["status"] != "ready":
            print(f"NOT CONVERTED: {report['blocked_fields']} blocked timestamp fields; see audit", file=sys.stderr)
            return 1
        with args.output.open("x", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(report["normalized_rows"])
    except (InputError, OSError, ValueError, csv.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
