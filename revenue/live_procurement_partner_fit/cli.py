"""Offline CLI for live_procurement_partner_fit."""
from __future__ import annotations
import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Any
from .core import QualificationError, canonical_json, compile_partner_fit, verify_receipt


def _reject_constant(value: str) -> Any:
    raise ValueError(f"non-finite JSON constant is not allowed: {value}")


def _load(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=_reject_constant)


def _now(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("--now must be timezone-aware")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m revenue.live_procurement_partner_fit", description="Offline pre-Muse partner-fit qualification. Never sends externally.")
    sub = parser.add_subparsers(dest="command", required=True)
    compile_cmd = sub.add_parser("compile")
    compile_cmd.add_argument("--input", required=True)
    compile_cmd.add_argument("--now", required=True)
    verify_cmd = sub.add_parser("verify")
    verify_cmd.add_argument("--input", required=True)
    verify_cmd.add_argument("--receipt", required=True)
    verify_cmd.add_argument("--now", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = _load(args.input)
        now = _now(args.now)
        if args.command == "compile":
            sys.stdout.write(canonical_json(compile_partner_fit(payload, now=now)) + "\n")
            return 0
        receipt = _load(args.receipt)
        ok = verify_receipt(payload, receipt, now=now)
        sys.stdout.write(canonical_json({"verified": ok}) + "\n")
        return 0 if ok else 1
    except (OSError, json.JSONDecodeError, ValueError, QualificationError) as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        return 2
