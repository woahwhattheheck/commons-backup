#!/usr/bin/env python3
"""Explicit retailer CSV mapping into the existing supplier reorder loaders."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import tempfile
from pathlib import Path

import reorder_assistant as engine

SCHEMA = "commons-reorder-mapping-v1"
FIELDS = {
    "stock": ("sku", "name", "on_hand", "on_order", "allocated", "unit"),
    "rules": ("sku", "reorder_at", "target_stock", "preferred_supplier"),
    "catalog": ("supplier_id", "supplier_sku", "sku", "description", "unit_cost",
                "available_qty", "lead_days", "alternative_for_sku"),
}
MAX_SOURCE = 2 * 1024 * 1024
MAX_PROFILE = 64 * 1024
MAX_OUTPUT = 8 * 1024 * 1024
MAX_ROWS = 20000
DELIMITERS = (",", ";", "\t", "|")


class MappingError(ValueError):
    """The mapping is ambiguous, incomplete, or invalid for the canonical loader."""


def _read(path: Path, maximum: int) -> bytes:
    with path.open("rb") as handle:
        data = handle.read(maximum + 1)
    if len(data) > maximum:
        raise MappingError(f"{path}: input exceeds {maximum} bytes")
    return data


def _object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise MappingError(f"profile has duplicate JSON key {key!r}")
        result[key] = value
    return result


def _constant(value: str) -> object:
    raise MappingError(f"profile contains non-JSON constant {value}")


def validate_profile(value: object) -> dict:
    if not isinstance(value, dict) or any(not isinstance(k, str) for k in value):
        raise MappingError("profile must be an object with string keys")
    unknown = set(value) - {"schema", "kind", "columns", "constants", "delimiter"}
    if unknown:
        raise MappingError(f"unknown profile fields: {sorted(unknown)}")
    if value.get("schema") != SCHEMA:
        raise MappingError(f"profile schema must be {SCHEMA}")
    kind = value.get("kind")
    if not isinstance(kind, str) or kind not in FIELDS:
        raise MappingError("profile kind must be stock, rules, or catalog")
    columns, constants = value.get("columns", {}), value.get("constants", {})
    for label, mapping in (("columns", columns), ("constants", constants)):
        if not isinstance(mapping, dict) or any(not isinstance(k, str) for k in mapping):
            raise MappingError(f"{label} must be an object with string keys")
        if any(not isinstance(v, str) for v in mapping.values()):
            raise MappingError(f"{label} values must be strings, including numeric constants")
    try:
        for mapping in (columns, constants):
            for key, text in mapping.items():
                key.encode("utf-8")
                text.encode("utf-8")
    except UnicodeError as exc:
        raise MappingError("profile text must be valid Unicode") from exc
    overlap = set(columns) & set(constants)
    if overlap:
        raise MappingError(f"fields cannot have both a column and a constant: {sorted(overlap)}")
    provided = set(columns) | set(constants)
    missing, extra = set(FIELDS[kind]) - provided, provided - set(FIELDS[kind])
    if missing or extra:
        raise MappingError(f"profile fields: missing={sorted(missing)}, unknown={sorted(extra)}")
    if any(not name.strip() for name in columns.values()):
        raise MappingError("source column names must be nonblank exact headers")
    delimiter = value.get("delimiter", ",")
    if not isinstance(delimiter, str) or delimiter not in DELIMITERS:
        raise MappingError("delimiter must be comma, semicolon, tab, or pipe")
    return {"schema": SCHEMA, "kind": kind, "columns": dict(columns),
            "constants": dict(constants), "delimiter": delimiter}


def load_profile(path: Path) -> dict:
    try:
        value = json.loads(_read(path, MAX_PROFILE).decode("utf-8-sig"),
                           object_pairs_hook=_object, parse_constant=_constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise MappingError(f"{path}: invalid UTF-8 JSON profile: {exc}") from exc
    return validate_profile(value)


def read_source(data: bytes, delimiter: str = ",") -> tuple[list[str], list[dict], list[dict]]:
    if delimiter not in DELIMITERS:
        raise MappingError("unsupported delimiter")
    if len(data) > MAX_SOURCE:
        raise MappingError(f"source exceeds {MAX_SOURCE} bytes")
    line = 1
    try:
        reader = csv.reader(io.StringIO(data.decode("utf-8-sig"), newline=""),
                            delimiter=delimiter, strict=True)
        headers = next(reader, [])
        if not headers or any(not name.strip() for name in headers):
            raise MappingError("source requires nonblank column headings")
        if len(headers) != len(set(headers)):
            raise MappingError("source has duplicate column headings")
        rows, locations = [], []
        while True:
            line = reader.line_num + 1
            try:
                cells = next(reader)
            except StopIteration:
                break
            if not cells:
                continue
            if len(cells) != len(headers):
                raise MappingError(f"source line {line}: expected {len(headers)} fields, got {len(cells)}")
            if len(rows) >= MAX_ROWS:
                raise MappingError(f"source exceeds {MAX_ROWS} data records")
            rows.append(dict(zip(headers, (cell.strip() for cell in cells))))
            locations.append({"output_record": len(rows), "source_start_line": line,
                              "source_end_line": reader.line_num})
    except (UnicodeError, csv.Error) as exc:
        raise MappingError(f"source line {line}: invalid UTF-8 CSV: {exc}") from exc
    return headers, rows, locations


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def map_bytes(data: bytes, profile: object) -> tuple[bytes, dict]:
    """Project explicit fields, then validate the complete CSV with the real loader."""
    profile = validate_profile(profile)
    headers, rows, locations = read_source(data, profile["delimiter"])
    columns, constants, kind = profile["columns"], profile["constants"], profile["kind"]
    missing = set(columns.values()) - set(headers)
    if missing:
        raise MappingError(f"mapped source columns are absent: {sorted(missing)}")
    fields = FIELDS[kind]
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    preview = []
    for row in rows:
        projected = {field: row[columns[field]] if field in columns else constants[field].strip()
                     for field in fields}
        writer.writerow(projected)
        if stream.tell() > MAX_OUTPUT:
            raise MappingError(f"mapped output exceeds {MAX_OUTPUT} bytes")
        if len(preview) < 5:
            preview.append(projected)
    encoded = stream.getvalue().encode("utf-8")
    if len(encoded) > MAX_OUTPUT:
        raise MappingError(f"mapped output exceeds {MAX_OUTPUT} bytes")
    with tempfile.TemporaryDirectory(prefix="reorder-map-check-") as directory:
        candidate = Path(directory) / f"{kind}.csv"
        candidate.write_bytes(encoded)
        loader = {"stock": engine.load_stock, "rules": engine.load_rules,
                  "catalog": engine.load_catalog}[kind]
        try:
            loader(candidate)
        except engine.ReorderError as exc:
            detail = str(exc).replace(str(candidate), f"mapped {kind}.csv")
            raise MappingError(f"canonical {kind} validation failed: {detail}") from exc
    receipt = {
        "schema": SCHEMA, "kind": kind, "row_count": len(rows),
        "source_headers": headers, "canonical_headers": list(fields),
        "ignored_source_columns": [h for h in headers if h not in columns.values()],
        "field_sources": {f: {"column": columns[f]} if f in columns else {"constant": constants[f]}
                          for f in fields},
        "preview_rows": preview, "source_locations": locations,
        "source_sha256": _hash(data), "output_sha256": _hash(encoded),
        "profile_sha256": _hash(json.dumps(profile, sort_keys=True, ensure_ascii=True).encode("utf-8")),
        "validation": f"{loader.__name__} passed", "orders_sent": 0,
    }
    return encoded, receipt


def create_output(path: Path, data: bytes) -> None:
    """Publish fully written bytes without replacing any existing destination."""
    staged = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".reorder-map-", delete=False) as handle:
            staged = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        # An atomic create-only link avoids check-then-overwrite races. A file,
        # directory, symlink (even dangling), or hardlink at path causes failure.
        os.link(staged, path)
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)


def convert(source: Path, profile_path: Path, output: Path | None = None) -> dict:
    profile = load_profile(profile_path)
    encoded, receipt = map_bytes(_read(source, MAX_SOURCE), profile)
    receipt["output_created"] = False
    if output is not None:
        create_output(output, encoded)
        receipt["output_created"] = True
        receipt["output_path"] = str(output)
    return receipt


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect", help="show exact source headers and sample values; infer nothing")
    inspect.add_argument("--source", type=Path, required=True)
    inspect.add_argument("--delimiter", choices=DELIMITERS, default=",")
    mapping = commands.add_parser("map", help="validate and preview; write only when --out is supplied")
    mapping.add_argument("--source", type=Path, required=True)
    mapping.add_argument("--profile", type=Path, required=True)
    mapping.add_argument("--out", type=Path, help="new canonical CSV path; never overwrites")
    return root


def main(argv: list[str] | None = None) -> int:
    cli = parser()
    args = cli.parse_args(argv)
    try:
        if args.command == "inspect":
            data = _read(args.source, MAX_SOURCE)
            headers, rows, locations = read_source(data, args.delimiter)
            result = {"source_headers": headers, "row_count": len(rows), "preview_rows": rows[:5],
                      "source_locations": locations, "source_sha256": _hash(data), "output_created": False}
        else:
            result = convert(args.source, args.profile, args.out)
        print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=True))
    except (MappingError, OSError) as exc:
        cli.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
