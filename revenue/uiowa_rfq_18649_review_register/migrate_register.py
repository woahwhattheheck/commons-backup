#!/usr/bin/env python3
"""Explicit, non-destructive migration of the historical event-register namespace.

The same old schema name also belongs to ORRERY's different patch-cycle format.
Only a complete, semantically valid legacy event register can be migrated.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

import review_register as rr

LEGACY_SCHEMA = "uiowa-rfq18649-review-cycle/v1"
MIGRATION_SCHEMA = "uiowa-rfq18649-review-register-migration/v1"
REGISTER_FIELDS = {"schema", "synthetic", "evidence", "reports", "comments"}
PATCH_CYCLE_FIELDS = {"schema", "id", "base_document_sha256", "base_report_receipt_sha256",
                      "target_report_receipt_sha256", "new_version", "comments"}


def migrate(packet: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return a detached register plus content-bound migration record.

    Only the top-level schema changes. Validation uses the full existing register
    engine; valid-looking root fields do not excuse malformed references/events.
    No finding, decision, report receipt, evidence locator, or source is modified.
    """
    if isinstance(packet, dict) and set(packet) == PATCH_CYCLE_FIELDS:
        rr.fail("packet", "canonical patch-cycle format belongs to review_cycle; not a legacy event register")
    rr.shape(packet, REGISTER_FIELDS, "packet")
    if packet["schema"] != LEGACY_SCHEMA:
        rr.fail("packet.schema", f"migration requires legacy {LEGACY_SCHEMA}; current registers compile directly")
    result = deepcopy(packet)
    result["schema"] = rr.SCHEMA
    response = rr.compile_cycle(result)
    receipt = {
        "schema": MIGRATION_SCHEMA,
        "status": "DRAFT_NON_AUTHORITATIVE",
        "synthetic": result["synthetic"],
        "operation": "EXPLICIT_NAMESPACE_MIGRATION",
        "source_schema": LEGACY_SCHEMA,
        "target_schema": rr.SCHEMA,
        "changed_fields": ["schema"],
        "source_packet_sha256": rr.sha(packet),
        "target_packet_sha256": rr.sha(result),
        "target_response_receipt_sha256": response["receipt_sha256"],
        "report_receipts_preserved": [r["receipt_sha256"] for r in result["reports"]],
        "authority": dict(rr.AUTHORITY),
        "limits": [
            "Digests bind canonical JSON content, not original file formatting or authenticity.",
            "Source packet and derived response digests change; retained report receipts do not.",
            "This migrates an event register, never ORRERY's patch-cycle document or a University finding.",
        ],
    }
    receipt["receipt_sha256"] = rr.sha(receipt)
    return result, receipt


def verify(source: dict[str, Any], target: dict[str, Any], receipt: dict[str, Any]) -> None:
    """Recompute from the source; resealing edited metadata is insufficient."""
    expected_target, expected_receipt = migrate(source)
    try:
        matches = (rr.canonical(target) == rr.canonical(expected_target)
                   and rr.canonical(receipt) == rr.canonical(expected_receipt))
    except (TypeError, ValueError, UnicodeError, RecursionError):
        rr.fail("migration", "invalid canonical JSON in migrated result or receipt")
    if not matches:
        rr.fail("migration", "result or receipt differs from source-bound namespace migration")


def encoded(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode("utf-8")


def write_bundle(source: Path, destination: Path) -> dict[str, Any]:
    """Validate/serialize first, then create a new directory without replacement.

    If an I/O failure interrupts writing, the new directory is incomplete and no
    manifest is written. No rollback deletes files. Verification can be rerun from
    the unchanged source into a different new directory.
    """
    packet = rr.strict_load(source)
    target, receipt = migrate(packet)
    files = {"register.json": encoded(target), "migration.json": encoded(receipt)}
    manifest = {
        "schema": "uiowa-rfq18649-review-register-migration-files/v1",
        "status": "DRAFT_NON_AUTHORITATIVE", "synthetic": target["synthetic"],
        "files": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())},
    }
    manifest_bytes = encoded(manifest)
    destination.mkdir(parents=False, exist_ok=False)
    for name, data in files.items():
        with (destination / name).open("xb") as stream:
            stream.write(data)
    with (destination / "manifest.json").open("xb") as stream:
        stream.write(manifest_bytes)
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("migrate", help="Validate legacy register and write a new directory")
    build.add_argument("source", type=Path)
    build.add_argument("--out", required=True, type=Path)
    check = commands.add_parser("verify", help="Recompute migration from its original source")
    check.add_argument("source", type=Path)
    check.add_argument("target", type=Path)
    check.add_argument("receipt", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "migrate":
            receipt = write_bundle(args.source, args.out)
            print("NAMESPACE_MIGRATED: only schema changed; source preserved; response receipt "
                  + receipt["target_response_receipt_sha256"])
        else:
            verify(rr.strict_load(args.source), rr.strict_load(args.target), rr.strict_load(args.receipt))
            print("SOURCE_BOUND_NAMESPACE_MIGRATION_VERIFIED; no approval or evidence authenticity established")
        return 0
    except (rr.ValidationError, OSError, TypeError, ValueError, RecursionError) as exc:
        print(f"migrate_register: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
