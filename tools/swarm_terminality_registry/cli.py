#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import stat
import sys
import tempfile
from pathlib import Path

from .core import RegistryError, compile_snapshot, load_strict_json, verify_bundle

MAX_INPUT = 2_000_000


def _read_regular(path: Path) -> str:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise RegistryError(f"not a regular file: {path}")
        data = os.read(fd, MAX_INPUT + 1)
        if len(data) > MAX_INPUT:
            raise RegistryError(f"input too large: {path}")
        return data.decode("utf-8", "strict")
    finally:
        os.close(fd)


def _write_exclusive(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    with tempfile.TemporaryDirectory(prefix=".terminality-", dir=path.parent) as directory:
        staged = Path(directory) / "output"
        fd = os.open(staged, flags, 0o600)
        try:
            data = text.encode("utf-8")
            offset = 0
            while offset < len(data):
                written = os.write(fd, data[offset:])
                if written == 0:
                    raise OSError("report output write did not advance")
                offset += written
            os.fsync(fd)
        finally:
            os.close(fd)
        # The sibling staging directory keeps publication on one filesystem.
        # link creates the final name exclusively, including for symlink targets.
        os.link(staged, path)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Compile/verify a retained swarm work terminality snapshot")
    sub = parser.add_subparsers(dest="command", required=True)
    c = sub.add_parser("compile")
    c.add_argument("input")
    c.add_argument("output_prefix")
    v = sub.add_parser("verify")
    v.add_argument("input")
    v.add_argument("report_json")
    v.add_argument("report_markdown")
    v.add_argument("receipt_json")
    args = parser.parse_args(argv)
    try:
        candidate = load_strict_json(_read_regular(Path(args.input)))
        if args.command == "compile":
            bundle = compile_snapshot(candidate)
            prefix = Path(args.output_prefix)
            _write_exclusive(prefix.with_suffix(".report.json"), bundle.report_json)
            _write_exclusive(prefix.with_suffix(".report.md"), bundle.report_markdown)
            _write_exclusive(prefix.with_suffix(".receipt.json"), bundle.receipt_json)
            print("COMPILED")
        else:
            verify_bundle(
                candidate,
                _read_regular(Path(args.report_json)),
                _read_regular(Path(args.report_markdown)),
                _read_regular(Path(args.receipt_json)),
            )
            print("VALID")
        return 0
    except (OSError, UnicodeError, RegistryError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
