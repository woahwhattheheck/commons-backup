"""Organization-level outreach pressure gate.

This module is deliberately non-sending. It authenticates a retained organization
scope and retained cross-contact event ledger, then decides whether the organization
is quiet enough to advance to existing single-writer and provider-bound controls.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

from .core import (
    AUTHORITY_SCHEMA,
    DECISIONS,
    EVENT_AUTO_REPLY,
    EVENT_DNR,
    EVENT_HARD_BOUNCE,
    EVENT_HUMAN_REPLY,
    EVENT_KINDS,
    EVENT_OWNER_RELEASE,
    EVENT_PROPOSED,
    EVENT_SENT,
    EVENT_UNSUBSCRIBE,
    HOLD_AUTHORITY,
    HOLD_CONFLICT,
    HOLD_DNR,
    HOLD_HUMAN_REPLY,
    HOLD_ORG_ACTIVE,
    HOLD_RECENT_CONTACT,
    KEY_POINTER_SCHEMA,
    LEDGER_SCHEMA,
    READY,
    RECEIPT_SCHEMA,
    RELEASABLE_KINDS,
    REQUEST_SCHEMA,
    AuthorityUnavailable,
    InputError,
    VerificationError,
    _canonical_bytes,
    _hmac_hex,
    _parse_time,
    _sha256,
    strict_json_loads,
)
from .records import _normalize_event, _normalize_request
from .receipts import compile_current, verify_receipt_current, verify_receipt_integrity
from .storage import _read_request_file, _write_exclusive


def _render_receipt(receipt: dict[str, object]) -> bytes:
    return _canonical_bytes(receipt) + b"\n"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="organization-contact-pressure")
    subparsers = parser.add_subparsers(dest="command", required=True)
    compile_parser = subparsers.add_parser("compile", help="compile a current organization-pressure receipt")
    compile_parser.add_argument("request", type=Path)
    compile_parser.add_argument("output", type=Path)
    verify_parser = subparsers.add_parser("verify", help="verify a receipt; READY is revalidated current")
    verify_parser.add_argument("receipt", type=Path)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "compile":
            request_data = _read_request_file(args.request)
            receipt = compile_current(request_data)
            _write_exclusive(args.output, _render_receipt(receipt))
            return 0 if receipt["decision"] == READY else 3
        if args.command == "verify":
            receipt_data = _read_request_file(args.receipt)
            verify_receipt_current(receipt_data)
            return 0
        parser.error("unsupported command")
    except InputError as exc:
        print(f"INPUT_ERROR: {exc}", file=sys.stderr)
        return 2
    except (AuthorityUnavailable, VerificationError) as exc:
        print(f"AUTHORITY_ERROR: {exc}", file=sys.stderr)
        return 4
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
