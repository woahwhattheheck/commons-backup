from __future__ import annotations

import argparse
import os
import stat
import sys
from pathlib import Path

from .engine import InputError, canonical_bytes, compile_report, loads_strict, render_markdown, verify_report

MAX_FILE_BYTES = 10 * 1024 * 1024


def _read_regular(path: Path) -> bytes:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise InputError(f"cannot open input {path}: {exc}") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise InputError(f"input is not a regular file: {path}")
        if before.st_size > MAX_FILE_BYTES:
            raise InputError(f"input exceeds {MAX_FILE_BYTES} bytes: {path}")
        data = bytearray()
        while True:
            chunk = os.read(fd, min(1 << 20, MAX_FILE_BYTES + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
            if len(data) > MAX_FILE_BYTES:
                raise InputError(f"input exceeds {MAX_FILE_BYTES} bytes: {path}")
        after = os.fstat(fd)
        fingerprint_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
        fingerprint_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
        if fingerprint_before != fingerprint_after or after.st_size != len(data):
            raise InputError(f"input changed while read: {path}")
        return bytes(data)
    finally:
        os.close(fd)


def _write_new(path: Path, data: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags, 0o644)
    except OSError as exc:
        raise InputError(f"cannot create output {path}: {exc}") from exc
    try:
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)


def _json_file(path: Path):
    raw = _read_regular(path)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InputError(f"input is not UTF-8: {path}") from exc
    return loads_strict(text)


def cmd_compile(args: argparse.Namespace) -> int:
    packet = _json_file(Path(args.input))
    report = compile_report(packet)
    report_path = Path(args.report)
    markdown_path = Path(args.markdown)
    if report_path == markdown_path:
        raise InputError("report and markdown outputs must differ")
    if report_path.exists() or markdown_path.exists():
        raise InputError("output path already exists")
    _write_new(report_path, canonical_bytes(report) + b"\n")
    _write_new(markdown_path, render_markdown(report).encode("utf-8"))
    print(report["receipt_sha256"])
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    packet = _json_file(Path(args.input))
    report = _json_file(Path(args.report))
    if not verify_report(packet, report):
        print("verification failed", file=sys.stderr)
        return 3
    print(f"OK {report['receipt_sha256']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Offline Accounts Receivable Leakage Desk")
    sub = parser.add_subparsers(dest="command", required=True)
    compile_p = sub.add_parser("compile")
    compile_p.add_argument("--input", required=True)
    compile_p.add_argument("--report", required=True)
    compile_p.add_argument("--markdown", required=True)
    compile_p.set_defaults(func=cmd_compile)
    verify_p = sub.add_parser("verify")
    verify_p.add_argument("--input", required=True)
    verify_p.add_argument("--report", required=True)
    verify_p.set_defaults(func=cmd_verify)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        return args.func(args)
    except InputError as exc:
        print(f"HOLD: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
