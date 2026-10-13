from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

from .core import attach_model_advisory, compile_plan, compile_plan_historical, verify_receipt
from .gloo import GlooClient, GlooError, simulated_advisory
from .readiness import compile_readiness


def _load(path: str):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _dump(value, path: str | None):
    text = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if path:
        target = Path(path)
        if target.exists():
            raise FileExistsError(f"refusing to overwrite existing output: {target}")
        target.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="neighborsignal")
    sub = parser.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan", help="compile a current plan using trusted process time")
    plan.add_argument("request")
    plan.add_argument("catalog")
    plan.add_argument("--output")
    plan.add_argument("--advisory", choices=["none", "simulate", "gloo"], default="none")

    historical = sub.add_parser("historical", help="explicit replay mode; never current authority")
    historical.add_argument("request")
    historical.add_argument("catalog")
    historical.add_argument("--at", required=True)
    historical.add_argument("--output")

    verify = sub.add_parser("verify")
    verify.add_argument("package")

    ready = sub.add_parser("readiness")
    ready.add_argument("evidence")

    sub.add_parser("gloo-status")

    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            package = compile_plan(_load(args.request), _load(args.catalog))
            if args.advisory == "simulate":
                package = attach_model_advisory(package, simulated_advisory(package["plan"]))
            elif args.advisory == "gloo":
                package = attach_model_advisory(package, GlooClient().advisory(package["plan"]))
            _dump(package, args.output)
            return 0
        if args.command == "historical":
            at = datetime.fromisoformat(args.at.replace("Z", "+00:00"))
            _dump(compile_plan_historical(_load(args.request), _load(args.catalog), at), args.output)
            return 0
        if args.command == "verify":
            result = verify_receipt(_load(args.package))
            _dump(result, None)
            return 0 if result.get("ok") else 2
        if args.command == "readiness":
            _dump(compile_readiness(_load(args.evidence)), None)
            return 0
        if args.command == "gloo-status":
            client = GlooClient()
            _dump({"configured": client.configured, "live_call_attempted": False}, None)
            return 0
    except (ValueError, OSError, GlooError) as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
