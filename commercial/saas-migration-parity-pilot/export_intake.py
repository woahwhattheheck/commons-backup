"""Convert operator-supplied exports into the existing parity manifest.

No format sniffing, key inference, value trimming, network access or file writes.
JSON integers stay in Python throughout ingestion; browsers send export text.
"""
from __future__ import annotations

import csv
import io
import re
from typing import Any

from errors import ParityError
from parity_schema import (
    INPUT_SCHEMA, MAX_INPUT_BYTES, MAX_RECORDS, MAX_FIELDS_PER_RECORD,
    MAX_KEY_MAPS, MAX_FIELD_MAPS, FIELD_RE,
    _exact_keys, _normalize_mapping, _normalize_manifest, _normalize_record,
    _strip_runtime, canonical_bytes, loads_strict,
)

csv.field_size_limit(MAX_INPUT_BYTES)
INTEGER_TEXT = re.compile(r"-?(?:0|[1-9][0-9]*)\Z")
SNAPSHOT_KEYS = {
    "format", "text", "snapshot_id", "schema_revision", "captured_at_utc", "complete",
}
REQUEST_KEYS = {
    "source", "target", "cutover_at_utc", "max_snapshot_age_seconds", "key_map", "field_map",
}


def parse_export(text: str, format_name: str) -> tuple[list[str], list[dict[str, Any]]]:
    """Return field names and flat records without guessing their declared types."""
    if type(text) is not str or type(format_name) is not str:
        raise ParityError("export text and format must be strings")
    try:
        raw = text.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise ParityError("export must contain valid Unicode") from exc
    if len(raw) > MAX_INPUT_BYTES:
        raise ParityError(f"each export must be <= {MAX_INPUT_BYTES} UTF-8 bytes")
    if format_name not in ("csv", "json"):
        raise ParityError("export format must be csv or json")

    columns: list[str] = []
    records: list[dict[str, Any]] = []
    if format_name == "csv":
        # A UTF-8 BOM is a CSV transport marker, not part of the first field name.
        reader = csv.reader(io.StringIO(text.removeprefix("\ufeff"), newline=""), strict=True)
        try:
            columns = next(reader, [])
            if not 1 <= len(columns) <= MAX_FIELDS_PER_RECORD:
                raise ParityError(f"CSV needs 1..{MAX_FIELDS_PER_RECORD} named columns")
            if len(set(columns)) != len(columns):
                raise ParityError("CSV has duplicate column names")
            if any(not FIELD_RE.fullmatch(name) for name in columns):
                raise ParityError("CSV column names must start with a letter and use only letters, digits, '.', '_' or '-' (64 characters maximum)")
            for row in reader:
                if len(records) >= MAX_RECORDS:
                    raise ParityError(f"CSV exceeds {MAX_RECORDS} records; it was not truncated")
                if len(row) != len(columns):
                    raise ParityError(f"CSV record ending at line {reader.line_num} has {len(row)} cells; expected {len(columns)}")
                records.append(dict(zip(columns, row)))
        except csv.Error as exc:
            raise ParityError(f"malformed CSV: {exc}") from exc
    else:
        value = loads_strict(raw)
        if type(value) is not list or len(value) > MAX_RECORDS:
            raise ParityError(f"JSON export must be an array of at most {MAX_RECORDS} flat objects")
        records = value
        seen: set[str] = set()
        for index, record in enumerate(records):
            if type(record) is not dict:
                raise ParityError(f"JSON record {index + 1} must be a flat object")
            for name in record:
                if name not in seen:
                    columns.append(name)
                    seen.add(name)
        if len(columns) > MAX_FIELDS_PER_RECORD:
            raise ParityError(f"JSON export contains more than {MAX_FIELDS_PER_RECORD} distinct columns")

    # Keep the engine's existing flat-cell and field-name contract. Blank/null,
    # nested, floating-point and invalid Unicode values are not silently dropped.
    for index, record in enumerate(records):
        _normalize_record({"fields": record}, f"export record {index + 1}")
    return columns, records


def _csv_types(records: list[dict[str, Any]], mapping: dict[str, str], side: str) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        fields = dict(record)
        for name, declared in mapping.items():
            if name not in fields or declared == "string":
                continue
            value = fields[name]
            location = f"{side} record {index + 1}, field {name}"
            if declared == "integer":
                if not INTEGER_TEXT.fullmatch(value) or len(value) > 20:
                    raise ParityError(f"{location}: integer needs decimal digits with optional '-' and no leading zeros; choose string for identifiers")
                number = int(value)
                if not -(2**63) <= number <= 2**63 - 1:
                    raise ParityError(f"{location}: integer is outside the signed 64-bit range")
                fields[name] = number
            elif declared == "boolean":
                if value not in ("true", "false"):
                    raise ParityError(f"{location}: boolean must be exactly true or false")
                fields[name] = value == "true"
        converted.append(fields)
    return converted


def build_manifest(request: Any) -> bytes:
    """Assemble a validated, downloadable input for parity.compile_bytes().

    Explicit CSV type conversion is the only cell conversion. JSON values keep
    their original types. A hash of this output binds the generated manifest,
    not the pre-conversion CSV/JSON file bytes.
    """
    _exact_keys(request, REQUEST_KEYS, "intake")
    keys = _normalize_mapping(request["key_map"], "key_map", max_rows=MAX_KEY_MAPS)
    compared = _normalize_mapping(request["field_map"], "field_map", max_rows=MAX_FIELD_MAPS)
    manifest: dict[str, Any] = {
        "schema": INPUT_SCHEMA,
        "cutover_at_utc": request["cutover_at_utc"],
        "max_snapshot_age_seconds": request["max_snapshot_age_seconds"],
        "key_map": keys,
        "field_map": compared,
    }
    for side in ("source", "target"):
        export = request[side]
        _exact_keys(export, SNAPSHOT_KEYS, side)
        _, records = parse_export(export["text"], export["format"])
        declared: dict[str, str] = {}
        for row in keys + compared:
            name, kind = row[side], row["type"]
            if name in declared and declared[name] != kind:
                raise ParityError(f"{side} field {name} has conflicting key/compared-field types")
            declared[name] = kind
        if export["format"] == "csv":
            records = _csv_types(records, declared, side)
        manifest[f"{side}_snapshot"] = {
            "snapshot_id": export["snapshot_id"],
            "schema_revision": export["schema_revision"],
            "captured_at_utc": export["captured_at_utc"],
            "complete": export["complete"],
            "records": [{"fields": record} for record in records],
        }
    manifest_raw = canonical_bytes(_strip_runtime(_normalize_manifest(manifest)))
    if len(manifest_raw) > MAX_INPUT_BYTES:
        raise ParityError(f"combined manifest exceeds {MAX_INPUT_BYTES} bytes; reduce the explicitly supplied export scope")
    return manifest_raw
