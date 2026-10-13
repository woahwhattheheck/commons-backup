#!/usr/bin/env python3
"""Read supplier CSV/JSON without network calls or inferred compatibility.

Preserve source SHA-256 and record locations; return raw named fields for the
canonical desk adapter. No database schema or order logic lives in this module.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import io
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path, PureWindowsPath
from typing import Any

MAX_BYTES = 8 * 1024 * 1024
MAX_ROWS = 5000


class CatalogFileError(ValueError):
    """Actionable file-format error; source data is never partially applied."""


@dataclass(frozen=True)
class ParsedCatalog:
    source: dict[str, Any]
    records: tuple[dict[str, Any], ...]

    def document(self) -> dict[str, Any]:
        return {"format": "parts-catalog-file-v1", "source": self.source,
                "records": list(self.records)}


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise CatalogFileError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _finite_json(value):
    raise CatalogFileError(f"non-finite JSON value: {value}")


def _json_value(value):
    # Preserve decimal source precision rather than rounding it through float.
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, list):
        return [_json_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _json_value(v) for k, v in value.items()}
    return value


def parse_bytes(raw: bytes, filename: str, format: str | None = None) -> ParsedCatalog:
    """Parse one immutable byte snapshot, not repeated reads of a changing file."""
    if not isinstance(raw, bytes):
        raise CatalogFileError("catalog source must be bytes")
    if not raw or len(raw) > MAX_BYTES:
        raise CatalogFileError(f"catalog must contain 1 to {MAX_BYTES} bytes")
    if b"\x00" in raw:
        raise CatalogFileError("catalog contains a NUL byte")
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CatalogFileError(f"catalog must be UTF-8; invalid byte near offset {exc.start}") from None
    # Metadata accepts either platform's upload labels without retaining folders.
    source_name = PureWindowsPath(filename).name
    kind = (format or PureWindowsPath(source_name).suffix.lstrip(".")).lower()
    if kind not in ("csv", "json"):
        raise CatalogFileError("choose csv or json format")
    source = {"filename": source_name, "sha256": hashlib.sha256(raw).hexdigest(),
              "size_bytes": len(raw), "format": kind}
    records = []
    if kind == "csv":
        reader = csv.reader(io.StringIO(content, newline=""), strict=True)
        try:
            headers = next(reader, None)
            if not headers or any(not h.strip() for h in headers):
                raise CatalogFileError("CSV needs a nonblank header for each column")
            if len(headers) != len(set(headers)):
                raise CatalogFileError("CSV has duplicate column headers")
            if any(h != h.strip() for h in headers):
                raise CatalogFileError("CSV headers have surrounding whitespace; normalize them explicitly")
            previous_line = reader.line_num
            for row in reader:
                start, end = previous_line + 1, reader.line_num
                previous_line = end
                if not row:
                    continue
                if len(row) != len(headers):
                    raise CatalogFileError(f"CSV lines {start}-{end}: expected {len(headers)} columns, found {len(row)}")
                records.append({"record": len(records) + 1, "location": {"line_start": start, "line_end": end},
                                "fields": dict(zip(headers, row))})
                if len(records) > MAX_ROWS:
                    raise CatalogFileError(f"catalog exceeds {MAX_ROWS} records")
        except csv.Error as exc:
            raise CatalogFileError(f"CSV near line {reader.line_num}: {exc}") from None
    else:
        try:
            values = json.loads(content, parse_float=Decimal, parse_constant=_finite_json,
                                object_pairs_hook=_unique_object)
        except json.JSONDecodeError as exc:
            raise CatalogFileError(f"JSON line {exc.lineno}, column {exc.colno}: {exc.msg}") from None
        prefix = ""
        if isinstance(values, dict):
            if set(values) != {"rows"}:
                raise CatalogFileError("JSON object form must contain only a rows array; use an array for raw records")
            values, prefix = values["rows"], "/rows"
        if not isinstance(values, list) or len(values) > MAX_ROWS:
            raise CatalogFileError(f"JSON needs an array of at most {MAX_ROWS} objects")
        for index, value in enumerate(values):
            if not isinstance(value, dict) or not value:
                raise CatalogFileError(f"JSON {prefix}/{index}: expected a nonempty row object")
            records.append({"record": index + 1, "location": {"json_pointer": f"{prefix}/{index}"},
                            "fields": _json_value(value)})
    if not records:
        raise CatalogFileError("catalog has no data records")
    return ParsedCatalog(source=source, records=tuple(records))


def read_catalog(path: str | Path, format: str | None = None) -> ParsedCatalog:
    path = Path(path)
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    return parse_bytes(raw, path.name, format)


def map_fields(catalog: ParsedCatalog, mapping: dict[str, str] | None = None,
               defaults: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Rename explicit headers, keeping unmapped fields; never overwrite values."""
    mapping = {} if mapping is None else mapping
    defaults = {} if defaults is None else defaults
    if not isinstance(mapping, dict) or any(not isinstance(k, str) or not k or not isinstance(v, str) or not v
                                            for k, v in mapping.items()):
        raise CatalogFileError("mapping must pair nonempty source and destination names")
    if not isinstance(defaults, dict):
        raise CatalogFileError("defaults must be a JSON object")
    available = {name for record in catalog.records for name in record["fields"]}
    absent = set(mapping) - available
    if absent:
        raise CatalogFileError("mapped source columns not found: " + ", ".join(sorted(absent)))
    output = []
    for record in catalog.records:
        fields = {}
        for name, value in record["fields"].items():
            target = mapping.get(name, name)
            if target in fields:
                raise CatalogFileError(f"record {record['record']}: mapping collides at {target!r}")
            fields[target] = value
        for name, value in defaults.items():
            if name not in fields or fields[name] == "":
                fields[name] = value
        output.append({"fields": fields, "provenance": {**catalog.source, **record["location"], "record": record["record"]}})
    return output


