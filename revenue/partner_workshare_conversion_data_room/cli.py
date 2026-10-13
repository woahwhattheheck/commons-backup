#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
import stat
from pathlib import Path

from .engine import PacketError, compile_packet, load_strict_json, verify_bundle

MAX_INPUT = 2_000_000


def _read_regular(path: Path) -> str:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise PacketError(f"not a regular file: {path}")
        data = os.read(fd, MAX_INPUT + 1)
        if len(data) > MAX_INPUT:
            raise PacketError(f"input too large: {path}")
        extra = os.read(fd, 1)
        if extra:
            raise PacketError(f"input too large: {path}")
        return data.decode("utf-8", "strict")
    finally:
        os.close(fd)


def _create_exclusive(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        data = text.encode("utf-8")
        offset = 0
        while offset < len(data):
            offset += os.write(fd, data[offset:])
        os.fsync(fd)
    finally:
        os.close(fd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Partner workshare conversion data room")
    sub = parser.add_subparsers(dest="command", required=True)
    compile_p = sub.add_parser("compile")
    compile_p.add_argument("input")
    compile_p.add_argument("output_prefix")
    verify_p = sub.add_parser("verify")
    verify_p.add_argument("input")
    verify_p.add_argument("packet_json")
    verify_p.add_argument("packet_markdown")
    verify_p.add_argument("receipt_json")
    args = parser.parse_args(argv)
    try:
        candidate = load_strict_json(_read_regular(Path(args.input)))
        if args.command == "compile":
            bundle = compile_packet(candidate)
            prefix = Path(args.output_prefix)
            _create_exclusive(prefix.with_suffix(".packet.json"), bundle.packet_json)
            _create_exclusive(prefix.with_suffix(".packet.md"), bundle.packet_markdown)
            _create_exclusive(prefix.with_suffix(".receipt.json"), bundle.receipt_json)
            print(bundle.decision)
            return 0
        verify_bundle(
            candidate,
            _read_regular(Path(args.packet_json)),
            _read_regular(Path(args.packet_markdown)),
            _read_regular(Path(args.receipt_json)),
        )
        print("VALID")
        return 0
    except (OSError, UnicodeError, PacketError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
