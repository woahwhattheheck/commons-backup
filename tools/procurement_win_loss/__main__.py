#!/usr/bin/env python3
"""CLI for the procurement win/loss evidence loop."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .compiler import OutcomeError, compile_record, load_json_file, render_receipt
from .verifier import VerificationError, verify_record


def _write(path: str, payload: bytes) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    compile_cmd = sub.add_parser("compile", help="compile redacted evidence into a deterministic receipt")
    compile_cmd.add_argument("input")
    compile_cmd.add_argument("output")
    verify_cmd = sub.add_parser("verify", help="independently verify a receipt against its evidence")
    verify_cmd.add_argument("input")
    verify_cmd.add_argument("receipt")
    args = parser.parse_args(argv)
    try:
        source = load_json_file(args.input)
        if args.command == "compile":
            receipt = compile_record(source)
            _write(args.output, render_receipt(receipt))
            print(json.dumps({"status": "COMPILED", "outcome": receipt["outcome"], "receipt_sha256": receipt["receipt_sha256"]}, sort_keys=True))
            return 0
        receipt = load_json_file(args.receipt)
        result = verify_record(source, receipt)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OutcomeError, VerificationError, OSError) as exc:
        print(json.dumps({"status": "ERROR", "error": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
