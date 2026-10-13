#!/usr/bin/env python3
"""Export one local file through bounded, explicitly requested base64 records."""
from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import select
import stat
import sys
import time
from typing import Any

SCHEMA = "commons.file_chunk_export/v1"
DEFAULT_CHUNK_BYTES = 450_000
MAX_CHUNK_BYTES = 524_286  # Divisible by three, below a 1 MiB JSON response.
MAX_EVENT_BYTES = 900_000
READ_BYTES = 131_072
DEFAULT_MAX_BYTES = 32 * 1024 * 1024


class ExportError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _fingerprint(fd: int) -> tuple[int, ...]:
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode):
        raise ExportError("NOT_REGULAR_FILE", "The opened input is not a regular file")
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _unchanged(fd: int, fingerprint: tuple[int, ...]) -> None:
    if _fingerprint(fd) != fingerprint:
        raise ExportError("SOURCE_CHANGED", "The retained input changed during export")


def _hashers(size: int):
    return hashlib.sha256(), hashlib.sha1(b"blob " + str(size).encode("ascii") + b"\0")


def _initial_hashes(fd: int, fingerprint: tuple[int, ...]) -> tuple[str, str]:
    size = fingerprint[2]
    sha, git = _hashers(size)
    total = 0
    while total <= size:
        chunk = os.read(fd, min(READ_BYTES, size + 1 - total))
        if not chunk:
            break
        total += len(chunk)
        sha.update(chunk)
        git.update(chunk)
    _unchanged(fd, fingerprint)
    if total != size:
        raise ExportError("SOURCE_CHANGED", "The initial read does not match the opened size")
    os.lseek(fd, 0, os.SEEK_SET)
    return sha.hexdigest(), git.hexdigest()


def _emit(record: dict[str, Any]) -> None:
    text = json.dumps({"schema": SCHEMA, **record}, sort_keys=True, separators=(",", ":")) + "\n"
    if len(text.encode("utf-8")) > MAX_EVENT_BYTES:
        raise ExportError("EVENT_TOO_LARGE", "The encoded record exceeds the response budget")
    sys.stdout.write(text)
    sys.stdout.flush()


@contextmanager
def _quiet_terminal():
    saved = None
    terminal = None
    if sys.stdin.isatty():
        import termios
        terminal = termios
        saved = terminal.tcgetattr(sys.stdin.fileno())
        changed = list(saved)
        changed[3] &= ~terminal.ECHO
        terminal.tcsetattr(sys.stdin.fileno(), terminal.TCSANOW, changed)
    try:
        yield
    finally:
        if terminal is not None and saved is not None:
            try:
                terminal.tcsetattr(sys.stdin.fileno(), terminal.TCSANOW, saved)
            except OSError:
                pass


def _next(offset: int, wait_seconds: float) -> None:
    deadline = time.monotonic() + wait_seconds
    line = bytearray()
    while len(line) < 128:
        remaining = deadline - time.monotonic()
        if remaining <= 0 or not select.select([sys.stdin], [], [], remaining)[0]:
            raise ExportError("NEXT_TIMEOUT", "No NEXT request arrived before the declared timeout")
        chunk = os.read(sys.stdin.fileno(), 1)
        if not chunk:
            break
        line.extend(chunk)
        if chunk == b"\n":
            break
    if not line:
        raise ExportError("INCOMPLETE_EXPORT", "Input closed before all chunks were requested")
    command = line.decode(sys.stdin.encoding or "utf-8", errors=sys.stdin.errors or "strict").strip()
    if command not in ("NEXT", "NEXT " + str(offset)):
        raise ExportError("INVALID_NEXT", "Expected NEXT or NEXT " + str(offset))


