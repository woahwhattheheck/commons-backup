from __future__ import annotations

import argparse
import json
import os
import sys

from .contracts import RouteScoutError, _strict_json_load
from .planning import preview
from .provider import CalleApi, run_live
from .results import reconcile

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RouteScout: approval-gated CALL-E business routing")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("preview", help="offline; prints exact task, approval token, no call")
    p.add_argument("inquiry")
    p = sub.add_parser("run", help="places one CALL-E call after exact-byte confirmation")
    p.add_argument("inquiry")
    p.add_argument("--confirm-call", required=True)
    p = sub.add_parser("resume", help="GET/poll an existing call id only; never creates a call")
    p.add_argument("inquiry")
    p.add_argument("call_id")
    p = sub.add_parser("reconcile", help="offline reconcile retained terminal CALL-E JSON")
    p.add_argument("inquiry")
    p.add_argument("terminal_result")
    args = parser.parse_args(argv)
    try:
        inquiry = _strict_json_load(args.inquiry)
        if args.command == "preview":
            out = preview(inquiry)
        elif args.command == "run":
            call_id, receipt = run_live(inquiry, args.confirm_call)
            out = {"call_id": call_id, "receipt": receipt}
        elif args.command == "resume":
            api = CalleApi(os.environ.get("CALLE_API_KEY", ""))
            terminal = api.wait(args.call_id)
            out = {"call_id": args.call_id, "receipt": reconcile(inquiry, terminal, expected_call_id=args.call_id)}
        else:
            out = reconcile(inquiry, _strict_json_load(args.terminal_result))
    except (OSError, RouteScoutError) as exc:
        print(json.dumps({"state": "HOLD", "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
