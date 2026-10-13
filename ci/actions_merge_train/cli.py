#!/usr/bin/env python3
"""Bounded create-exclusive CLI for the Actions merge-train advisory compiler."""
from __future__ import annotations

import argparse
import os
import stat
import sys
from pathlib import Path
from typing import Any, Sequence

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ci.actions_merge_train import core

MAX_CAPTURE_BYTES = 32 << 20
MAX_RECEIPT_BYTES = 32 << 20


def read_regular(path: str, *, max_bytes: int, label: str) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise core.EvidenceError(f"{label}: cannot open regular input: {exc.strerror}") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise core.EvidenceError(f"{label}: input must be a regular file")
        if before.st_size > max_bytes:
            raise core.EvidenceError(f"{label}: input exceeds {max_bytes} byte limit")
        chunks = []
        remaining = max_bytes + 1
        while remaining:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        after = os.fstat(fd)
        first = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
        second = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
        if len(data) > max_bytes:
            raise core.EvidenceError(f"{label}: input exceeds {max_bytes} byte limit")
        if first != second or len(data) != before.st_size:
            raise core.EvidenceError(f"{label}: input generation changed while reading")
        return data
    finally:
        os.close(fd)


def write_exclusive(path: str, data: bytes, *, label: str) -> None:
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_BINARY", 0)
    )
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as exc:
        raise core.EvidenceError(f"{label}: create-exclusive open failed: {exc.strerror}") from exc
    try:
        view = memoryview(data)
        offset = 0
        while offset < len(view):
            written = os.write(fd, view[offset:])
            if written <= 0:
                raise core.EvidenceError(f"{label}: short write made no progress")
            offset += written
        os.fsync(fd)
    finally:
        os.close(fd)


def read_captures(paths: Sequence[str]) -> list[Any]:
    if not paths or len(paths) > core.MAX_CAPTURES:
        raise core.EvidenceError(f"expected 1..{core.MAX_CAPTURES} --capture inputs")
    return [
        core.loads_strict(
            read_regular(path, max_bytes=MAX_CAPTURE_BYTES, label=f"capture {idx}"),
            label=f"capture {idx}",
        )
        for idx, path in enumerate(paths, 1)
    ]


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    subs = root.add_subparsers(dest="command", required=True)
    compile_parser = subs.add_parser("compile")
    compile_parser.add_argument("--capture", action="append", required=True)
    compile_parser.add_argument("--out", required=True)
    compile_parser.add_argument("--markdown")
    verify_parser = subs.add_parser("verify")
    verify_parser.add_argument("--receipt", required=True)
    verify_parser.add_argument("--capture", action="append", required=True)
    verify_parser.add_argument("--out", required=True)
    return root


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        captures = read_captures(args.capture)
        if args.command == "compile":
            receipt = core.compile_train(captures)
            write_exclusive(args.out, core.canonical_bytes(receipt), label="output")
            if args.markdown:
                write_exclusive(args.markdown, core.render_markdown(receipt).encode("utf-8"), label="markdown")
            return 0
        supplied = core.loads_strict(
            read_regular(args.receipt, max_bytes=MAX_RECEIPT_BYTES, label="receipt"),
            label="receipt",
        )
        result = core.verify_receipt(supplied, captures)
        write_exclusive(args.out, core.canonical_bytes(result), label="output")
        return 0 if result["valid"] else 1
    except core.EvidenceError as exc:
        print(f"actions-merge-train: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
