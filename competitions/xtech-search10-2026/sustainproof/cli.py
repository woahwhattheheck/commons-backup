"""Command-line entry point for the SustainProof xTech carrier."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from qualification import ContractError as QualificationError, compile_packet, read_regular_json
from sustainproof import ContractError as HandoffError, compile_handoff
from validate_white_paper import DraftError, validate_file

UTC_FMT = "%Y-%m-%dT%H:%M:%SZ"


def _as_of(value: str) -> datetime:
    try:
        parsed = datetime.strptime(value, UTC_FMT).replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected canonical UTC YYYY-MM-DDTHH:MM:SSZ") from exc
    if parsed.strftime(UTC_FMT) != value:
        raise argparse.ArgumentTypeError("expected canonical whole-second UTC")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SustainProof offline xTech readiness/prototype tools")
    sub = parser.add_subparsers(dest="command", required=True)

    handoff = sub.add_parser("handoff", help="compile a local sustainment handoff review packet")
    handoff.add_argument("--input", required=True)
    handoff.add_argument("--historical-as-of", type=_as_of)

    qualify = sub.add_parser("qualify", help="compile owner-review xTech qualification packet")
    qualify.add_argument("--input", required=True)
    qualify.add_argument("--sources", default=str(HERE / "official_sources.json"))
    qualify.add_argument("--historical-as-of", type=_as_of)

    white = sub.add_parser("white-paper-check", help="check the bounded three-section draft")
    white.add_argument("--draft", default=str(HERE / "white_paper.md"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "handoff":
            result = compile_handoff(read_regular_json(args.input), as_of=args.historical_as_of)
        elif args.command == "qualify":
            result = compile_packet(read_regular_json(args.input), read_regular_json(args.sources), as_of=args.historical_as_of)
        else:
            result = {"ok": True, **validate_file(args.draft), "submissionAuthorized": False}
        print(json.dumps(result, sort_keys=True, indent=2))
        return 0
    except (QualificationError, HandoffError, DraftError) as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__, "detail": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
