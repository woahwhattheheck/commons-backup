from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

from .common import ControlError, canonical_bytes, require_timestamp
from .control import (
    compile_current_bytes,
    compile_historical_bytes,
    render_markdown,
    verify_current_bytes,
    verify_integrity_bytes,
)
from .io import read_bounded_regular, write_exclusive_pair


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="teaming-conversion-control")
    sub = parser.add_subparsers(dest="command", required=True)

    current = sub.add_parser("compile-current", help="compile using repository-owned current roots")
    current.add_argument("--candidate", required=True)
    current.add_argument("--evidence", required=True)
    current.add_argument("--json-output", required=True)
    current.add_argument("--markdown-output", required=True)

    verify_current = sub.add_parser("verify-current", help="re-evaluate with current roots and UTC")
    verify_current.add_argument("--candidate", required=True)
    verify_current.add_argument("--evidence", required=True)
    verify_current.add_argument("--receipt", required=True)

    historical = sub.add_parser(
        "compile-history",
        help="compile explicit replay evidence; output is historical-integrity-only",
    )
    historical.add_argument("--candidate", required=True)
    historical.add_argument("--evidence", required=True)
    historical.add_argument("--roots", required=True)
    historical.add_argument("--as-of", required=True)
    historical.add_argument("--json-output", required=True)
    historical.add_argument("--markdown-output", required=True)

    verify_history = sub.add_parser(
        "verify-integrity",
        help="verify exact receipt bytes without making a current-readiness claim",
    )
    verify_history.add_argument("--candidate", required=True)
    verify_history.add_argument("--evidence", required=True)
    verify_history.add_argument("--roots", required=True)
    verify_history.add_argument("--receipt", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        candidate = read_bounded_regular(args.candidate)
        evidence = read_bounded_regular(args.evidence)
        if args.command == "compile-current":
            receipt = compile_current_bytes(candidate, evidence)
            receipt_bytes = canonical_bytes(receipt)
            markdown_bytes = render_markdown(receipt).encode("utf-8")
            write_exclusive_pair(
                args.json_output,
                receipt_bytes,
                args.markdown_output,
                markdown_bytes,
            )
            print(f"CURRENT {receipt['disposition']} {receipt['decision_sha256']}")
            return 0
        if args.command == "verify-current":
            receipt_bytes = read_bounded_regular(args.receipt)
            result = verify_current_bytes(candidate, evidence, receipt_bytes)
            status = "CURRENT_VALID" if result["current_valid"] else "CURRENT_INVALID"
            print(f"{status} {result['current_disposition']} {result['current_decision_sha256']}")
            return 0 if result["current_valid"] else 2
        roots = read_bounded_regular(args.roots)
        if args.command == "compile-history":
            as_of = require_timestamp(args.as_of, "--as-of")
            receipt = compile_historical_bytes(
                candidate,
                evidence,
                roots,
                evaluated_at=as_of,
            )
            receipt_bytes = canonical_bytes(receipt)
            markdown_bytes = render_markdown(receipt).encode("utf-8")
            write_exclusive_pair(
                args.json_output,
                receipt_bytes,
                args.markdown_output,
                markdown_bytes,
            )
            print(f"HISTORICAL_INTEGRITY_ONLY {receipt['disposition']} {receipt['decision_sha256']}")
            return 0
        receipt_bytes = read_bounded_regular(args.receipt)
        valid = verify_integrity_bytes(candidate, evidence, roots, receipt_bytes)
        print("HISTORICAL_INTEGRITY_VALID" if valid else "HISTORICAL_INTEGRITY_INVALID")
        return 0 if valid else 2
    except ControlError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
