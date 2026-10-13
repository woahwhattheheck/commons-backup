from __future__ import annotations

import argparse
import json
from typing import Any, Sequence

from .common import (
    ProofError, RECEIPT_SCHEMA, SCHEMA, _sha, loads_strict, read_json_file, validate_spec,
)
from .engine import build_proof
from .receipt import verify_receipt

__all__ = [
    "ProofError", "RECEIPT_SCHEMA", "SCHEMA", "_sha", "build_proof",
    "loads_strict", "read_json_file", "validate_spec", "verify_receipt",
]

def _write_json(value: Any) -> None:
    print(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build or verify deterministic reconciliation proof receipts")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--verify-receipt", metavar="PATH")
    mode.add_argument("--spec", metavar="PATH")
    parser.add_argument("--left", metavar="PATH")
    parser.add_argument("--right", metavar="PATH")
    parser.add_argument("--as-of", metavar="UTC_Z")
    args = parser.parse_args(argv)
    try:
        if args.verify_receipt:
            receipt = read_json_file(args.verify_receipt)
            verify_receipt(receipt)
            _write_json({"valid": True, "receipt_sha256": receipt["receipt_sha256"]})
            return 0
        if not args.left or not args.right or not args.as_of:
            parser.error("--spec mode requires --left, --right, and --as-of")
        receipt = build_proof(
            read_json_file(args.spec),
            read_json_file(args.left),
            read_json_file(args.right),
            as_of=args.as_of,
        )
        _write_json(receipt)
        return 0 if receipt["status"] == "RECONCILED_FOR_HUMAN_REVIEW" else 3
    except ProofError as exc:
        _write_json({"error": str(exc), "status": "INVALID_INPUT"})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
