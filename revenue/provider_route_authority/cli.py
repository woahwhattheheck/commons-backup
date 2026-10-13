from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
from .core import AuthorityError, canonical_json, compile_authority, strict_json_loads, verify_authority

def _load(path: str):
    return strict_json_loads(Path(path).read_text(encoding="utf-8"))

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile or verify provider-route outreach authority.")
    sub = parser.add_subparsers(dest="command", required=True)
    compile_p = sub.add_parser("compile")
    compile_p.add_argument("input")
    verify_p = sub.add_parser("verify")
    verify_p.add_argument("input")
    verify_p.add_argument("receipt")
    args = parser.parse_args(argv)
    try:
        if args.command == "compile":
            sys.stdout.write(canonical_json(compile_authority(_load(args.input))))
            return 0
        verify_authority(_load(args.input), _load(args.receipt))
        sys.stdout.write(json.dumps({"verified": True}, sort_keys=True) + "\n")
        return 0
    except (AuthorityError, OSError) as exc:
        sys.stderr.write(f"provider-route-authority: {exc}\n")
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