def _config(path: Path | None) -> dict[str, Any] | None:
    """Read explicit CLI options without dropping keys or rounding decimals."""
    if path is None:
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"), parse_float=Decimal,
                           parse_constant=_finite_json, object_pairs_hook=_unique_object)
    except UnicodeDecodeError as exc:
        raise CatalogFileError(f"{path.name}: configuration must be UTF-8; invalid byte near offset {exc.start}") from None
    except json.JSONDecodeError as exc:
        raise CatalogFileError(f"{path.name}: JSON line {exc.lineno}, column {exc.colno}: {exc.msg}") from None
    except InvalidOperation:
        raise CatalogFileError(f"{path.name}: JSON number exceeds the supported decimal range") from None
    except CatalogFileError as exc:
        raise CatalogFileError(f"{path.name}: {exc}") from None
    if not isinstance(value, dict):
        raise CatalogFileError(f"{path.name}: configuration must be a JSON object")
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--format", choices=("csv", "json"))
    parser.add_argument("--mapping", type=Path, help="JSON source-column to canonical-column map")
    parser.add_argument("--defaults", type=Path, help="JSON defaults for absent/empty columns")
    parser.add_argument("--output", type=Path, help="new preview file; never overwrites an existing file")
    args = parser.parse_args(argv)
    try:
        catalog = read_catalog(args.file, args.format)
        mapping = _config(args.mapping)
        # Match catalog JSON normalization for defaults, but do not coerce a
        # numeric mapping destination into a valid string column name.
        defaults = _json_value(_config(args.defaults))
        doc = {"format": "parts-catalog-preview-v1", "source": catalog.source,
               "rows": map_fields(catalog, mapping, defaults), "applied": False,
               "supplier_contact": "not_performed", "compatibility": "not_inferred"}
        encoded = json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        if args.output:
            with args.output.open("x", encoding="utf-8") as stream:
                stream.write(encoded)
        else:
            print(encoded, end="")
        return 0
    except (CatalogFileError, OSError, ValueError) as exc:
        parser.exit(2, f"catalog-file: {exc}\n")


if __name__ == "__main__":
    main()
