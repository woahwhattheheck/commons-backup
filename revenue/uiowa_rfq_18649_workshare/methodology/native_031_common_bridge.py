#!/usr/bin/env python3
"""Lossless view of GRANITE's canonical two-table UIOWA-031 in current UIOWA-023.

The native tables remain authoritative for their own structure. This adapter
adds the declared owner and digest required by current 023 without modifying
the native input, treating repeated citations as independent corroboration,
or claiming it read or authenticated the referenced documents.
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import io
import json
from pathlib import Path
import re
import sys
from typing import Any

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("uiowa031_common_bridge_transport", HERE / "evidence_register_interchange.py")
if spec is None or spec.loader is None:
    raise ImportError("missing sibling register transport")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

SCHEMA = "uiowa-031-common-register-bridge/1"
DERIVED = ("custodian_or_owner", "content_digest")
NATIVE_REQUIRED = m._validator.REQUIRED - set(DERIVED) | {"source_id", "excerpt_locator", "practice_supported"}
MANIFEST_REQUIRED = {"source_id", "title", "document_location", "document_version", "owner",
                     "supplied_date", "source_type", "sha256", "retention_note"}
LIMITS = {"assessment_authority": False, "document_content_checked": False,
          "source_authenticity_verified": False}


def _table(columns: Any, rows: Any, required: set[str]) -> dict[str, Any]:
    if not isinstance(columns, list) or any(not isinstance(c, str) or not c.strip() for c in columns):
        raise m.RegisterError("table columns must be nonblank strings")
    if len(columns) != len(set(columns)) or required - set(columns):
        raise m.RegisterError("table has duplicate columns or lacks required columns")
    if not isinstance(rows, list):
        raise m.RegisterError("table rows must be a list")
    for row in rows:
        if not isinstance(row, dict) or set(row) != set(columns) or any(not isinstance(v, str) for v in row.values()):
            raise m.RegisterError("table rows must contain exactly the declared string-valued cells")
        try:
            for value in row.values():
                value.encode("utf-8")
        except UnicodeError as exc:
            raise m.RegisterError("table contains non-scalar Unicode") from exc
    try:
        for column in columns:
            column.encode("utf-8")
    except UnicodeError as exc:
        raise m.RegisterError("column contains non-scalar Unicode") from exc
    return {"columns": list(columns), "rows": [{c: r[c] for c in columns} for r in rows]}


def read_native_csv(text: str, required: set[str]) -> dict[str, Any]:
    try:
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        columns = next(reader, [])
        _table(columns, [], required)
        rows = []
        for values in reader:
            if not values:
                continue
            if len(values) != len(columns):
                raise m.RegisterError(f"CSV line {reader.line_num}: row width does not match header")
            rows.append(dict(zip(columns, values)))
        return _table(columns, rows, required)
    except (csv.Error, UnicodeError, TypeError) as exc:
        raise m.RegisterError(f"native CSV input error: {exc}") from exc


def _as_table(value: Any, required: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"columns", "rows"}:
        raise m.RegisterError("table must contain exactly columns and rows")
    return _table(value["columns"], value["rows"], required)


def native_to_common(manifest: Any, register: Any) -> dict[str, Any]:
    manifest = _as_table(manifest, MANIFEST_REQUIRED)
    register = _as_table(register, NATIVE_REQUIRED)
    documents: dict[str, dict[str, str]] = {}
    for doc in manifest["rows"]:
        sid = doc["source_id"]
        if not sid.strip() or sid in documents:
            raise m.RegisterError("manifest source_id must be nonblank and unambiguous")
        if not doc["owner"].strip():
            raise m.RegisterError(f"source {sid}: declared owner must not be blank")
        if not re.fullmatch(r"[0-9a-fA-F]{64}", doc["sha256"]):
            raise m.RegisterError(f"source {sid}: declared sha256 must contain exactly 64 hex digits")
        # Version, supplied date and location are retained literal metadata;
        # their actuality, calendar correctness and document access are not inferred.
        documents[sid] = doc
    added = [c for c in DERIVED if c not in register["columns"]]
    common_columns = register["columns"] + added
    common_rows = []
    for row in register["rows"]:
        doc = documents.get(row["source_id"])
        if doc is None:
            raise m.RegisterError(f"unresolved exact source_id {row['source_id']!r}")
        derived = {"custodian_or_owner": doc["owner"], "content_digest": "sha256:" + doc["sha256"]}
        for column, value in derived.items():
            if column in row and row[column] != value:
                raise m.RegisterError(f"source {row['source_id']}: native {column} conflicts with manifest metadata")
        common_rows.append({**row, **derived})
    common = m.validate_packet({"schema": m.SCHEMA, "columns": common_columns, "rows": common_rows})
    return {"schema": SCHEMA, **LIMITS, "manifest": manifest,
            "native_register_columns": register["columns"],
            "derived_columns": added, "common_register": common}


def common_to_native(bundle: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    expected = {"schema", *LIMITS, "manifest", "native_register_columns", "derived_columns", "common_register"}
    if not isinstance(bundle, dict) or set(bundle) != expected or bundle["schema"] != SCHEMA:
        raise m.RegisterError("invalid bridge envelope")
    if any(bundle[k] is not False for k in LIMITS):
        raise m.RegisterError("bridge must not claim assessment or source verification")
    common = m.validate_packet(bundle["common_register"])
    columns = bundle["native_register_columns"]
    if not isinstance(columns, list) or any(not isinstance(c, str) or c not in common["columns"] for c in columns):
        raise m.RegisterError("native column list is invalid")
    register = _table(columns, [{c: r[c] for c in columns} for r in common["rows"]], NATIVE_REQUIRED)
    rebuilt = native_to_common(bundle["manifest"], register)
    if rebuilt != bundle:
        raise m.RegisterError("bridge metadata or derived fields fail exact source-table recomputation")
    return rebuilt["manifest"], register


def dumps(bundle: Any) -> str:
    common_to_native(bundle)
    return json.dumps(bundle, ensure_ascii=False, allow_nan=False, indent=2) + "\n"


def loads(text: str) -> dict[str, Any]:
    try:
        bundle = json.loads(text, object_pairs_hook=m._unique_object, parse_constant=m._reject_constant)
    except m.RegisterError:
        raise
    except (ValueError, RecursionError, TypeError) as exc:
        raise m.RegisterError(f"bridge JSON error: {exc}") from exc
    common_to_native(bundle)
    return bundle


def render_table(table: dict[str, Any]) -> str:
    out = io.StringIO(newline="")
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(table["columns"])
    writer.writerows([[r[c] for c in table["columns"]] for r in table["rows"]])
    return out.getvalue()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    take = sub.add_parser("import")
    take.add_argument("packet_directory", type=Path)
    take.add_argument("output", type=Path)
    for command in ("export-manifest", "export-register", "export-common"):
        emit = sub.add_parser(command)
        emit.add_argument("input", type=Path)
        emit.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "import":
            manifest = read_native_csv(m._read_text(args.packet_directory / "manifest.csv"), MANIFEST_REQUIRED)
            register = read_native_csv(m._read_text(args.packet_directory / "register.csv"), NATIVE_REQUIRED)
            text = dumps(native_to_common(manifest, register))
        else:
            bundle = loads(m._read_text(args.input))
            manifest, register = common_to_native(bundle)
            if args.command == "export-common":
                text = m.to_csv(bundle["common_register"])
            else:
                text = render_table(manifest if args.command == "export-manifest" else register)
        m.publish_new(args.output, text)
    except (m.RegisterError, UnicodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"OK {args.command}: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
