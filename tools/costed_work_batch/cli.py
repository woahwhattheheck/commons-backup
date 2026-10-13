"""Read-only scenario/replay CLI. Results go to stdout; no output paths are written."""
from __future__ import annotations
import argparse
import os
import stat
import sys
from typing import Any
from .planner import InputError, MAX_DOCUMENT_BYTES, canonical_json, parse_json, plan, render_text, verify


def read_document(path: str) -> Any:
    if path == "-":
        raw = sys.stdin.buffer.read(MAX_DOCUMENT_BYTES + 1)
    else:
        flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_DOCUMENT_BYTES:
                raise InputError("input must be a bounded regular file")
            chunks, length = [], 0
            while length <= MAX_DOCUMENT_BYTES:
                chunk = os.read(fd, min(65_536, MAX_DOCUMENT_BYTES + 1 - length))
                if not chunk:
                    break
                chunks.append(chunk)
                length += len(chunk)
            after = os.fstat(fd)
            if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns,
                    before.st_ctime_ns) != (after.st_dev, after.st_ino, after.st_size,
                    after.st_mtime_ns, after.st_ctime_ns):
                raise InputError("input changed during read")
            raw = b"".join(chunks)
        finally:
            os.close(fd)
    if len(raw) > MAX_DOCUMENT_BYTES:
        raise InputError("input exceeds byte limit")
    try:
        return parse_json(raw.decode("utf-8"))
    except UnicodeError as exc:
        raise InputError("input must be UTF-8") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Advisory costed work-batch calculator; never sends or claims work")
    sub = parser.add_subparsers(dest="command", required=True)
    calculate = sub.add_parser("plan", help="calculate a bounded scenario batch")
    calculate.add_argument("scenario", help="UTF-8 JSON file or - for stdin")
    calculate.add_argument("--format", choices=("json", "text"), default="json")
    replay = sub.add_parser("verify", help="deterministically replay; no source authentication")
    replay.add_argument("scenario")
    replay.add_argument("report")
    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            report = plan(read_document(args.scenario))
            text = render_text(report) if args.format == "text" else canonical_json(report)
        else:
            if args.scenario == args.report == "-":
                raise InputError("scenario and report cannot both consume stdin")
            text = canonical_json(verify(read_document(args.scenario), read_document(args.report)))
        sys.stdout.write(text)
        return 0
    except (InputError, OSError) as exc:
        print(f"costed-work-batch: {exc}", file=sys.stderr)
        return 2
