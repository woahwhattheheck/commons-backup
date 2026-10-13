# SPDX-License-Identifier: MPL-2.0
"""CLI for deterministic CAS benchmark evidence validation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .core import BenchmarkInputError, evaluate_benchmark, verify_snapshot
from .fixture import synthetic_evidence


def _read(path: str):
    if path == "-":
        return json.load(sys.stdin)
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cas-actuarial-benchmark-evidence")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="validate evidence and emit a safe snapshot")
    validate.add_argument("evidence", help="JSON path, or - for stdin")
    validate.add_argument("--output", help="optional snapshot JSON path")

    verify = sub.add_parser("verify", help="verify a content-addressed snapshot")
    verify.add_argument("snapshot", help="snapshot JSON path, or - for stdin")

    fixture = sub.add_parser("fixture", help="run the repository synthetic acceptance fixture")
    fixture.add_argument("--output", help="optional snapshot JSON path")

    args = parser.parse_args(argv)
    try:
        if args.command == "verify":
            snapshot = _read(args.snapshot)
            ok = verify_snapshot(snapshot)
            print(json.dumps({"snapshot_valid": ok}, sort_keys=True))
            return 0 if ok else 3

        evidence = synthetic_evidence() if args.command == "fixture" else _read(args.evidence)
        snapshot = evaluate_benchmark(evidence)
        text = json.dumps(snapshot, indent=2, sort_keys=True, ensure_ascii=False)
        output = getattr(args, "output", None)
        if output:
            Path(output).write_text(text + "\n", encoding="utf-8")
        print(
            json.dumps(
                {
                    "status": snapshot["status"],
                    "snapshot_sha256": snapshot["snapshot_sha256"],
                    "task_count": snapshot["signals"]["task_count"],
                    "model_count": snapshot["signals"]["model_count"],
                    "run_count": snapshot["signals"]["run_count"],
                },
                sort_keys=True,
            )
        )
        return 0
    except (OSError, json.JSONDecodeError, BenchmarkInputError) as exc:
        print(json.dumps({"status": "HOLD", "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
