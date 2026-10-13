from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .engine import EvidenceError, parse_json_bytes, read_regular_file, render_bundle, retained_root, verify_bundle, write_bundle_exclusive


def _load(path: str):
    return parse_json_bytes(read_regular_file(path))


def cmd_root(args: argparse.Namespace) -> int:
    print(retained_root(_load(args.input)))
    return 0


def cmd_compile(args: argparse.Namespace) -> int:
    doc = _load(args.input)
    bundle = render_bundle(doc, args.expected_root)
    write_bundle_exclusive(args.output, bundle)
    packet = json.loads(bundle.packet_json)
    print(json.dumps({"observedState": packet["observedState"], "nextExperiment": packet["nextExperiment"]["code"], "output": str(Path(args.output))}, sort_keys=True))
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    doc = _load(args.input)
    out = Path(args.output)
    ok = verify_bundle(doc, args.expected_root,
        packet_json=read_regular_file(out / "packet.json"),
        summary_md=read_regular_file(out / "summary.md"),
        events_csv=read_regular_file(out / "events.csv"),
        receipt_txt=read_regular_file(out / "receipt.txt"))
    print(json.dumps({"verified": ok}, sort_keys=True))
    return 0 if ok else 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="commerce-conversion-loop", description="Offline provenance-bound revenue conversion evidence compiler.")
    sp = p.add_subparsers(dest="command", required=True)
    x = sp.add_parser("root", help="compute retained root")
    x.add_argument("input")
    x.set_defaults(func=cmd_root)
    x = sp.add_parser("compile", help="compile owner-review artifacts")
    x.add_argument("input")
    x.add_argument("--expected-root", required=True)
    x.add_argument("--output", required=True)
    x.set_defaults(func=cmd_compile)
    x = sp.add_parser("verify", help="semantic exact-replay verification")
    x.add_argument("input")
    x.add_argument("--expected-root", required=True)
    x.add_argument("--output", required=True)
    x.set_defaults(func=cmd_verify)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except EvidenceError as exc:
        print(f"HOLD: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
