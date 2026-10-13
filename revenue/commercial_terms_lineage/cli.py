"""CLI for offline commercial terms lineage compilation / verification."""
from __future__ import annotations

import argparse
import json
import sys

try:
    from .lineage import TermsLineageError, canonical_bytes, render_markdown
    from .runtime import compile_current, read_json_file, verify_current, write_exclusive
except ImportError:  # direct script execution from the package directory
    from lineage import TermsLineageError, canonical_bytes, render_markdown  # type: ignore
    from runtime import compile_current, read_json_file, verify_current, write_exclusive  # type: ignore


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    compile_p = sub.add_parser("compile-current", help="compile using process-owned current UTC + current policy guard")
    compile_p.add_argument("--authority", required=True)
    compile_p.add_argument("--review", required=True)
    compile_p.add_argument("--previous-authority")
    compile_p.add_argument("--output-json", required=True)
    compile_p.add_argument("--output-markdown", required=True)

    verify_p = sub.add_parser(
        "verify",
        help="verify historical receipt bytes, then recompute fresh current readiness",
    )
    verify_p.add_argument("--authority", required=True)
    verify_p.add_argument("--review", required=True)
    verify_p.add_argument("--previous-authority")
    verify_p.add_argument("--receipt", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        authority = read_json_file(args.authority)
        review = read_json_file(args.review)
        previous = read_json_file(args.previous_authority) if args.previous_authority else None
        if args.command == "compile-current":
            receipt = compile_current(
                authority,
                review,
                previous_authority=previous,
            )
            json_text = canonical_bytes(receipt).decode("utf-8") + "\n"
            md_text = render_markdown(receipt)
            write_exclusive(args.output_json, json_text)
            write_exclusive(args.output_markdown, md_text)
            print(json.dumps({"state": receipt["state"], "receipt_sha256": receipt["receipt_sha256"]}, sort_keys=True))
            return 0
        receipt = read_json_file(args.receipt)
        verified = verify_current(
            authority,
            review,
            receipt,
            previous_authority=previous,
        )
        print(
            json.dumps(
                {
                    "verified": True,
                    "current_state": verified["state"],
                    "current_compiled_at": verified["compiled_at"],
                    "current_receipt_sha256": verified["receipt_sha256"],
                },
                sort_keys=True,
            )
        )
        return 0
    except TermsLineageError as exc:
        print(f"commercial-terms-lineage: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
