"""Strict retained-descriptor JSON ingress for evaluation evidence."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any

from .gate import EvidenceError

MAX_INPUT_BYTES = 8 * 1024 * 1024
_READ_CHUNK = 64 * 1024


def _stat_fingerprint(info: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _read_once(fd: int) -> bytes:
    data = bytearray()
    while len(data) <= MAX_INPUT_BYTES:
        chunk = os.read(
            fd,
            min(_READ_CHUNK, MAX_INPUT_BYTES + 1 - len(data)),
        )
        if not chunk:
            break
        data.extend(chunk)
    if len(data) > MAX_INPUT_BYTES:
        raise EvidenceError(f"input exceeds {MAX_INPUT_BYTES} bytes")
    return bytes(data)


def _read_bytes_bounded(path: Path) -> bytes:
    """Read one stable regular-file generation through a retained descriptor.

    Two descriptor reads plus immutable metadata checks prevent a successful
    parse from spanning a same-inode rewrite. ``st_ctime_ns`` is included so a
    writer cannot hide the mutation merely by restoring mtime.
    """
    flags = os.O_RDONLY
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    if nofollow:
        flags |= nofollow

    before_path = path.lstat() if not nofollow else None
    fd = os.open(path, flags)
    try:
        first = os.fstat(fd)
        if not stat.S_ISREG(first.st_mode):
            raise EvidenceError(f"{path}: expected regular file")
        if before_path is not None and (
            before_path.st_dev,
            before_path.st_ino,
        ) != (
            first.st_dev,
            first.st_ino,
        ):
            raise EvidenceError(f"{path}: file identity changed during open")
        if first.st_size > MAX_INPUT_BYTES:
            raise EvidenceError(f"{path}: input exceeds {MAX_INPUT_BYTES} bytes")

        first_bytes = _read_once(fd)
        middle = os.fstat(fd)
        if _stat_fingerprint(first) != _stat_fingerprint(middle):
            raise EvidenceError(f"{path}: file generation changed during read")
        if len(first_bytes) != first.st_size:
            raise EvidenceError(f"{path}: file length changed during read")

        os.lseek(fd, 0, os.SEEK_SET)
        second_bytes = _read_once(fd)
        last = os.fstat(fd)
        if _stat_fingerprint(first) != _stat_fingerprint(last):
            raise EvidenceError(f"{path}: file generation changed during reread")
        if first_bytes != second_bytes:
            raise EvidenceError(f"{path}: file bytes changed during retained reread")
        if len(second_bytes) != last.st_size:
            raise EvidenceError(f"{path}: file length changed during reread")

        try:
            visible = path.lstat()
        except OSError as exc:
            raise EvidenceError(
                f"{path}: visible input disappeared after retained read"
            ) from exc
        if not stat.S_ISREG(visible.st_mode):
            raise EvidenceError(
                f"{path}: visible input is no longer a regular file"
            )
        if (visible.st_dev, visible.st_ino) != (last.st_dev, last.st_ino):
            raise EvidenceError(
                f"{path}: visible input no longer names retained generation"
            )
        return second_bytes
    finally:
        os.close(fd)


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _strict_json_loads(raw: bytes, *, source: str) -> Any:
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise EvidenceError(f"{source}: invalid UTF-8") from exc
    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"invalid constant {token}")
            ),
        )
    except EvidenceError:
        raise
    except (json.JSONDecodeError, ValueError) as exc:
        raise EvidenceError(f"{source}: invalid JSON") from exc


def _read_json(path: Path) -> Any:
    return _strict_json_loads(
        _read_bytes_bounded(path),
        source=os.fspath(path),
    )
