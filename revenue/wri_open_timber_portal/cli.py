from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .engine import ContractError, compile_proposal, load_json_strict, render_markdown, verify_report


def _load(path: str) -> dict:
    return load_json_strict(Path(path).read_bytes(), path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="WRI Open Timber Portal source-bound proposal carrier")
    sub = parser.add_subparsers(dest="command", required=True)

    compile_cmd = sub.add_parser("compile")
    compile_cmd.add_argument("packet")
    compile_cmd.add_argument("--markdown", action="store_true")

    verify_cmd = sub.add_parser("verify")
    verify_cmd.add_argument("packet")
    verify_cmd.add_argument("report")

    args = parser.parse_args(argv)
    try:
        if args.command == "compile":
            report = compile_proposal(_load(args.packet))
            if args.markdown:
                sys.stdout.write(render_markdown(report))
            else:
                print(json.dumps(report, sort_keys=True, separators=(",", ":")))
            return 2 if report["submission_readiness"].startswith("HOLD") else 0

        verification = verify_report(_load(args.packet), _load(args.report))
        print(json.dumps(verification, sort_keys=True, separators=(",", ":")))
        return 0 if verification["verdict"].startswith("CURRENT_") else 2
    except (OSError, ContractError) as exc:
        sys.stderr.write(f"HOLD: {exc}\n")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
