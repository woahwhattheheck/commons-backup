"""Import explicit CSV evidence registers and run the existing offline comparator.

No document identities, version order, or predecessor relationships are inferred.
Source files are read only; outputs are created exclusively at new paths.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import sys
from typing import Any

if __package__:
    from . import lineage
else:
    import lineage


REQUIRED = ("record_id", "document_id", "version", "title", "location")
OPTIONAL = ("sha256", "metadata_json", "supersedes_json")


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise lineage.InvalidInput(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _nonfinite(value: str) -> None:
    raise lineage.InvalidInput(f"non-finite JSON constant: {value}")


def _json_cell(value: str, expected: type, where: str) -> Any:
    try:
        parsed = json.loads(value, object_pairs_hook=_object, parse_constant=_nonfinite)
        # Also reject finite-looking JSON numeric literals that overflow to infinity.
        json.dumps(parsed, allow_nan=False)
    except (ValueError, TypeError, RecursionError) as exc:
        raise lineage.InvalidInput(f"{where}: invalid JSON ({exc})") from exc
    if not isinstance(parsed, expected):
        name = "object" if expected is dict else "array"
        raise lineage.InvalidInput(f"{where}: JSON {name} required")
    return parsed


def import_register(
    path: Path, *, collection_id: str, synthetic: bool, source_root: Path | None = None
) -> dict:
    """Preserve register strings and extensions; optionally hash explicitly named files."""
    lineage.text(collection_id, "collection_id")
    if type(synthetic) is not bool:
        raise lineage.InvalidInput("synthetic must be a boolean")
    with path.open("rb") as stream:
        raw = stream.read(lineage.MAX_BYTES + 1)
    if len(raw) > lineage.MAX_BYTES:
        raise lineage.InvalidInput(f"{path}: CSV exceeds {lineage.MAX_BYTES} bytes")
    # UTF-8 BOM is accepted for spreadsheet exports; malformed UTF-8 is not repaired.
    source = raw.decode("utf-8-sig")
    if "\x00" in source:
        raise lineage.InvalidInput(f"{path}: NUL characters are not supported")
    reader = csv.reader(io.StringIO(source, newline=""), strict=True)
    previous_limit = csv.field_size_limit(lineage.MAX_BYTES)
    records: list[dict] = []
    try:
        headers = next(reader, None)
        if not headers:
            raise lineage.InvalidInput(f"{path}: header row required")
        if any(not header.strip() for header in headers):
            raise lineage.InvalidInput(f"{path}: blank column name")
        if len(set(headers)) != len(headers):
            raise lineage.InvalidInput(f"{path}: duplicate column name")
        missing = [name for name in REQUIRED if name not in headers]
        if missing:
            raise lineage.InvalidInput(f"{path}: missing columns: {', '.join(missing)}")
        extra = [name for name in headers if name not in REQUIRED + OPTIONAL]
        seen: set[str] = set()
        for values in reader:
            if not values:  # A genuinely empty CSV line, not a row of empty cells.
                continue
            where = f"{path}:line {reader.line_num}"
            if len(values) != len(headers):
                raise lineage.InvalidInput(
                    f"{where}: expected {len(headers)} cells, received {len(values)}"
                )
            cells = dict(zip(headers, values))
            record = {name: lineage.text(cells[name], f"{where}.{name}") for name in REQUIRED}
            if record["record_id"] in seen:
                raise lineage.InvalidInput(f"{where}: duplicate record_id: {record['record_id']}")
            seen.add(record["record_id"])
            declared_hash = cells.get("sha256", "")
            if declared_hash:
                record["sha256"] = lineage.digest(declared_hash, f"{where}.sha256")
            elif source_root is None:
                raise lineage.InvalidInput(
                    f"{where}.sha256: provide a digest or an explicit source root"
                )
            metadata = cells.get("metadata_json", "")
            predecessors = cells.get("supersedes_json", "")
            if metadata:
                record["metadata"] = _json_cell(metadata, dict, f"{where}.metadata_json")
            if predecessors:
                record["supersedes"] = _json_cell(
                    predecessors, list, f"{where}.supersedes_json"
                )
            if extra:
                # Unknown export columns remain visible, including deliberately empty values.
                record["register_columns"] = {name: cells[name] for name in extra}
            records.append(record)
    except csv.Error as exc:
        raise lineage.InvalidInput(f"{path}:line {reader.line_num}: invalid CSV ({exc})") from exc
    finally:
        csv.field_size_limit(previous_limit)
    catalog = {
        "schema": lineage.SCHEMA,
        "collection_id": collection_id,
        "synthetic": synthetic,
        "records": records,
        "register_source": {
            "format": "csv",
            "name": path.name,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "columns": headers,
        },
    }
    if source_root is not None:
        return lineage.snapshot(catalog, source_root)
    catalog["hash_basis"] = "IMPORTED_SOURCE_ASSERTIONS_NOT_AUTHENTICATED"
    return lineage.validate_manifest(catalog)


def _write_new(path: Path, content: str) -> None:
    # Never silently replace an input, previous report, or another worker's output.
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(content)


def _data_kind(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--data-kind", required=True, choices=("private", "synthetic"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    manifest = commands.add_parser("manifest", help="convert one register to a new JSON manifest")
    manifest.add_argument("register", type=Path)
    manifest.add_argument("--collection-id", required=True)
    manifest.add_argument("--source-root", type=Path)
    manifest.add_argument("--output", required=True, type=Path)
    _data_kind(manifest)
    compare = commands.add_parser("compare", help="import two registers and write a new review directory")
    compare.add_argument("before", type=Path)
    compare.add_argument("after", type=Path)
    compare.add_argument("--before-id", required=True)
    compare.add_argument("--after-id", required=True)
    compare.add_argument("--before-root", type=Path)
    compare.add_argument("--after-root", type=Path)
    compare.add_argument("--findings", type=Path)
    compare.add_argument("--output-dir", required=True, type=Path)
    _data_kind(compare)
    args = parser.parse_args(argv)
    created_directory: Path | None = None
    try:
        synthetic = args.data_kind == "synthetic"
        if args.command == "manifest":
            result = import_register(
                args.register, collection_id=args.collection_id,
                synthetic=synthetic, source_root=args.source_root,
            )
            payload = lineage.encoded(result)
            _write_new(args.output, payload)
            print(f"Created {args.output} ({len(result['records'])} records)")
            return 0
        before = import_register(
            args.before, collection_id=args.before_id,
            synthetic=synthetic, source_root=args.before_root,
        )
        after = import_register(
            args.after, collection_id=args.after_id,
            synthetic=synthetic, source_root=args.after_root,
        )
        findings = lineage.load(args.findings) if args.findings is not None else None
        report = lineage.compare(before, after, findings)
        # Complete all parsing, comparison, and rendering before creating output files.
        outputs = {
            "before.json": lineage.encoded(before),
            "after.json": lineage.encoded(after),
            "review.json": lineage.encoded(report),
            "review.md": lineage.markdown(report),
        }
        args.output_dir.mkdir(parents=False, exist_ok=False)
        created_directory = args.output_dir
        for name, content in outputs.items():
            _write_new(args.output_dir / name, content)
        print(
            f"Created {args.output_dir}: {len(before['records'])} before records, "
            f"{len(after['records'])} after records; review.json and review.md"
        )
        print("Processing completed; review findings are not an assessment approval.")
        return 0
    except (ValueError, OSError, UnicodeError, TypeError, RecursionError) as exc:
        print(f"Register import failed: {exc}", file=sys.stderr)
        if created_directory is not None:
            print(
                f"Output may be incomplete in {created_directory}; no existing files were replaced.",
                file=sys.stderr,
            )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
