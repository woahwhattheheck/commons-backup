from __future__ import annotations

import argparse
import os
import stat
import sys
from pathlib import Path

from .audit import (
    MAX_CAPTURE_BYTES,
    audit_transcript,
    canonical_json_bytes,
    verify_receipt,
)

MAX_RECEIPT_BYTES = 32 * 1024 * 1024


def _open_flags() -> int:
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    # Avoid blocking forever on FIFOs/special files before S_ISREG.
    # Platforms without O_NONBLOCK keep the prior open path.
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    return flags


def _read_bounded(path: str, *, max_bytes: int, label: str) -> bytes:
    fd = os.open(path, _open_flags())
    try:
        file_stat = os.fstat(fd)
        if not stat.S_ISREG(file_stat.st_mode):
            raise ValueError(f"{label} input must be a regular file")
        if file_stat.st_size > max_bytes:
            raise ValueError(f"{label} exceeds {max_bytes} byte limit")

        data = bytearray()
        while True:
            remaining = max_bytes + 1 - len(data)
            chunk = os.read(fd, min(64 * 1024, remaining))
            if not chunk:
                break
            data.extend(chunk)
            if len(data) > max_bytes:
                raise ValueError(f"{label} exceeds {max_bytes} byte limit")
        return bytes(data)
    finally:
        os.close(fd)


def _write_exclusive(path: str, data: bytes) -> None:
    target = Path(path)
    parent = target.parent
    if not parent.exists() or not parent.is_dir():
        raise ValueError(f"output parent does not exist: {parent}")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(str(target), flags, 0o600)
    try:
        with os.fdopen(fd, "wb", closefd=True) as handle:
            handle.write(data)
            handle.write(b"\n")
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            target.unlink(missing_ok=True)
        finally:
            raise


def _emit(value: dict, output: str | None, output_format: str = "json") -> None:
    if output_format == "markdown":
        from .report import render_markdown
        payload = render_markdown(value).encode("utf-8")
    else:
        payload = canonical_json_bytes(value)
    if output:
        _write_exclusive(output, payload)
    else:
        sys.stdout.buffer.write(payload + b"\n")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mcp-transcript-audit",
        description="Offline byte-bound audit for captured MCP 2025-11-25 JSON-RPC transcripts.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    audit = sub.add_parser("audit", help="audit a capture and emit a deterministic receipt")
    audit.add_argument("capture")
    audit.add_argument("--output", "-o")

    verify = sub.add_parser("verify", help="recompute a capture and verify a saved receipt")
    verify.add_argument("capture")
    verify.add_argument("receipt")
    verify.add_argument("--output", "-o")
    for command in (audit, verify):
        command.add_argument(
            "--format", choices=("json", "markdown"), default="json",
            help="JSON receipt/result (default), or a readable Markdown view",
        )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        source = _read_bounded(args.capture, max_bytes=MAX_CAPTURE_BYTES, label="capture")
        if args.command == "audit":
            result = audit_transcript(source)
            _emit(result, args.output, args.format)
            return 0 if result["status"] == "PASS" else 3
        receipt = _read_bounded(args.receipt, max_bytes=MAX_RECEIPT_BYTES, label="receipt")
        result = verify_receipt(source, receipt)
        _emit(result, args.output, args.format)
        return 0 if result["valid"] else 3
    except (OSError, ValueError) as exc:
        print(f"mcp-transcript-audit: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
