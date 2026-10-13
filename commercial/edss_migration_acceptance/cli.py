"""CLI for EDSS migration/interoperability acceptance evidence."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import stat
import sys

from .acceptance import DEFAULT_POLICY, EdssAcceptanceError, canonical_json_bytes, compile_acceptance, load_json_strict, render_markdown, verify_receipt

MAX_INPUT_BYTES = 8_000_000


def _read_regular(path: Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise EdssAcceptanceError(f"input is not a regular file: {path}")
        if st.st_size > MAX_INPUT_BYTES:
            raise EdssAcceptanceError(f"input exceeds {MAX_INPUT_BYTES} bytes: {path}")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(fd, min(65536, MAX_INPUT_BYTES + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > MAX_INPUT_BYTES:
                raise EdssAcceptanceError(f"input exceeds {MAX_INPUT_BYTES} bytes: {path}")
        return b"".join(chunks)
    finally:
        os.close(fd)


def _write_exclusive(path: Path, data: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise EdssAcceptanceError(f"output is not a regular file: {path}")
        offset = 0
        while offset < len(data):
            offset += os.write(fd, data[offset:])
        os.fsync(fd)
    finally:
        os.close(fd)


def _load(path: Path):
    return load_json_strict(_read_regular(path))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Compile or verify EDSS acceptance evidence")
    sub = root.add_subparsers(dest="command", required=True)
    compile_p = sub.add_parser("compile")
    compile_p.add_argument("--input", type=Path, required=True)
    compile_p.add_argument("--policy", type=Path)
    compile_p.add_argument("--json-out", type=Path, required=True)
    compile_p.add_argument("--md-out", type=Path, required=True)
    verify_p = sub.add_parser("verify")
    verify_p.add_argument("--input", type=Path, required=True)
    verify_p.add_argument("--receipt", type=Path, required=True)
    verify_p.add_argument("--policy", type=Path)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        packet = _load(args.input)
        policy = DEFAULT_POLICY if args.policy is None else _load(args.policy)
        if args.command == "compile":
            receipt = compile_acceptance(packet, as_of=datetime.now(timezone.utc), policy=policy)
            _write_exclusive(args.json_out, canonical_json_bytes(receipt) + b"\n")
            _write_exclusive(args.md_out, render_markdown(receipt).encode("utf-8"))
            print(receipt["state"])
            return 0
        receipt = _load(args.receipt)
        verify_receipt(packet, receipt, policy=policy)
        print("VERIFIED")
        return 0
    except (EdssAcceptanceError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
