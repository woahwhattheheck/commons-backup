from __future__ import annotations
import argparse
import sys
from .engine import ContractError, compile_receipt, read_json_regular, verify_receipt, write_json_exclusive


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Offline regulated-handoff custody evidence gate")
    sub = parser.add_subparsers(dest="command", required=True)
    c = sub.add_parser("compile", help="compile an event envelope into a canonical receipt")
    c.add_argument("input")
    c.add_argument("output")
    v = sub.add_parser("verify", help="verify receipt digest and recompute embedded evidence")
    v.add_argument("receipt")
    args = parser.parse_args(argv)
    try:
        if args.command == "compile":
            envelope = read_json_regular(args.input)
            if not isinstance(envelope, dict) or set(envelope) != {"policy", "events"}:
                raise ContractError("compile envelope must contain exactly policy and events")
            if not isinstance(envelope["events"], list):
                raise ContractError("events must be a list")
            receipt = compile_receipt(envelope["events"], envelope["policy"])
            write_json_exclusive(args.output, receipt)
            print(f"{receipt['body']['state']} {receipt['receipt_sha256']}")
            return 0 if receipt["body"]["state"] == "PASS_EVIDENCE" else 3
        receipt = read_json_regular(args.receipt)
        verified = verify_receipt(receipt)
        print(f"VERIFIED {verified['body']['state']} {verified['receipt_sha256']}")
        return 0
    except (ContractError, OSError, UnicodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
