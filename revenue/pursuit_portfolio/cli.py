"""CLI for authenticated current-use pursuit portfolio allocation."""
from __future__ import annotations

import argparse
import hashlib
import json

from .core import PortfolioError, load_json_bytes
from .current import MAX_AUTHORITY_BYTES, load_current_input, read_regular_bytes
from .host import compile_current, verify_current
from .publisher import publish_current, read_current


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pursuit-portfolio")
    sub = parser.add_subparsers(dest="command", required=True)

    compile_p = sub.add_parser(
        "compile",
        help="compile a fixed-host-authenticated current owner-review portfolio",
    )
    compile_p.add_argument("input")
    compile_p.add_argument("authority")
    compile_p.add_argument("output_dir", help="existing owner-controlled output directory")

    verify_p = sub.add_parser(
        "verify",
        help="verify host seal, historical integrity, and fresh-current semantics",
    )
    verify_p.add_argument("output_dir")

    args = parser.parse_args(argv)
    try:
        if args.command == "compile":
            source = load_current_input(args.input)
            authority_raw = read_regular_bytes(
                args.authority, MAX_AUTHORITY_BYTES, "upstream authority"
            )
            authority = load_json_bytes(authority_raw, "upstream authority")
            value = compile_current(source, authority)
            publish_current(value, args.output_dir)
            authorized = value.authorized
            print(
                json.dumps(
                    {
                        "authority_sha256": authorized.current_receipt["authority_sha256"],
                        "current_receipt_sha256": _digest(
                            authorized.current_receipt_bytes
                        ),
                        "host_seal_sha256": _digest(value.host_seal_bytes),
                        "output_dir": args.output_dir,
                        "selected_opportunity_ids": authorized.compiled.result[
                            "selected_opportunity_ids"
                        ],
                        "selected_priority_units": authorized.compiled.result[
                            "selected_priority_units"
                        ],
                    },
                    sort_keys=True,
                )
            )
            return 0

        result, markdown, receipt, authority, current_receipt, host_seal = read_current(
            args.output_dir
        )
        verified = verify_current(
            result,
            markdown,
            receipt,
            authority,
            current_receipt,
            host_seal,
        )
        print(json.dumps(verified, sort_keys=True))
        return 0
    except (PortfolioError, OSError) as exc:
        parser.exit(2, f"error: {exc}\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
