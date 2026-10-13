"""CLI for current sales-meeting readiness compilation and offline verification."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import stat
import sys

from .meeting_readiness import (
    DEFAULT_POLICY,
    MeetingReadinessError,
    canonical_json_bytes,
    compile_meeting_readiness,
    load_json_strict,
    render_markdown,
    verify_receipt,
)

MAX_INPUT_BYTES = 1_000_000


def _read_regular(path: Path) -> bytes:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise MeetingReadinessError(f"input is not a regular file: {path}")
        if st.st_size > MAX_INPUT_BYTES:
            raise MeetingReadinessError(f"input exceeds {MAX_INPUT_BYTES} bytes: {path}")
        data = b""
        while len(data) <= MAX_INPUT_BYTES:
            chunk = os.read(fd, min(65536, MAX_INPUT_BYTES + 1 - len(data)))
            if not chunk:
                break
            data += chunk
        if len(data) > MAX_INPUT_BYTES:
            raise MeetingReadinessError(f"input exceeds {MAX_INPUT_BYTES} bytes: {path}")
        return data
    finally:
        os.close(fd)


def _write_exclusive(path: Path, data: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise MeetingReadinessError(f"output is not a regular file: {path}")
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)


def _load(path: Path):
    return load_json_strict(_read_regular(path))


def _policy(path: Path | None):
    return DEFAULT_POLICY if path is None else _load(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compile or verify sales meeting readiness receipts")
    sub = parser.add_subparsers(dest="command", required=True)

    compile_p = sub.add_parser("compile", help="capture current UTC internally and compile")
    compile_p.add_argument("--input", required=True, type=Path)
    compile_p.add_argument("--policy", type=Path)
    compile_p.add_argument("--json-out", required=True, type=Path)
    compile_p.add_argument("--md-out", required=True, type=Path)

    verify_p = sub.add_parser("verify", help="offline-verify an existing receipt")
    verify_p.add_argument("--input", required=True, type=Path)
    verify_p.add_argument("--receipt", required=True, type=Path)
    verify_p.add_argument("--policy", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        packet = _load(args.input)
        policy = _policy(args.policy)
        if args.command == "compile":
            receipt = compile_meeting_readiness(packet, as_of=datetime.now(timezone.utc), policy=policy)
            _write_exclusive(args.json_out, canonical_json_bytes(receipt) + b"\n")
            _write_exclusive(args.md_out, render_markdown(receipt).encode("utf-8"))
            print(receipt["state"])
            return 0
        receipt = _load(args.receipt)
        verify_receipt(packet, receipt, policy=policy)
        print("VERIFIED")
        return 0
    except (MeetingReadinessError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
