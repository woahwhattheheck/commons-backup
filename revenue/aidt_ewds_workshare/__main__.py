"""Offline JSON-file interface to the AIDT consistency compiler.

No transport, scheduling, live-system access or source authentication is performed.
Use private storage for identifiers; all output is create-only or standard output.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .core import (MAX_CANONICAL_BYTES, WorkshareError, compile_readiness,
                   compile_sync_receipt, reconcile_migration,
                   verify_migration_receipt, verify_readiness, verify_sync_receipt)


def _load(path: Path):
    with path.open("rb") as source:
        raw = source.read(MAX_CANONICAL_BYTES + 1)
    if len(raw) > MAX_CANONICAL_BYTES:
        raise WorkshareError("input exceeds byte limit")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise WorkshareError("duplicate JSON key")
            result[key] = value
        return result

    def no_float(value):
        raise WorkshareError("floating-point values are not part of this receipt schema")

    def integer(value):
        if len(value.lstrip("-")) > 16:
            raise WorkshareError("integer exceeds receipt schema bound")
        return int(value)

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                          parse_float=no_float, parse_constant=no_float,
                          parse_int=integer)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise WorkshareError(f"invalid receipt JSON: {exc}") from exc


def _write(result, output: Path | None):
    text = json.dumps(result, sort_keys=True, ensure_ascii=True, indent=2,
                      allow_nan=False) + "\n"
    if output is None:
        sys.stdout.write(text)
    else:
        # Complete computation precedes create-exclusive publication. No overwrite.
        with output.open("x", encoding="utf-8", newline="\n") as destination:
            destination.write(text)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    migration = commands.add_parser("migration", help="compare ID/digest arrays")
    migration.add_argument("source", type=Path)
    migration.add_argument("target", type=Path)
    sync = commands.add_parser("sync", help="compare event and target observation")
    sync.add_argument("event", type=Path)
    sync.add_argument("observed", type=Path)
    readiness = commands.add_parser("readiness", help="evaluate the supplied current collection")
    readiness.add_argument("evidence", type=Path)
    readiness.add_argument("migrations", type=Path, help="JSON array of V2 migration receipts")
    readiness.add_argument("syncs", type=Path, help="JSON array of V2 sync receipts")
    verify = commands.add_parser("verify", help="replay one receipt's internal semantics")
    verify.add_argument("receipt", type=Path)
    verify.add_argument("--expected-source-manifest-sha256")
    verify.add_argument("--expected-target-manifest-sha256")
    for command in (migration, sync, readiness, verify):
        command.add_argument("--out", type=Path, help="new file; default is standard output")
    args = parser.parse_args(argv)
    try:
        if args.command == "migration":
            result = reconcile_migration(_load(args.source), _load(args.target))
        elif args.command == "sync":
            result = compile_sync_receipt(_load(args.event), _load(args.observed))
        elif args.command == "readiness":
            result = compile_readiness(_load(args.evidence), _load(args.migrations), _load(args.syncs))
        else:
            receipt = _load(args.receipt)
            if type(receipt) is not dict:
                raise WorkshareError("receipt must be a JSON object")
            schema = receipt.get("schema")
            source_pin = args.expected_source_manifest_sha256
            target_pin = args.expected_target_manifest_sha256
            if schema == "aidt-ewds-migration/v2":
                verify_migration_receipt(receipt, expected_source_manifest_sha256=source_pin,
                                        expected_target_manifest_sha256=target_pin)
            else:
                if source_pin is not None or target_pin is not None:
                    raise WorkshareError("independent manifest pins apply only to migration receipts")
                if schema == "aidt-ewds-sync/v2":
                    verify_sync_receipt(receipt)
                elif schema == "aidt-ewds-readiness/v2":
                    verify_readiness(receipt)
                else:
                    raise WorkshareError("V2 receipt required; regenerate legacy receipts from inputs")
            result = {"state": "VERIFIED_INTERNAL_CONSISTENCY", "schema": schema,
                      "receipt_sha256": receipt["receipt_sha256"],
                      "independent_source_pin_checked": source_pin is not None,
                      "independent_target_pin_checked": target_pin is not None,
                      "external_source_authenticity_established": False}
        _write(result, args.out)
        return 0
    except (OSError, WorkshareError, KeyError, RecursionError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
