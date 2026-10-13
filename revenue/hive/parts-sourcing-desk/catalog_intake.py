#!/usr/bin/env python3
"""Prepare source-linked catalog files for the existing Parts Sourcing Desk.

Preview is the default. Optional apply uses only the canonical Desk transaction;
this companion defines no database schema, fit review, order, or network logic.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from catalog_file import CatalogFileError, ParsedCatalog, map_fields, read_catalog
from parts_desk import MAX_BODY, Desk, DeskError, catalog_data, dumps

MAX_IMPORT_ROWS = 2000  # The canonical Desk catalog transaction's batch contract.
PROVENANCE_LABEL = "[catalog-file provenance] "


def prepare_import(catalog: ParsedCatalog, mapping: dict[str, str] | None = None,
                   defaults: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return an import-ready payload plus its original-field/source preview.

    The payload is reusable unchanged across network/process retries. New bytes,
    filenames or mapped fields yield a new operation ID. Required identifiers and
    observation dates come from the input, never inferred from the file or clock.
    """
    mapped = map_fields(catalog, mapping, defaults)
    if not 1 <= len(mapped) <= MAX_IMPORT_ROWS:
        raise CatalogFileError(f"desk import needs 1-{MAX_IMPORT_ROWS} records; split the source file")
    items, identities = [], set()
    for record in mapped:
        fields = record["fields"]
        provenance = dict(record["provenance"])
        try:
            item = catalog_data(fields)
            # Retain supplier columns outside the canonical schema in evidence.
            # The canonical validator remains the only application field schema.
            extras = {key: value for key, value in fields.items() if key not in item}
            if extras:
                provenance["extra_fields"] = extras
            note = item["source_note"]
            item["source_note"] = (note + "\n" if note else "") + PROVENANCE_LABEL + dumps(provenance)
            item = catalog_data(item)
        except (DeskError, ValueError, TypeError) as exc:
            raise CatalogFileError(f"record {record['provenance']['record']} {dumps(record['provenance'])}: {exc}") from None
        if item["id"] in identities:
            raise CatalogFileError(f"record {record['provenance']['record']}: duplicate catalog id {item['id']!r}")
        identities.add(item["id"])
        items.append(item)
    digest = hashlib.sha256(dumps({"format": "parts-catalog-intake-v1", "items": items}).encode("utf-8")).hexdigest()
    payload = {"operation_id": "catalog-file-" + digest, "items": items}
    # An import-ready payload must also fit the existing HTTP road after metadata
    # expansion, even when the original file fit the reader's larger byte limit.
    if len(dumps(payload).encode("utf-8")) > MAX_BODY:
        raise CatalogFileError(f"prepared payload exceeds the desk's {MAX_BODY}-byte body limit; split the source file")
    return {"format": "parts-catalog-intake-v1", "source": dict(catalog.source),
            "rows": mapped, "payload": payload, "applied": False,
            "supplier_contact": "not_performed", "compatibility": "not_inferred"}


def _config(path: Path | None) -> dict | None:
    if path is None:
        return None
    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise CatalogFileError(f"{path.name}: duplicate configuration key {key!r}")
            result[key] = value
        return result
    def constant(value):
        raise CatalogFileError(f"{path.name}: non-finite configuration value {value}")
    value = json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=object_pairs,
                       parse_constant=constant)
    if not isinstance(value, dict):
        raise CatalogFileError(f"{path.name}: configuration must be a JSON object")
    return value


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--format", choices=("csv", "json"))
    parser.add_argument("--mapping", type=Path)
    parser.add_argument("--defaults", type=Path)
    parser.add_argument("--output", type=Path, help="write a new preview file; leave existing files unchanged")
    parser.add_argument("--apply", action="store_true", help="apply the prepared payload through the existing Desk")
    parser.add_argument("--db", type=Path, help="existing desk database, used only with --apply")
    args = parser.parse_args(argv)
    if args.apply != (args.db is not None):
        parser.error("use --apply and --db together; otherwise this command only previews")
    try:
        prepared = prepare_import(read_catalog(args.file, args.format), _config(args.mapping), _config(args.defaults))
        if args.apply and not args.db.is_file():
            raise CatalogFileError("desk database does not exist; start the canonical desk first")
        # Save the preview before any mutation; an existing/unwritable output
        # cannot turn a failed preview write into an unreported applied import.
        if args.output:
            with args.output.open("x", encoding="utf-8") as stream:
                stream.write(json.dumps(prepared, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
        if args.apply:
            result = Desk(args.db).mutate("catalog", "", prepared["payload"])
            print(dumps({"format": "parts-catalog-apply-result-v1", "source": prepared["source"],
                         "operation_id": prepared["payload"]["operation_id"], "applied": True,
                         "result": result, "supplier_contact": "not_performed"}))
        elif not args.output:
            print(json.dumps(prepared, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (CatalogFileError, DeskError, OSError, ValueError, sqlite3.Error) as exc:
        parser.exit(2, f"catalog-intake: {exc}\n")


if __name__ == "__main__":
    main()
