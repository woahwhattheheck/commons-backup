"""CLI for portfolio execution handoff manifests."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from .handoff import compile_handoff, render_markdown, verify_receipt

def _load(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    c = sub.add_parser("compile")
    c.add_argument("input")
    c.add_argument("--trusted-as-of", required=True)
    c.add_argument("--receipt", required=True)
    c.add_argument("--markdown")
    v = sub.add_parser("verify")
    v.add_argument("receipt")
    v.add_argument("--trusted-as-of")
    args = parser.parse_args(argv)
    if args.command == "compile":
        receipt = compile_handoff(_load(args.input), trusted_as_of=args.trusted_as_of)
        Path(args.receipt).write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        if args.markdown:
            Path(args.markdown).write_text(render_markdown(receipt), encoding="utf-8")
        return 0 if receipt["authority"]["strongestState"] == "READY_FOR_OWNER_HANDOFF_REVIEW" else 3
    verify_receipt(_load(args.receipt), trusted_as_of=args.trusted_as_of)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