def export_file(path: Path, *, chunk_bytes: int = DEFAULT_CHUNK_BYTES,
                max_bytes: int = DEFAULT_MAX_BYTES, wait_seconds: float = 45,
                expect_sha256: str | None = None,
                expect_git_blob: str | None = None) -> dict[str, Any]:
    """Emit a manifest, requested chunks and completion using one retained fd."""
    if type(chunk_bytes) is not int or not 3 <= chunk_bytes <= MAX_CHUNK_BYTES or chunk_bytes % 3:
        raise ExportError("INVALID_CHUNK_BYTES", "chunk_bytes must be a multiple of 3 in 3..524286")
    if type(max_bytes) is not int or max_bytes < 0:
        raise ExportError("INVALID_MAX_BYTES", "max_bytes must be a nonnegative integer")
    if type(wait_seconds) not in (int, float) or not 0 < wait_seconds <= 60:
        raise ExportError("INVALID_WAIT", "wait_seconds must be greater than 0 and at most 60")
    for label, value, length in (("SHA-256", expect_sha256, 64), ("Git blob", expect_git_blob, 40)):
        if value is not None and (type(value) is not str or re.fullmatch("[0-9a-f]{" + str(length) + "}", value) is None):
            raise ExportError("INVALID_DIGEST", label + " must be a lowercase hexadecimal digest")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(os.fspath(path), flags)
    try:
        fingerprint = _fingerprint(fd)
        size = fingerprint[2]
        if size > max_bytes:
            raise ExportError("FILE_TOO_LARGE", "Input has " + str(size) + " bytes; max_bytes is " + str(max_bytes))
        source_sha, source_git = _initial_hashes(fd, fingerprint)
        if expect_sha256 is not None and source_sha != expect_sha256:
            raise ExportError("SHA256_MISMATCH", "Input does not match the expected SHA-256")
        if expect_git_blob is not None and source_git != expect_git_blob:
            raise ExportError("GIT_BLOB_MISMATCH", "Input does not match the expected Git blob")
        parts = (size + chunk_bytes - 1) // chunk_bytes
        identity = {"file": os.fspath(path), "file_bytes": size,
                    "sha256": source_sha, "git_blob_sha1": source_git}
        _emit({"kind": "manifest", **identity, "chunk_bytes": chunk_bytes,
               "part_count": parts, "max_bytes": max_bytes, "wait_seconds": wait_seconds,
               "next_offset": 0 if parts else None})
        sha, git = _hashers(size)
        offset = 0
        for index in range(parts):
            _next(offset, wait_seconds)
            _unchanged(fd, fingerprint)
            wanted = min(chunk_bytes, size - offset)
            data = bytearray()
            while len(data) < wanted:
                chunk = os.read(fd, wanted - len(data))
                if not chunk:
                    raise ExportError("SOURCE_CHANGED", "Input ended before the requested chunk")
                data.extend(chunk)
            _unchanged(fd, fingerprint)
            sha.update(data)
            git.update(data)
            end = offset + len(data)
            if end == size and (sha.hexdigest(), git.hexdigest()) != (source_sha, source_git):
                raise ExportError("SOURCE_CHANGED", "Transferred bytes differ from the initial file identity")
            _emit({"kind": "source-part", **identity, "part_index": index,
                   "part_count": parts, "start": offset, "end": end,
                   "chunk_sha256": hashlib.sha256(data).hexdigest(),
                   "next_offset": end if end < size else None,
                   "base64": base64.b64encode(data).decode("ascii")})
            offset = end
        _unchanged(fd, fingerprint)
        if offset != size or (sha.hexdigest(), git.hexdigest()) != (source_sha, source_git):
            raise ExportError("SOURCE_CHANGED", "The complete transfer does not match the file identity")
        result = {"kind": "complete", **identity, "parts": parts, "transferred_bytes": offset}
        _emit(result)
        return result
    finally:
        os.close(fd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path, help="existing local regular file; symlinks to regular files are supported")
    parser.add_argument("--chunk-bytes", type=int, default=DEFAULT_CHUNK_BYTES,
                        help="raw bytes per response, multiple of 3 (default: 450000; maximum: 524286)")
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES,
                        help="explicit full-file budget (default: 33554432)")
    parser.add_argument("--wait-seconds", type=float, default=45,
                        help="maximum wait for each NEXT, at most 60 seconds (default: 45)")
    parser.add_argument("--expect-sha256", help="optional exact lowercase SHA-256 of the source")
    parser.add_argument("--expect-git-blob", help="optional exact lowercase Git SHA-1 blob identity")
    args = parser.parse_args(argv)
    try:
        with _quiet_terminal():
            export_file(args.file, chunk_bytes=args.chunk_bytes, max_bytes=args.max_bytes,
                        wait_seconds=args.wait_seconds, expect_sha256=args.expect_sha256,
                        expect_git_blob=args.expect_git_blob)
        return 0
    except (ExportError, OSError, ValueError, KeyboardInterrupt) as exc:
        code = exc.code if isinstance(exc, ExportError) else "INTERRUPTED" if isinstance(exc, KeyboardInterrupt) else "IO_ERROR"
        error = {"schema": SCHEMA, "kind": "error", "code": code, "message": str(exc)}
        print(json.dumps(error, sort_keys=True), file=sys.stderr, flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
