#!/usr/bin/env python3
"""Cheap always-on canary in front of trust-cache v1.

Proof is cached. Build unless the bytes moved.

v1 already keys receipts by (artifact_sha256, check_id). This slice is the
named input-set canary: every listed file must exist and have a readable
SHA-256, the ledger schema must be v1, and full checks run only for
UNVERIFIED or STALE. The artifact hashed for classify/run is the actual
concatenated bytes of those files, not a summary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from host import trust_cache


RULE = "Proof is cached. Build unless the bytes moved."
BUNDLE_MAGIC = b"commons-trust-cache-bundle/v1\n"
DEFAULT_LEDGER = trust_cache.DEFAULT_LEDGER


def _command_tail(values: list[str]) -> list[str]:
    return values[1:] if values[:1] == ["--"] else values


def canary_inputs(paths: list[Path]) -> list[dict[str, str]]:
    """Always-on cheap boundary: existence and readable hash per file."""
    rows = []
    for path in paths:
        digest = trust_cache.sha256_file(path)
        rows.append({"artifact": str(path), "artifact_sha256": digest})
    return rows


def write_bundle(paths: list[Path], dest: Path) -> str:
    """Write actual file bytes into a deterministic bundle and hash it."""
    ordered = sorted(paths, key=lambda path: path.as_posix())
    parts = [BUNDLE_MAGIC]
    for path in ordered:
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        rel = path.as_posix().encode("utf-8")
        parts.append(f"{len(rel)} {len(data)} {digest}\n".encode("ascii"))
        parts.append(rel)
        parts.append(b"\n")
        parts.append(data)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"".join(parts))
    return trust_cache.sha256_file(dest)


def inspect(
    paths: list[Path],
    check_id: str,
    ledger: Path,
    bundle: Path,
) -> dict[str, Any]:
    files = canary_inputs(paths)
    receipts = trust_cache.read_receipts(ledger)
    digest = write_bundle(paths, bundle)
    state = trust_cache.classify(digest, check_id, receipts)
    return {
        "rule": RULE,
        "schema_version": trust_cache.SCHEMA_VERSION,
        "canary": "PASS",
        "artifact": str(bundle),
        "artifact_sha256": digest,
        "check_id": check_id,
        "state": state,
        "inputs": files,
        "waste_count": sum(
            row["result"] == "WASTE"
            and row["artifact_sha256"] == digest
            and row["check_id"] == check_id
            for row in receipts
        ),
    }


def run_named_check(
    paths: list[Path],
    check_id: str,
    command: list[str],
    ledger: Path,
) -> tuple[dict[str, Any], int]:
    with tempfile.TemporaryDirectory(prefix="trust-cache-bundle-") as tmp:
        bundle = Path(tmp) / "bundle.bin"
        snapshot = inspect(paths, check_id, ledger, bundle)
        result, code = trust_cache.run_check(bundle, check_id, command, ledger)
        snapshot.update(result)
        if snapshot.get("event") == "WASTE" or snapshot.get("state") == "TRUSTED":
            snapshot["rule"] = RULE
        return snapshot, code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ledger",
        type=Path,
        default=DEFAULT_LEDGER,
        help=f"append-only JSONL ledger (default: {DEFAULT_LEDGER})",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    canary_parser = commands.add_parser("canary")
    canary_parser.add_argument("--input", dest="inputs", action="append", type=Path, required=True)
    canary_parser.add_argument("--check-id", default="canary")
    status_parser = commands.add_parser("status")
    status_parser.add_argument("--input", dest="inputs", action="append", type=Path, required=True)
    status_parser.add_argument("--check-id", required=True)
    run_parser = commands.add_parser("run")
    run_parser.add_argument("--input", dest="inputs", action="append", type=Path, required=True)
    run_parser.add_argument("--check-id", required=True)
    run_parser.add_argument("check_command", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    try:
        with tempfile.TemporaryDirectory(prefix="trust-cache-canary-") as tmp:
            bundle = Path(tmp) / "bundle.bin"
            if args.command == "run":
                output, code = run_named_check(
                    args.inputs,
                    args.check_id,
                    _command_tail(args.check_command),
                    args.ledger,
                )
            else:
                output = inspect(args.inputs, args.check_id, args.ledger, bundle)
                code = 0
        print(json.dumps(output, sort_keys=True))
        return code
    except (OSError, trust_cache.TrustCacheError) as error:
        print(f"TRUST_CACHE_ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
