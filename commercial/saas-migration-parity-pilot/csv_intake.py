#!/usr/bin/env python3
"""Convert explicitly mapped CSV exports using the unchanged parity diagnostic."""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from errors import ParityError
from parity import compile_bytes
from parity_schema import INPUT_SCHEMA, MAX_INPUT_BYTES, MAX_RECORDS, canonical_bytes, sha256, loads_strict
from secure_io import read_bounded_regular

PLAN_SCHEMA = "saas-migration-csv-intake/v1"
DELIMITERS = {",", ";", "\t"}
INTEGER = re.compile(r"-?(?:0|[1-9][0-9]*)\Z")


@dataclass
class Table:
    headers: list[str]
    rows: list[list[str]]
    digest: str


def read_csv(raw: bytes, delimiter: str) -> Table:
    if delimiter not in DELIMITERS:
        raise ParityError("Choose comma, semicolon or tab explicitly; delimiters are not guessed")
    if len(raw) > MAX_INPUT_BYTES:
        raise ParityError(f"Each CSV must be at most {MAX_INPUT_BYTES} bytes")
    # Match the file budget without depending on another adapter's imports.
    csv.field_size_limit(MAX_INPUT_BYTES)
    try:
        reader = csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""), delimiter=delimiter, strict=True)
        headers = next(reader, None)
        if not headers or len(headers) > 64:
            raise ParityError("CSV must have a header with 1..64 columns")
        if any(not h or len(h) > 256 or any(ord(c) < 32 or ord(c) == 127 for c in h) for h in headers):
            raise ParityError("Headers must be nonempty, at most 256 characters, without control characters")
        if len(headers) != len(set(headers)):
            raise ParityError("Duplicate CSV headers are ambiguous; rename them in the export")
        rows = []
        for ordinal, row in enumerate(reader, start=1):
            if ordinal > MAX_RECORDS:
                raise ParityError(f"CSV exceeds {MAX_RECORDS} data records; no rows were truncated")
            if len(row) != len(headers):
                raise ParityError(f"Data record {ordinal} has {len(row)} cells; expected {len(headers)}")
            rows.append(row)
        return Table(headers, rows, sha256(raw))
    except (UnicodeDecodeError, csv.Error) as exc:
        raise ParityError(f"CSV must be well-formed UTF-8 text: {exc}") from exc


def inspect_csv(raw: bytes, delimiter: str) -> dict[str, Any]:
    table = read_csv(raw, delimiter)
    return {"headers": table.headers, "record_count": len(table.rows), "csv_sha256": table.digest}


def exact(obj: Any, fields: set[str], where: str) -> None:
    if type(obj) is not dict or set(obj) != fields:
        raise ParityError(f"{where} must contain exactly: {', '.join(sorted(fields))}")


def mappings(value: Any, source: Table, target: Table, *, keys: bool) -> list[dict[str, str]]:
    limit = 4 if keys else 32
    kind = "key_map" if keys else "field_map"
    if type(value) is not list or not 1 <= len(value) <= limit:
        raise ParityError(f"{kind} needs 1..{limit} explicit mappings")
    seen = {"source": set(), "target": set()}
    for index, entry in enumerate(value, 1):
        exact(entry, {"source", "target", "type"}, f"{kind}[{index}]")
        if type(entry["type"]) is not str or entry["type"] not in ({"string", "integer"} if keys else {"string", "integer", "boolean"}):
            raise ParityError(f"{kind}[{index}] has an unsupported type")
        for side, table in (("source", source), ("target", target)):
            name = entry[side]
            if type(name) is not str or name not in table.headers:
                raise ParityError(f"{kind}[{index}].{side} is not an inspected CSV header")
            if name in seen[side]:
                raise ParityError(f"{kind} repeats a {side} column")
            seen[side].add(name)
    return value


def convert(cell: str, declared: str, where: str) -> str | int | bool:
    if declared == "integer":
        if len(cell) > 20 or not INTEGER.fullmatch(cell):
            raise ParityError(f"{where}: integer needs unpadded decimal digits, no spaces or fraction; use string for identifiers")
        value = int(cell)
        if not -(2**63) <= value < 2**63:
            raise ParityError(f"{where}: integer is outside signed 64-bit range")
        return value
    if declared == "boolean":
        if cell not in {"true", "false"}:
            raise ParityError(f"{where}: boolean must be exactly true or false")
        return cell == "true"
    if not cell or len(cell) > 2048 or any(ord(c) < 32 or ord(c) == 127 for c in cell):
        raise ParityError(f"{where}: mapped strings must contain 1..2048 characters without controls; blank is not inferred as null")
    return cell


