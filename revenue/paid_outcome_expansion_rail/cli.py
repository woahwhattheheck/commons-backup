"""CLI for offline evaluation, receipt verification, and synthetic acceptance."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .acceptance import run_acceptance
from .rail import canonical_json, evaluate, verify_receipt


def _load(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="paid-outcome-expansion")
    sub = parser.add_subparsers(dest="command", required=True)
    evaluate_cmd = sub.add_parser("evaluate")
    evaluate_cmd.add_argument("input")
    verify_cmd = sub.add_parser("verify")
    verify_cmd.add_argument("receipt")
    sub.add_parser("acceptance")
    args = parser.parse_args(argv)
    if args.command == "evaluate":
        receipt = evaluate(_load(args.input))
        print(canonical_json(receipt))
        return 0 if receipt["decision"] != "HOLD" else 2
    if args.command == "verify":
        valid = verify_receipt(_load(args.receipt))
        print("VALID" if valid else "INVALID")
        return 0 if valid else 2
    if args.command == "acceptance":
        print(canonical_json(run_acceptance()))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
