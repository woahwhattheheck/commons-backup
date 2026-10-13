"""Offline CLI for the Hyperagent transcript pilot proof."""

from __future__ import annotations

import argparse
from pathlib import Path
import os
import stat
import sys

from .adapter import ValidationError, canonical_bytes, load_strict_json, project_fixture

MAX_INPUT_BYTES = 1_000_000


def _read_regular(path: Path) -> bytes:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise ValueError("input must be a regular file")
        if st.st_size > MAX_INPUT_BYTES:
            raise ValueError("input too large")
        data = os.read(fd, MAX_INPUT_BYTES + 1)
        if len(data) > MAX_INPUT_BYTES:
            raise ValueError("input too large")
        return data
    finally:
        os.close(fd)


def _write_exclusive(path: Path, data: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("short write")
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Project synthetic agent events into offline Slack transcript artifacts")
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args(argv)

    try:
        fixture = load_strict_json(_read_regular(args.input))
        result = project_fixture(fixture)
        _write_exclusive(args.output, canonical_bytes(result) + b"\n")
    except (ValidationError, ValueError, OSError) as exc:
        print(f"hyperagent-transcript: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
