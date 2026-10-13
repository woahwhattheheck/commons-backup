from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .core import IntakeError, compile_document, parse_strict_json, verify_record, write_bundle


def _historical(value: str) -> datetime:
    if not value.endswith("Z"):
        raise argparse.ArgumentTypeError("historical time must be UTC Z")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00").astimezone(timezone.utc)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("invalid historical time") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="external-opportunity-intake")
    sub = parser.add_subparsers(dest="command", required=True)
    current = sub.add_parser("compile-current", help="compile with a process-owned current UTC clock")
    current.add_argument("input")
    current.add_argument("output_dir")
    replay = sub.add_parser("compile-historical", help="integrity replay; can never emit current READY")
    replay.add_argument("input")
    replay.add_argument("output_dir")
    replay.add_argument("--at", required=True, type=_historical)
    verify = sub.add_parser("verify")
    verify.add_argument("record")
    args = parser.parse_args(argv)
    try:
        if args.command == "verify":
            record = parse_strict_json(Path(args.record).read_bytes())
            verify_record(record)
            print(record["receipt_sha256"])
            return 0
        document = parse_strict_json(Path(args.input).read_bytes())
        record = write_bundle(document, args.output_dir, historical_at=getattr(args, "at", None))
        print(json.dumps({"state": record["state"], "receipt_sha256": record["receipt_sha256"]}, sort_keys=True))
        return 0
    except (IntakeError, OSError) as exc:
        parser.exit(2, f"error: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
