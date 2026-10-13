from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path

from .compiler import (
    ValidationError,
    compile_packet,
    loads_strict,
    render_markdown,
)

MAX_PACKET_BYTES = 2_000_000
MAX_BUNDLE_FILE_BYTES = 24_000_000


def _stat_fingerprint(st: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        st.st_dev,
        st.st_ino,
        st.st_size,
        st.st_mtime_ns,
        st.st_ctime_ns,
    )


def _read_fd_bounded(fd: int, limit: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = os.read(fd, min(131_072, limit + 1 - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > limit:
            raise SystemExit(f"input exceeds {limit} byte limit")
    return b"".join(chunks)


def _read_retained(path: Path, *, limit: int = MAX_PACKET_BYTES) -> str:
    """Read one retained, no-follow regular-file generation."""
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        raise SystemExit("safe no-follow input acquisition is unavailable")
    flags = os.O_RDONLY | nofollow | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise SystemExit(f"cannot safely open input {path}: {exc}") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            raise SystemExit(f"input must be a regular file <= {limit} bytes")
        first = _read_fd_bounded(fd, limit)
        after_first = os.fstat(fd)
        if (
            _stat_fingerprint(before) != _stat_fingerprint(after_first)
            or len(first) != after_first.st_size
        ):
            raise SystemExit("input generation changed during retained read")
        os.lseek(fd, 0, os.SEEK_SET)
        second = _read_fd_bounded(fd, limit)
        after_second = os.fstat(fd)
        if (
            _stat_fingerprint(after_first) != _stat_fingerprint(after_second)
            or first != second
        ):
            raise SystemExit("input bytes changed during retained read")
        try:
            return first.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SystemExit(f"input is not strict UTF-8: {path}") from exc
    finally:
        os.close(fd)


def _write_new(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
        0o600,
    )
    data = text.encode("utf-8")
    try:
        offset = 0
        while offset < len(data):
            written = os.write(fd, data[offset:])
            if written <= 0:
                raise OSError("short output write")
            offset += written
        os.fsync(fd)
    finally:
        os.close(fd)


def _run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compile NUMIH packet readiness from a packet plus retained-byte bundle."
    )
    parser.add_argument("input", type=Path, help="strict packet JSON")
    parser.add_argument(
        "--evidence-bundle",
        type=Path,
        required=True,
        help="separate exact-byte evidence bundle JSON",
    )
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--markdown-out", type=Path)
    args = parser.parse_args(argv)

    packet = loads_strict(_read_retained(args.input, limit=MAX_PACKET_BYTES))
    bundle = loads_strict(
        _read_retained(args.evidence_bundle, limit=MAX_BUNDLE_FILE_BYTES)
    )
    result = compile_packet(packet, bundle)
    json_text = json.dumps(
        result,
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"
    if args.json_out:
        _write_new(args.json_out, json_text)
    else:
        print(json_text, end="")
    if args.markdown_out:
        _write_new(
            args.markdown_out,
            render_markdown(packet, result, bundle) + "\n",
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        return _run(argv)
    except SystemExit:
        # argparse and retained-file capability/size guards are already
        # deterministic, traceback-free command-line failures.
        raise
    except (
        ValidationError,
        OSError,
        UnicodeError,
        ValueError,
        TypeError,
        RecursionError,
    ) as exc:
        print(f"numih error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
