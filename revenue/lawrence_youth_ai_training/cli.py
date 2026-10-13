from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

from .gate import (
    COLLABORATIVE_READY,
    HOLD,
    NO_BID,
    PRIME_READY,
    QualificationInputError,
    evaluate_current,
    evaluate_historical,
    strict_json_loads,
    verify_current,
)

_MAX_INPUT_BYTES = 1_048_576


def _read_json(path_text: str, name: str) -> Any:
    path = Path(path_text)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise QualificationInputError(f"{name} must be a readable non-symlink file") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise QualificationInputError(f"{name} must be a one-link regular file")
        if before.st_size < 1 or before.st_size > _MAX_INPUT_BYTES:
            raise QualificationInputError(f"{name} size is outside bounds")
        chunks: list[bytes] = []
        remaining = _MAX_INPUT_BYTES + 1
        while remaining:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        after = os.fstat(fd)
        if (
            len(raw) != before.st_size
            or len(raw) > _MAX_INPUT_BYTES
            or (
                before.st_dev,
                before.st_ino,
                before.st_mode,
                before.st_nlink,
                before.st_size,
                before.st_mtime_ns,
                before.st_ctime_ns,
            )
            != (
                after.st_dev,
                after.st_ino,
                after.st_mode,
                after.st_nlink,
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            )
        ):
            raise QualificationInputError(f"{name} changed during read")
        visible = os.lstat(path)
        if (visible.st_dev, visible.st_ino) != (after.st_dev, after.st_ino):
            raise QualificationInputError(f"{name} pathname changed during read")
        return strict_json_loads(raw, name)
    finally:
        os.close(fd)


def _emit(value: Any) -> None:
    sys.stdout.write(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    )


def _decision_exit(decision: str) -> int:
    if decision in {PRIME_READY, COLLABORATIVE_READY}:
        return 0
    if decision == HOLD:
        return 3
    if decision == NO_BID:
        return 4
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="lawrence-youth-ai-qualification",
        description=(
            "Evaluate source-bound internal qualification evidence. "
            "Current commands own process UTC and fixed host semantic authority."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    current = sub.add_parser("evaluate-current")
    current.add_argument("snapshot")
    current.add_argument("--expected-rfp-sha256", required=True)

    verify = sub.add_parser("verify-current")
    verify.add_argument("receipt")
    verify.add_argument("snapshot")
    verify.add_argument("--expected-rfp-sha256", required=True)

    historical = sub.add_parser(
        "evaluate-historical",
        help="Non-authorizing historical integrity replay; never emits current readiness.",
    )
    historical.add_argument("snapshot")
    historical.add_argument("--evaluated-at", required=True)
    historical.add_argument("--expected-rfp-sha256", required=True)

    args = parser.parse_args(argv)
    try:
        if args.command == "evaluate-current":
            result = evaluate_current(
                _read_json(args.snapshot, "snapshot"),
                expected_rfp_sha256=args.expected_rfp_sha256,
            )
            _emit(result)
            return _decision_exit(result["receipt"]["decision"])
        if args.command == "verify-current":
            result = _read_json(args.receipt, "receipt")
            snapshot = _read_json(args.snapshot, "snapshot")
            ok = verify_current(
                result,
                snapshot=snapshot,
                expected_rfp_sha256=args.expected_rfp_sha256,
            )
            _emit({"verified": ok})
            return 0 if ok else 3
        result = evaluate_historical(
            _read_json(args.snapshot, "snapshot"),
            evaluated_at=args.evaluated_at,
            expected_rfp_sha256=args.expected_rfp_sha256,
        )
        _emit(result)
        return _decision_exit(result["receipt"]["decision"])
    except (QualificationInputError, OSError) as exc:
        _emit({"error": str(exc), "verified": False})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
