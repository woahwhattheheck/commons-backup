"""Offline CLI for the Fort Worth AI-IVR validation evidence carrier."""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

from .core import ValidationError, VerificationError, canonical_json_bytes, compile_receipt, verify_receipt

MAX_INPUT_BYTES = 4_000_000
MAX_REPORT_BYTES = 4_000_000


class FileBoundaryError(RuntimeError):
    pass


def _object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise FileBoundaryError(f"duplicate JSON key: {key!r}")
        out[key] = value
    return out


def _reject_constant(value: str) -> None:
    raise FileBoundaryError(f"non-finite JSON constant forbidden: {value}")


def read_regular(path: str | os.PathLike[str], *, max_bytes: int) -> bytes:
    raw = os.fspath(path)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(raw, flags)
    except OSError as exc:
        raise FileBoundaryError(f"cannot open {raw!r}: {exc}") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise FileBoundaryError(f"not a regular file: {raw!r}")
        if before.st_size > max_bytes:
            raise FileBoundaryError(f"file exceeds {max_bytes} bytes: {raw!r}")
        chunks: list[bytes] = []
        remaining = max_bytes + 1
        while remaining:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        if len(payload) > max_bytes or os.read(fd, 1):
            raise FileBoundaryError(f"file exceeds bound while reading: {raw!r}")
        after = os.fstat(fd)
        sig = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_nlink, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if sig(before) != sig(after) or len(payload) != before.st_size:
            raise FileBoundaryError(f"file generation changed while reading: {raw!r}")
        visible = os.lstat(raw)
        if not stat.S_ISREG(visible.st_mode) or sig(visible) != sig(after):
            raise FileBoundaryError(f"visible path generation changed while reading: {raw!r}")
        return payload
    finally:
        os.close(fd)


def load_json(path: str | os.PathLike[str]) -> Any:
    raw = read_regular(path, max_bytes=MAX_INPUT_BYTES)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FileBoundaryError("JSON must be UTF-8") from exc
    try:
        return json.loads(text, object_pairs_hook=_object_pairs, parse_constant=_reject_constant)
    except json.JSONDecodeError as exc:
        raise FileBoundaryError(f"invalid JSON: {exc}") from exc


def write_exclusive(path: Path, payload: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as exc:
        raise FileBoundaryError(f"cannot create output {str(path)!r}: {exc}") from exc
    try:
        view = memoryview(payload)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise FileBoundaryError(f"short write: {str(path)!r}")
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)


def compile_command(args: argparse.Namespace) -> int:
    value = load_json(args.input)
    receipt, report = compile_receipt(value)
    output = Path(args.output_dir)
    output.mkdir(mode=0o700, parents=False, exist_ok=True)
    write_exclusive(output / "receipt.json", canonical_json_bytes(receipt) + b"\n")
    write_exclusive(output / "report.md", report.encode("utf-8"))
    print(json.dumps({"status": receipt["status"], "receipt_sha256": receipt["receipt_sha256"]}, sort_keys=True))
    return 0 if receipt["status"] == "EVIDENCE_READY_FOR_PRIME_REVIEW" else 3


def verify_command(args: argparse.Namespace) -> int:
    value = load_json(args.input)
    receipt = load_json(args.receipt)
    report_raw = read_regular(args.report, max_bytes=MAX_REPORT_BYTES)
    try:
        report = report_raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FileBoundaryError("report must be UTF-8") from exc
    verify_receipt(value, receipt, report)
    print(json.dumps({"verified": True, "receipt_sha256": receipt["receipt_sha256"]}, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fort-worth-ai-ivr-validation")
    sub = parser.add_subparsers(dest="command", required=True)
    comp = sub.add_parser("compile")
    comp.add_argument("input")
    comp.add_argument("--output-dir", required=True)
    comp.set_defaults(handler=compile_command)
    ver = sub.add_parser("verify")
    ver.add_argument("input")
    ver.add_argument("receipt")
    ver.add_argument("report")
    ver.set_defaults(handler=verify_command)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.handler(args))
    except (ValidationError, VerificationError, FileBoundaryError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
