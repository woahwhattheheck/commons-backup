"""CLI for provider cost truth receipts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .codec import GateError, loads_strict_json
from .engine import compile_current, verify_receipt


def _read(path: str):
    return loads_strict_json(Path(path).read_bytes())


def _dump(value) -> None:
    print(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile/verify provider cost-truth receipts")
    sub = parser.add_subparsers(dest="command", required=True)
    c = sub.add_parser("compile", help="compile a fresh current cost-truth receipt")
    c.add_argument("snapshot")
    v = sub.add_parser("verify", help="verify historical receipt integrity (never current authority)")
    v.add_argument("snapshot")
    v.add_argument("receipt")
    args = parser.parse_args(argv)
    try:
        if args.command == "compile":
            _dump(compile_current(_read(args.snapshot)))
            return 0
        ok = verify_receipt(_read(args.snapshot), _read(args.receipt))
        _dump({
            "integrity_valid": bool(ok),
            "current_delegation_authorized": False,
            "provider_session_authorized": False,
            "spend_authorized": False,
        })
        return 0
    except (GateError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
