from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import pilot


def _distinct(paths: list[Path]) -> None:
    normalized = [str(p.absolute()) for p in paths]
    if len(set(normalized)) != len(normalized):
        raise pilot.PilotError("outputs_must_be_distinct")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fixed Evidence Freshness Diagnostic")
    sub = parser.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("compile")
    c.add_argument("request", type=Path)
    c.add_argument("engine_packet", type=Path)
    c.add_argument("diagnostic", type=Path)
    c.add_argument("buyer_report", type=Path)

    v = sub.add_parser("verify")
    v.add_argument("request", type=Path)
    v.add_argument("engine_packet", type=Path)
    v.add_argument("diagnostic", type=Path)
    v.add_argument("buyer_report", type=Path)

    args = parser.parse_args(argv)
    try:
        if args.cmd == "compile":
            _distinct([args.engine_packet, args.diagnostic, args.buyer_report])
            request = pilot.load_json(args.request)
            packet, diagnostic, report = pilot.compile_diagnostic(request)
            pilot.write_exclusive(args.engine_packet, pilot.canonical(packet) + b"\n")
            pilot.write_exclusive(args.diagnostic, pilot.canonical(diagnostic) + b"\n")
            pilot.write_exclusive(args.buyer_report, report.encode("utf-8"))
            print("DIAGNOSTIC_READY")
        else:
            request = pilot.load_json(args.request)
            packet = pilot.load_json(args.engine_packet)
            diagnostic = pilot.load_json(args.diagnostic)
            report = pilot.load_markdown(args.buyer_report)
            pilot.verify_diagnostic(request, packet, diagnostic, report)
            print("VERIFIED")
        return 0
    except pilot.PilotError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
