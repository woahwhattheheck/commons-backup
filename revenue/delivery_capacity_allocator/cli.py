from __future__ import annotations

import argparse
import sys
from typing import Optional

from .engine import CapacityError, canonical_json, compile_bytes, read_regular_file, verify_current_bytes, write_exclusive


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="delivery-capacity-allocator")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("compile", "verify"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--policy", required=True)
        cmd.add_argument("--demands", required=True)
        cmd.add_argument("--reservations", required=True)
        cmd.add_argument("--policy-sha", required=True, help="integrity pin only; not operational authority")
        cmd.add_argument("--demand-sha", required=True, help="integrity pin only; not operational authority")
        cmd.add_argument("--reservations-sha", required=True, help="integrity pin only; not operational authority")
        if name == "compile":
            cmd.add_argument("--out", required=True)
        else:
            cmd.add_argument("--receipt", required=True)
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = _parser().parse_args(argv)
    try:
        policy = read_regular_file(args.policy)
        demands = read_regular_file(args.demands)
        reservations = read_regular_file(args.reservations)
        common = dict(
            expected_policy_sha256=args.policy_sha,
            expected_demand_sha256=args.demand_sha,
            expected_reservations_sha256=args.reservations_sha,
        )
        if args.command == "compile":
            receipt = compile_bytes(policy, demands, reservations, **common)
            write_exclusive(args.out, canonical_json(receipt))
            print(receipt["current_state"])
            return 0 if receipt["current_state"] == "CURRENT" else 3
        receipt = read_regular_file(args.receipt)
        ok = verify_current_bytes(policy, demands, reservations, receipt, **common)
        print("VERIFIED_CURRENT" if ok else "NOT_CURRENT_OR_INVALID")
        return 0 if ok else 3
    except CapacityError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
