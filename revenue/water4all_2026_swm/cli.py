"""Command-line interface for the Water4All 2026 readiness compiler."""

from __future__ import annotations

import argparse
import errno
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any, Optional, Sequence

try:
    from .common import ReadinessError, canonical_bytes, strict_json_loads
    from .engine import (
        compile_current,
        compile_historical,
        render_owner_markdown,
        verify_bundle,
    )
except ImportError:  # pragma: no cover - direct script execution fallback
    from common import ReadinessError, canonical_bytes, strict_json_loads  # type: ignore
    from engine import (  # type: ignore
        compile_current,
        compile_historical,
        render_owner_markdown,
        verify_bundle,
    )

_MAX_BYTES = 2 * 1024 * 1024


def _read_regular_nofollow(path_text: str) -> bytes:
    path = Path(path_text)
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(str(path), flags)
    except OSError as exc:
        if exc.errno in (errno.ELOOP, errno.EMLINK):
            raise ReadinessError("input path must not be a symlink") from exc
        raise ReadinessError("cannot open input: %s" % exc) from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise ReadinessError("input must be a regular file")
        if before.st_size > _MAX_BYTES:
            raise ReadinessError("input exceeds size ceiling")
        chunks = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                raise ReadinessError("input ended before retained size")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(fd, 1):
            raise ReadinessError("input grew during retained read")
        after = os.fstat(fd)
        before_identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
        after_identity = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
        if before_identity != after_identity:
            raise ReadinessError("input generation changed during retained read")
        return b"".join(chunks)
    finally:
        os.close(fd)


def _load_json_file(path_text: str) -> Any:
    raw = _read_regular_nofollow(path_text)
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ReadinessError("input is not UTF-8") from exc
    return strict_json_loads(text)


def _write_exclusive(path_text: str, payload: bytes) -> None:
    if len(payload) > _MAX_BYTES:
        raise ReadinessError("output exceeds size ceiling")
    path = Path(path_text)
    parent = path.parent
    if not parent.exists() or not parent.is_dir():
        raise ReadinessError("output parent directory does not exist")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(str(path), flags, 0o600)
    except FileExistsError as exc:
        raise ReadinessError("output already exists") from exc
    except OSError as exc:
        raise ReadinessError("cannot create output: %s" % exc) from exc
    completed = False
    try:
        offset = 0
        while offset < len(payload):
            written = os.write(fd, payload[offset:])
            if written <= 0:
                raise ReadinessError("short output write")
            offset += written
        os.fsync(fd)
        final = os.fstat(fd)
        if not stat.S_ISREG(final.st_mode) or final.st_size != len(payload):
            raise ReadinessError("retained output generation does not match authored bytes")
        completed = True
    finally:
        os.close(fd)
        if not completed:
            try:
                os.unlink(str(path))
            except OSError:
                pass
    try:
        dir_flags = os.O_RDONLY
        if hasattr(os, "O_DIRECTORY"):
            dir_flags |= os.O_DIRECTORY
        dir_fd = os.open(str(parent), dir_flags)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except OSError:
        pass


def _json_output(value: Any) -> bytes:
    return canonical_bytes(value) + b"\n"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="water4all-readiness")
    sub = parser.add_subparsers(dest="command", required=True)

    current = sub.add_parser("compile-current", help="compile using process-owned UTC")
    current.add_argument("input")
    current.add_argument("output")
    current.add_argument("--markdown-output")

    historical = sub.add_parser("compile-historical", help="compile at an explicit historical instant")
    historical.add_argument("input")
    historical.add_argument("evaluated_at")
    historical.add_argument("output")
    historical.add_argument("--markdown-output")

    verify = sub.add_parser("verify", help="verify retained integrity and current semantics when applicable")
    verify.add_argument("input")
    verify.add_argument("bundle")
    verify.add_argument("--result-output")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "compile-current":
            input_value = _load_json_file(args.input)
            bundle = compile_current(input_value, input_value)
            _write_exclusive(args.output, _json_output(bundle))
            if args.markdown_output:
                _write_exclusive(args.markdown_output, render_owner_markdown(bundle).encode("utf-8"))
            print(bundle["packet"]["decision"]["status"])
            return 0
        if args.command == "compile-historical":
            input_value = _load_json_file(args.input)
            bundle = compile_historical(input_value, args.evaluated_at)
            _write_exclusive(args.output, _json_output(bundle))
            if args.markdown_output:
                _write_exclusive(args.markdown_output, render_owner_markdown(bundle).encode("utf-8"))
            print(bundle["packet"]["decision"]["status"])
            return 0
        if args.command == "verify":
            input_value = _load_json_file(args.input)
            bundle = _load_json_file(args.bundle)
            result = verify_bundle(input_value, bundle, input_value)
            if args.result_output:
                _write_exclusive(args.result_output, _json_output(result))
            print(json.dumps(result, sort_keys=True, separators=(",", ":")))
            return 0
        raise ReadinessError("unknown command")
    except ReadinessError as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
