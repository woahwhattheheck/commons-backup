"""python -m cashiering_lab compile INPUT --out NEW_DIRECTORY | verify DIRECTORY"""
from __future__ import annotations
import argparse
import json
import sys
from .artifacts import bundle, read_input, verify, write_bundle
from .core import InputError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline cashiering acceptance review; never posts or moves money")
    sub = parser.add_subparsers(dest="command", required=True)
    compile_parser = sub.add_parser("compile", help="write a new deterministic review bundle")
    compile_parser.add_argument("input")
    compile_parser.add_argument("--out", required=True)
    verify_parser = sub.add_parser("verify", help="recompute and compare every artifact")
    verify_parser.add_argument("directory")
    args = parser.parse_args(argv)
    try:
        if args.command == "verify":
            result = verify(args.directory)
            print(json.dumps(result, sort_keys=True))
            return 0
        artifacts = bundle(read_input(args.input))
        write_bundle(args.out, artifacts)
        report = json.loads(artifacts["report.json"])
        print(json.dumps({"status": report["status"], "findings_count": report["findings_count"],
                          "input_sha256": report["input_sha256"], "output": args.out}, sort_keys=True))
        return 1 if report["findings_count"] else 0
    except (InputError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
