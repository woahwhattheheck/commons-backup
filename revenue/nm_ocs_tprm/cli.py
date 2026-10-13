"""Offline CLI for deterministic TPRM assessment and verification."""

from __future__ import annotations

import argparse
import json
import math
import os
import stat
from pathlib import Path
import sys
from typing import Any

if __package__:
    from .qualification import compile_qualification, verify_receipt
    from .tprm import (
        compile_assessment,
        compile_portfolio,
        verify_assessment_packet,
        verify_portfolio_packet,
    )
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from revenue.nm_ocs_tprm.qualification import compile_qualification, verify_receipt
    from revenue.nm_ocs_tprm.tprm import (
        compile_assessment,
        compile_portfolio,
        verify_assessment_packet,
        verify_portfolio_packet,
    )


# Source documents remain bounded to the original 4 MB limit. Compiled packets
# contain normalized sources, derived results and indented presentation, so a
# separate packet budget is needed for the compile -> verify round trip.
MAX_INPUT_BYTES = 4_000_000
MAX_PACKET_BYTES = 32_000_000
MAX_JSON_DEPTH = 64


def _generation(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _check_depth(raw: bytes) -> None:
    """Bound container nesting before the JSON parser allocates the tree."""
    depth = 0
    quoted = False
    escaped = False
    for char in raw:
        if quoted:
            if escaped:
                escaped = False
            elif char == 92:
                escaped = True
            elif char == 34:
                quoted = False
        elif char == 34:
            quoted = True
        elif char in (91, 123):
            depth += 1
            if depth > MAX_JSON_DEPTH:
                raise ValueError("JSON nesting exceeds depth limit")
        elif char in (93, 125):
            depth -= 1
    # JSON syntax and string validity are still checked by json.loads.


def _strict_load(path: Path, *, max_bytes: int = MAX_INPUT_BYTES) -> Any:
    if type(max_bytes) is not int or max_bytes < 1:
        raise ValueError("max_bytes must be a positive integer")
    try:
        before = path.lstat()
    except OSError as exc:
        raise ValueError("input must be an ordinary non-symlink file") from exc
    if not stat.S_ISREG(before.st_mode):
        raise ValueError("input must be an ordinary non-symlink file")
    if before.st_size > max_bytes:
        raise ValueError("input too large")

    # O_NONBLOCK prevents a raced-in FIFO from hanging the reader. Platforms
    # without O_NOFOLLOW still receive lstat/fstat and final-entry checks.
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ValueError("input could not be opened as a stable ordinary file") from exc
    try:
        with os.fdopen(fd, "rb") as stream:
            fd = -1  # The stream owns the descriptor from this point onward.
            opened = os.fstat(stream.fileno())
            if not stat.S_ISREG(opened.st_mode) or _generation(opened) != _generation(before):
                raise ValueError("input changed before reading")
            raw = stream.read(max_bytes + 1)
            after = os.fstat(stream.fileno())
    finally:
        if fd != -1:
            os.close(fd)
    if len(raw) > max_bytes:
        raise ValueError("input too large")
    try:
        current = path.lstat()
    except OSError as exc:
        raise ValueError("input changed while reading") from exc
    if (
        not stat.S_ISREG(current.st_mode)
        or _generation(after) != _generation(opened)
        or _generation(current) != _generation(opened)
    ):
        raise ValueError("input changed while reading")

    _check_depth(raw)

    def pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in values:
            if key in out:
                raise ValueError(f"duplicate JSON key: {key[:100]}")
            out[key] = value
        return out

    def bad_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON constant: {value}")

    def finite_float(value: str) -> float:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("non-finite JSON number")
        return number

    try:
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_constant=bad_constant,
            parse_float=finite_float,
        )
    except RecursionError as exc:
        raise ValueError("JSON nesting exceeds the parser limit") from exc


def _write(path: Path, value: Any) -> None:
    encoded = (
        json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    ).encode("utf-8")
    if len(encoded) > MAX_PACKET_BYTES:
        raise ValueError("compiled packet exceeds verification size limit")
    try:
        stream = path.open("xb")
    except FileExistsError as exc:
        raise ValueError("refusing to overwrite output") from exc
    # Exclusive creation, not a check followed by a truncating open, protects
    # another worker's existing result. An I/O failure after creation can leave
    # a partial file; it is deliberately not unlinked by a racy cleanup path.
    with stream:
        stream.write(encoded)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    for name in ("assessment", "portfolio", "qualification"):
        p = sub.add_parser(name)
        p.add_argument("input")
        p.add_argument("output")

    for name in ("verify-assessment", "verify-portfolio", "verify-qualification"):
        p = sub.add_parser(name)
        p.add_argument("input")

    args = parser.parse_args(argv)
    limit = MAX_PACKET_BYTES if args.cmd.startswith("verify-") else MAX_INPUT_BYTES
    data = _strict_load(Path(args.input), max_bytes=limit)

    if args.cmd == "assessment":
        _write(Path(args.output), compile_assessment(data))
    elif args.cmd == "portfolio":
        _write(Path(args.output), compile_portfolio(data))
    elif args.cmd == "qualification":
        _write(Path(args.output), compile_qualification(data))
    elif args.cmd == "verify-assessment":
        return 0 if verify_assessment_packet(data) else 2
    elif args.cmd == "verify-portfolio":
        return 0 if verify_portfolio_packet(data) else 2
    elif args.cmd == "verify-qualification":
        return 0 if verify_receipt(data) else 2
    return 0


def _entrypoint(argv: list[str] | None = None) -> int:
    """Shell boundary: invalid input is exit 2, not an unhandled traceback.

    ``main`` retains its programmatic exception behavior for existing callers.
    """
    try:
        return main(argv)
    except (OSError, ValueError, TypeError, RecursionError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(_entrypoint())
