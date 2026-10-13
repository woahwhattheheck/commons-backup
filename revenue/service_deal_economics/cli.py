from __future__ import annotations

import argparse
import sys

from .authority import AuthorityError
from .current_runtime import (
    assert_current_runtime,
    compile_current,
    render_current_markdown,
    verify_current_authority,
)
from .engine import DealEconomicsError, canonical_json, read_json_file, write_exclusive


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="service-deal-economics")
    sub = parser.add_subparsers(dest="command", required=True)

    compile_cmd = sub.add_parser("compile", help="compile a current authority-gated owner-review economics packet")
    compile_cmd.add_argument("input")
    compile_cmd.add_argument("output")
    compile_cmd.add_argument("--markdown", dest="markdown")

    verify_cmd = sub.add_parser("verify", help="verify historical receipt plus current fixed-host input authority")
    verify_cmd.add_argument("input")
    verify_cmd.add_argument("report")
    return parser


def _build_main(parser_factory, assert_runtime, compile_current_fn, verify_current_fn, render_fn, read_fn, write_fn, canonical_fn):
    # Keep CURRENT dependencies in closure cells so main(argv) has no hidden
    # caller-overridable trust/clock/provider keyword arguments.
    def main(argv: list[str] | None = None) -> int:
        args = parser_factory().parse_args(argv)
        try:
            assert_runtime()
            if args.command == "compile":
                packet = read_fn(args.input)
                report = compile_current_fn(packet)
                write_fn(args.output, canonical_fn(report) + "\n")
                if args.markdown:
                    write_fn(args.markdown, render_fn(report))
                print(report["state"])
                print(report["receipt_sha256"])
                return 0 if report["state"] == "READY_FOR_OWNER_QUOTE_REVIEW" else 2

            packet = read_fn(args.input)
            report = read_fn(args.report)
            result = verify_current_fn(packet, report)
            print(canonical_fn(result))
            return 0 if result["state"] == "CURRENT_VERIFIED" else 2
        except (DealEconomicsError, AuthorityError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2

    return main


main = _build_main(
    build_parser,
    assert_current_runtime,
    compile_current,
    verify_current_authority,
    render_current_markdown,
    read_json_file,
    write_exclusive,
    canonical_json,
)
del _build_main


if __name__ == "__main__":
    raise SystemExit(main())
