from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .authority import AuthorityError, load_trusted_registry, packet_from_text, verify_current, verify_historical, verify_receipt
from .strict_json import canonical_json, loads_strict


def _parse_utc(value: str) -> datetime:
    if not value.endswith("Z"):
        raise argparse.ArgumentTypeError("timestamp must end in Z")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00").astimezone(timezone.utc)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("invalid timestamp") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Trusted source-evidence authority kernel")
    sub = parser.add_subparsers(dest="command", required=True)

    current = sub.add_parser("verify-current", help="production/current authority verification; clock is process UTC only")
    current.add_argument("packet")
    current.add_argument("--registry", required=True)
    current.add_argument("--expected-registry-sha256", required=True)

    forensic = sub.add_parser("verify-forensic", help="historical replay; can never produce current authority")
    forensic.add_argument("packet")
    forensic.add_argument("--registry", required=True)
    forensic.add_argument("--expected-registry-sha256", required=True)
    forensic.add_argument("--as-of", required=True, type=_parse_utc)

    receipt = sub.add_parser("verify-receipt", help="verify receipt integrity only")
    receipt.add_argument("receipt")

    args = parser.parse_args(argv)
    try:
        if args.command == "verify-receipt":
            data = loads_strict(Path(args.receipt).read_text(encoding="utf-8"))
            ok = verify_receipt(data)
            print(json.dumps({"integrity_valid": ok}, sort_keys=True))
            return 0 if ok else 2

        registry = load_trusted_registry(args.registry, expected_file_sha256=args.expected_registry_sha256)
        packet = packet_from_text(Path(args.packet).read_text(encoding="utf-8"))
        if args.command == "verify-current":
            result = verify_current(packet, registry)
        else:
            result = verify_historical(packet, registry, as_of=args.as_of)
        print(canonical_json(result))
        return 0 if result["evidence_level"] != "HOLD" else 3
    except (OSError, AuthorityError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
