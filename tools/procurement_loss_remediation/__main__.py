#!/usr/bin/env python3
"""CLI for procurement loss/debrief remediation receipts."""
from __future__ import annotations

import argparse
import json
import sys

from tools.procurement_win_loss import OutcomeError
from tools.procurement_win_loss.compiler import load_json_file

from .core import RemediationError
from .policy import compile_plan
from .verifier import RemediationVerificationError, verify_plan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    compile_cmd = sub.add_parser("compile", help="compile a remediation plan to stdout")
    compile_cmd.add_argument("input")
    verify_cmd = sub.add_parser("verify", help="verify a remediation receipt")
    verify_cmd.add_argument("input")
    verify_cmd.add_argument("receipt")
    args = parser.parse_args(argv)

    try:
        if args.command == "compile":
            result = compile_plan(load_json_file(args.input))
        else:
            result = verify_plan(load_json_file(args.input), load_json_file(args.receipt))
    except (OutcomeError, RemediationError, RemediationVerificationError, OSError, RecursionError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
