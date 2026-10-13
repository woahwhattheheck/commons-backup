"""CLI for the paid-discovery offer compiler."""
from __future__ import annotations

import argparse
import json
import sys

from .engine import (
    OfferError,
    audit_at,
    compile_current,
    read_strict_json_file,
    verify_current,
    verify_historical,
    write_bundle,
)


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Compile or verify an evidence-bound paid discovery offer")
    sub = p.add_subparsers(dest="command", required=True)
    cc = sub.add_parser("compile-current")
    cc.add_argument("input")
    cc.add_argument("roots")
    cc.add_argument("bundle")
    aa = sub.add_parser("audit-at")
    aa.add_argument("input")
    aa.add_argument("roots")
    aa.add_argument("at")
    aa.add_argument("bundle")
    vc = sub.add_parser("verify-current")
    vc.add_argument("input")
    vc.add_argument("roots")
    vc.add_argument("packet")
    vh = sub.add_parser("verify-historical")
    vh.add_argument("input")
    vh.add_argument("roots")
    vh.add_argument("packet")
    return p


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    try:
        candidate = read_strict_json_file(args.input)
        roots = read_strict_json_file(args.roots)
        if args.command == "compile-current":
            packet = compile_current(candidate, roots)
            result = write_bundle(args.bundle, packet)
            print(json.dumps({"decision": packet["decision"], **result}, sort_keys=True))
            return 0
        if args.command == "audit-at":
            packet = audit_at(candidate, roots, args.at)
            result = write_bundle(args.bundle, packet)
            print(json.dumps({"decision": packet["decision"], "historical_assessment": packet["historical_assessment"], **result}, sort_keys=True))
            return 0
        packet = read_strict_json_file(args.packet)
        valid = verify_current(candidate, roots, packet) if args.command == "verify-current" else verify_historical(candidate, roots, packet)
        print(json.dumps({"valid": bool(valid), "mode": packet.get("mode")}, sort_keys=True))
        return 0 if valid else 2
    except OfferError as exc:
        print(json.dumps({"error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
