"""CLI for the deterministic opportunity portfolio compiler."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .portfolio import PortfolioError, compile_portfolio, render_markdown, verify_receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile or verify a source-bound revenue opportunity portfolio")
    sub = parser.add_subparsers(dest="command", required=True)

    compile_cmd = sub.add_parser("compile")
    compile_cmd.add_argument("input", type=Path)
    compile_cmd.add_argument("--trusted-as-of", required=True, help="UTC RFC3339 instant supplied outside the opportunity packet")
    compile_cmd.add_argument("--receipt", type=Path, required=True)
    compile_cmd.add_argument("--markdown", type=Path)

    verify_cmd = sub.add_parser("verify")
    verify_cmd.add_argument("receipt", type=Path)

    args = parser.parse_args(argv)
    try:
        if args.command == "compile":
            data = json.loads(args.input.read_text(encoding="utf-8"))
            receipt = compile_portfolio(data, trusted_as_of=args.trusted_as_of)
            args.receipt.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
            if args.markdown:
                args.markdown.write_text(render_markdown(receipt), encoding="utf-8")
            print(receipt["receiptDigestSha256"])
            return 0
        receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
        verify_receipt(receipt)
        print(receipt["receiptDigestSha256"])
        return 0
    except (PortfolioError, json.JSONDecodeError, OSError) as exc:
        print(f"HOLD: {exc}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
