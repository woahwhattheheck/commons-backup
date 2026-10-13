"""Public compile/verify facade and CLI for RFP clarification-question packets."""
from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any, Sequence

from ._core import BOUNDARY, INPUT, MAX_BYTES, PACKET, Error, Output, _authority, _clock, _timestamp, canon, digest, load
from ._engine import _compile_at


def compile_current(raw: bytes) -> Output:
    """Compile against the process clock. No caller-supplied current time is accepted."""
    return _compile_at(raw, _clock())


def verify(raw: bytes, packet_bytes: bytes, markdown_bytes: bytes, receipt_bytes: bytes) -> dict[str, Any]:
    packet = load(packet_bytes, "packet")
    if packet.get("schema") != PACKET:
        raise Error("packet schema mismatch")
    eval_dt = _timestamp(packet.get("evaluated_at"), "packet.evaluated_at")
    expected = _compile_at(raw, eval_dt)
    if packet_bytes != expected.packet:
        raise Error("packet mismatch")
    if markdown_bytes != expected.markdown:
        raise Error("markdown mismatch")
    if receipt_bytes != expected.receipt:
        raise Error("receipt mismatch")
    current = _compile_at(raw, _clock())
    return {
        "verified": True,
        "recorded_status": expected.status,
        "current_status": current.status,
        "packet_sha256": digest(expected.packet),
        "authority": _authority(),
    }


def _open_regular(path: str, *, write: bool = False, exclusive: bool = False):
    flags = os.O_WRONLY | os.O_CREAT if write else os.O_RDONLY
    if write and exclusive:
        flags |= os.O_EXCL
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_NONBLOCK", 0)
    flags |= getattr(os, "O_BINARY", 0)
    fd = os.open(path, flags, 0o600 if write else 0)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise Error(f"{path}: regular file required")
        if hasattr(os, "O_NONBLOCK"):
            import fcntl

            current = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, current & ~os.O_NONBLOCK)
        return fd
    except Exception:
        os.close(fd)
        raise


def read_bytes(path: str) -> bytes:
    fd = _open_regular(path)
    try:
        chunks = []
        total = 0
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_BYTES:
                raise Error(f"{path}: exceeds size bound")
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(fd)


def write_exclusive(path: str, raw: bytes) -> None:
    fd = _open_regular(path, write=True, exclusive=True)
    try:
        view = memoryview(raw)
        while view:
            wrote = os.write(fd, view)
            if wrote <= 0:
                raise Error("short write")
            view = view[wrote:]
        os.fsync(fd)
    finally:
        os.close(fd)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile/verify source-bound RFP clarification question drafts")
    sub = parser.add_subparsers(dest="command", required=True)
    compile_cmd = sub.add_parser("compile")
    compile_cmd.add_argument("--input", required=True)
    compile_cmd.add_argument("--out-dir", required=True)
    verify_cmd = sub.add_parser("verify")
    verify_cmd.add_argument("--input", required=True)
    verify_cmd.add_argument("--packet", required=True)
    verify_cmd.add_argument("--markdown", required=True)
    verify_cmd.add_argument("--receipt", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "compile":
            result = compile_current(read_bytes(args.input))
            out = Path(args.out_dir)
            out.mkdir(parents=True, exist_ok=True)
            write_exclusive(str(out / "packet.json"), result.packet)
            write_exclusive(str(out / "questions.md"), result.markdown)
            write_exclusive(str(out / "receipt.json"), result.receipt)
            print(json.dumps({"status": result.status, "packet_sha256": digest(result.packet)}, sort_keys=True))
        else:
            result = verify(
                read_bytes(args.input),
                read_bytes(args.packet),
                read_bytes(args.markdown),
                read_bytes(args.receipt),
            )
            print(json.dumps(result, sort_keys=True))
        return 0
    except (Error, OSError, ValueError, TypeError, UnicodeError) as exc:
        print(f"RFP_CLARIFICATION_HOLD: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
