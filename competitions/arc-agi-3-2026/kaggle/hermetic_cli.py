"""Command-line entrypoint for ARC3 SAGE hermetic bundle evidence."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import math
from pathlib import Path
import sys
from typing import Sequence

from .hermetic import (
    ExecutionPolicy,
    HermeticError,
    dependency_closure,
    receipt_json,
    require_closed_dependencies,
    run_hermetic,
    verify_receipt,
)


def _positive_float(text: str) -> float:
    try:
        value = float(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected a number") from exc
    if not math.isfinite(value) or value <= 0:
        raise argparse.ArgumentTypeError("expected a finite positive number")
    return value


def _fraction(text: str) -> float:
    value = _positive_float(text)
    if value >= 1:
        raise argparse.ArgumentTypeError("expected a fraction in (0,1)")
    return value


def _positive_int(text: str) -> int:
    try:
        value = int(text, 10)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected an integer") from exc
    if value <= 0:
        raise argparse.ArgumentTypeError("expected a positive integer")
    return value


def _read_json(path: Path, *, max_bytes: int = 2 << 20) -> dict[str, object]:
    try:
        st = path.lstat()
    except OSError as exc:
        raise HermeticError("cannot stat receipt") from exc
    if path.is_symlink() or not path.is_file():
        raise HermeticError("receipt must be a regular non-symlink file")
    if st.st_size > max_bytes:
        raise HermeticError("receipt exceeds size limit")
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HermeticError("receipt is not valid UTF-8 JSON") from exc
    if not isinstance(obj, dict):
        raise HermeticError("receipt JSON root must be an object")
    return obj


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m kaggle.hermetic_cli",
        description="Verify and execute an ARC3 SAGE offline bundle without external authority.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    closure = sub.add_parser("closure", help="verify manifest bytes and dependency closure")
    closure.add_argument("bundle", type=Path)

    run = sub.add_parser("run", help="run a manifest-bound entrypoint in the hermetic interpreter")
    run.add_argument("bundle", type=Path)
    run.add_argument("--entrypoint", default="benchmark.py")
    run.add_argument("--timeout", type=_positive_float, default=300.0)
    run.add_argument("--competition-runtime", type=_positive_float, default=32_400.0)
    run.add_argument("--margin", type=_fraction, default=0.80)
    run.add_argument("--memory-mib", type=_positive_float, default=None)
    run.add_argument("--max-output-bytes", type=_positive_int, default=1 << 20)

    verify = sub.add_parser("verify", help="verify a previously written execution receipt")
    verify.add_argument("receipt", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "closure":
            result = dependency_closure(args.bundle)
            require_closed_dependencies(result)
            print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
            return 0
        if args.command == "run":
            policy = ExecutionPolicy(
                timeout_seconds=args.timeout,
                competition_runtime_seconds=args.competition_runtime,
                runtime_margin_fraction=args.margin,
                memory_limit_mib=args.memory_mib,
                max_output_bytes=args.max_output_bytes,
            )
            receipt = run_hermetic(args.bundle, entrypoint=args.entrypoint, policy=policy)
            print(receipt_json(receipt))
            return 0 if receipt.state == "HERMETIC_RUNTIME_CONFORMANT" else 2
        if args.command == "verify":
            receipt = _read_json(args.receipt)
            verify_receipt(receipt)
            print(json.dumps({"state": "VERIFIED", "execution_identity_sha256": receipt["execution_identity_sha256"]},
                             sort_keys=True, separators=(",", ":")))
            return 0
        raise HermeticError("unsupported command")
    except HermeticError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
