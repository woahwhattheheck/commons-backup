from __future__ import annotations

import argparse
import sys

from .core import (
    ValidationError,
    VerificationError,
    compile_snapshot,
    loads_strict_json,
    read_text_file,
    verify_compilation,
    write_compilation,
)


def _load_json(path: str):
    return loads_strict_json(read_text_file(path))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Compile/verify a retained Slack custody publication preflight")
    sub = parser.add_subparsers(dest="command", required=True)

    compile_p = sub.add_parser("compile")
    compile_p.add_argument("snapshot")
    compile_p.add_argument("output_prefix")

    verify_p = sub.add_parser("verify")
    verify_p.add_argument("snapshot")
    verify_p.add_argument("report_json")
    verify_p.add_argument("report_markdown")
    verify_p.add_argument("receipt_json")

    args = parser.parse_args(argv)
    try:
        if args.command == "compile":
            snapshot = _load_json(args.snapshot)
            report, markdown, receipt = compile_snapshot(snapshot)
            created = write_compilation(args.output_prefix, report, markdown, receipt)
            print("COMPILED " + " ".join(created))
            return 0
        snapshot = _load_json(args.snapshot)
        report = _load_json(args.report_json)
        markdown = read_text_file(args.report_markdown)
        receipt = _load_json(args.receipt_json)
        verify_compilation(snapshot, report, markdown, receipt)
        print("VERIFIED")
        return 0
    except (ValidationError, VerificationError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
