#!/usr/bin/env python3
"""Bounded create-exclusive CLI for the execution-truth classifier."""
from __future__ import annotations

import argparse
import os
import stat
import sys
from pathlib import Path
from typing import Any, Iterable, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core

MAX_RUN_BYTES = 1 << 20
MAX_JOBS_BYTES = 16 << 20
MAX_RECEIPT_BYTES = 16 << 20


def read_regular(path: str, *, max_bytes: int, label: str) -> bytes:
    flags = os.O_RDONLY | (getattr(os, "O_NOFOLLOW", 0))
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
        chunks, remaining = [], max_bytes + 1
        while remaining:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk: break
            chunks.append(chunk); remaining -= len(chunk)
        data = b"".join(chunks)
        if len(data) > max_bytes:
            raise core.EvidenceError(f"{label}: input exceeds {max_bytes} byte limit")
        after = os.fstat(fd)
        first = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
        second = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
        if first != second or len(data) != before.st_size:
            raise core.EvidenceError(f"{label}: input generation changed while reading")
        return data
    finally:
        os.close(fd)


def write_exclusive(path: str, value: Any) -> None:
    data = core.canonical_bytes(value)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as exc:
        raise core.EvidenceError(f"output: create-exclusive open failed: {exc.strerror}") from exc
    try:
        view, offset = memoryview(data), 0
        while offset < len(view):
            written = os.write(fd, view[offset:])
            if written <= 0: raise core.EvidenceError("output: short write made no progress")
            offset += written
        os.fsync(fd)
    finally:
        os.close(fd)


def read_cases(case_args: Iterable[Sequence[str]]) -> list[tuple[Any, Any]]:
    args = list(case_args)
    if not args or len(args) > core.MAX_CASES:
        raise core.EvidenceError(f"expected 1..{core.MAX_CASES} --case pairs")
    cases = []
    for index, pair in enumerate(args, 1):
        if len(pair) != 2: raise core.EvidenceError("each --case requires RUN_JSON JOBS_JSON")
        run_path, jobs_path = pair
        run = core.loads_strict(read_regular(run_path, max_bytes=MAX_RUN_BYTES, label=f"case {index} run"), label=f"case {index} run")
        jobs = core.loads_strict(read_regular(jobs_path, max_bytes=MAX_JOBS_BYTES, label=f"case {index} jobs"), label=f"case {index} jobs")
        cases.append((run, jobs))
    return cases


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    subs = root.add_subparsers(dest="command", required=True)
    compile_cmd = subs.add_parser("compile")
    compile_cmd.add_argument("--case", action="append", nargs=2, metavar=("RUN_JSON", "JOBS_JSON"), required=True)
    compile_cmd.add_argument("--out", required=True)
    verify_cmd = subs.add_parser("verify")
    verify_cmd.add_argument("--receipt", required=True)
    verify_cmd.add_argument("--case", action="append", nargs=2, metavar=("RUN_JSON", "JOBS_JSON"), required=True)
    verify_cmd.add_argument("--out", required=True)
    return root


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        cases = read_cases(args.case)
        if args.command == "compile":
            write_exclusive(args.out, core.compile_receipt(cases)); return 0
        supplied = core.loads_strict(read_regular(args.receipt, max_bytes=MAX_RECEIPT_BYTES, label="receipt"), label="receipt")
        result = core.verify_receipt(supplied, cases)
        write_exclusive(args.out, result)
        return 0 if result["valid"] else 1
    except core.EvidenceError as exc:
        print(f"actions-execution-truth: {exc}", file=sys.stderr); return 2


if __name__ == "__main__":
    raise SystemExit(main())
