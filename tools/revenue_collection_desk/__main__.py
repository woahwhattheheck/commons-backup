from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .core import ContractError, compile_json, verify_json
from .portal_registration import audit_json

def _read(path: str) -> bytes:
    return Path(path).read_bytes()

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compile revenue evidence or reconcile exact provider registrations."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    p_compile = sub.add_parser("compile")
    p_compile.add_argument("ledger")
    p_compile.add_argument("--pretty", action="store_true")
    p_queue = sub.add_parser("queue")
    p_queue.add_argument("ledger")
    p_verify = sub.add_parser("verify")
    p_verify.add_argument("ledger")
    p_verify.add_argument("report")
    p_portal = sub.add_parser("portal-audit", help="Read-only GitHub/IssueHunt/BountyHub claim reconciliation")
    p_portal.add_argument("evidence", help="First-party portal snapshots plus exact PR list, JSON v1")
    p_portal.add_argument("--pretty", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "compile":
            report = compile_json(_read(args.ledger))
            if args.pretty:
                print(json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False))
            else:
                print(json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
            return 0
        if args.command == "queue":
            report = compile_json(_read(args.ledger))
            sys.stdout.write(report["collection_queue_markdown"])
            return 0
        if args.command == "portal-audit":
            report = audit_json(_read(args.evidence))
            print(json.dumps(report, sort_keys=True, indent=2 if args.pretty else None,
                             separators=None if args.pretty else (",", ":"), ensure_ascii=False))
            return 1 if report["actionable_registration_gaps"] else 0
        verified = verify_json(_read(args.ledger), _read(args.report))
        print(json.dumps({"verified": verified}, sort_keys=True))
        return 0 if verified else 1
    except (ContractError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": type(exc).__name__, "message": str(exc)}, sort_keys=True))
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