def compile_csv(source_raw: bytes, target_raw: bytes, plan: Any) -> dict[str, Any]:
    exact(plan, {"schema", "cutover_at_utc", "max_snapshot_age_seconds", "key_map", "field_map", "source_snapshot", "target_snapshot"}, "plan")
    if plan["schema"] != PLAN_SCHEMA:
        raise ParityError(f"plan.schema must be {PLAN_SCHEMA}")
    tables = {}
    for side, raw in (("source", source_raw), ("target", target_raw)):
        meta = plan[f"{side}_snapshot"]
        exact(meta, {"snapshot_id", "schema_revision", "captured_at_utc", "complete", "delimiter"}, f"{side}_snapshot")
        if type(meta["delimiter"]) is not str:
            raise ParityError(f"{side} delimiter must be a string")
        tables[side] = read_csv(raw, meta["delimiter"])
    key_map = mappings(plan["key_map"], tables["source"], tables["target"], keys=True)
    field_map = mappings(plan["field_map"], tables["source"], tables["target"], keys=False)
    aliases = [(f"key_{i}", m) for i, m in enumerate(key_map, 1)] + [(f"field_{i}", m) for i, m in enumerate(field_map, 1)]
    manifest = {
        "schema": INPUT_SCHEMA,
        "cutover_at_utc": plan["cutover_at_utc"],
        "max_snapshot_age_seconds": plan["max_snapshot_age_seconds"],
        "key_map": [{"source": f"key_{i}", "target": f"key_{i}", "type": m["type"]} for i, m in enumerate(key_map, 1)],
        "field_map": [{"source": f"field_{i}", "target": f"field_{i}", "type": m["type"]} for i, m in enumerate(field_map, 1)],
    }
    for side, table in tables.items():
        columns = {h: i for i, h in enumerate(table.headers)}
        records = []
        for ordinal, row in enumerate(table.rows, 1):
            fields = {alias: convert(row[columns[m[side]]], m["type"], f"{side} record {ordinal}, column {columns[m[side]] + 1}") for alias, m in aliases}
            records.append({"fields": fields})
        manifest[f"{side}_snapshot"] = {k: v for k, v in plan[f"{side}_snapshot"].items() if k != "delimiter"}
        manifest[f"{side}_snapshot"]["records"] = records
    manifest_raw = canonical_bytes(manifest)
    report, markdown = compile_bytes(manifest_raw)
    intake = {
        "csv_sha256": {side: table.digest for side, table in tables.items()},
        "columns": [{"alias": alias, **mapping} for alias, mapping in aliases],
        "excluded_columns": {side: [h for h in table.headers if h not in {m[side] for _, m in aliases}] for side, table in tables.items()},
        "notice": "Only explicitly mapped columns are compared. Completeness is an operator declaration, not independently established. Replay manifest contains selected raw values; keep it private.",
    }
    return {"manifest": manifest, "report": report, "markdown": markdown, "plan": plan, "intake": intake}


def bundle_bytes(result: dict[str, Any]) -> bytes:
    buffer = io.BytesIO()
    files = {
        "manifest.json": canonical_bytes(result["manifest"]),
        "report.json": canonical_bytes(result["report"]),
        "report.md": result["markdown"].encode("utf-8"),
        "intake-plan.json": canonical_bytes(result["plan"]),
        "column-map.json": canonical_bytes(result["intake"]),
    }
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for name, content in files.items():
            bundle.writestr(name, content)
    return buffer.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="new private ZIP path; never overwritten")
    args = parser.parse_args()
    try:
        result = compile_csv(read_bounded_regular(args.source, MAX_INPUT_BYTES), read_bounded_regular(args.target, MAX_INPUT_BYTES), loads_strict(read_bounded_regular(args.plan, 100_000)))
        payload = bundle_bytes(result)
        # Restrict the private replay bundle to this operating-system user.
        import os
        fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
        print(json.dumps({"state": result["report"]["summary"]["diagnostic_state"], "output": str(args.output), "private_replay_bundle": True}))
        return 0
    except (ParityError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
