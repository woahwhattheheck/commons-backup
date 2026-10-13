#!/usr/bin/env python3
"""Descriptor-relative, generation-fenced input and output custody."""
from __future__ import annotations

import os
from pathlib import Path
import stat
from typing import Any

from workshare_contract import ContractError, MAX_INPUT_BYTES, loads_strict


def _stat_fingerprint(st: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        stat.S_IFMT(st.st_mode),
        st.st_dev,
        st.st_ino,
        st.st_size,
        getattr(st, "st_mtime_ns", int(st.st_mtime * 1_000_000_000)),
        getattr(st, "st_ctime_ns", int(st.st_ctime * 1_000_000_000)),
    )


def _identity(st: os.stat_result) -> tuple[int, int, int]:
    return (stat.S_IFMT(st.st_mode), st.st_dev, st.st_ino)


def _read_all(fd: int, *, max_bytes: int, path: Path) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = os.read(fd, min(65_536, max_bytes + 1 - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > max_bytes:
            raise ContractError(f"input grew beyond {max_bytes} bytes: {path}")
    return b"".join(chunks)


def _read_bounded_regular(path: Path, *, max_bytes: int = MAX_INPUT_BYTES) -> bytes:
    if not hasattr(os, "O_NOFOLLOW"):
        raise ContractError("safe no-follow input reads are unavailable")
    flags = os.O_RDONLY | os.O_NOFOLLOW
    flags |= getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(os.fspath(path), flags)
    except OSError as exc:
        raise ContractError(f"cannot open input safely: {path}: {exc.strerror}") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise ContractError(f"input must be regular file: {path}")
        if before.st_size < 0 or before.st_size > max_bytes:
            raise ContractError(f"input exceeds {max_bytes} bytes: {path}")
        fingerprint = _stat_fingerprint(before)
        data = _read_all(fd, max_bytes=max_bytes, path=path)
        after = os.fstat(fd)
        if _stat_fingerprint(after) != fingerprint:
            raise ContractError(f"input generation changed during read: {path}")
        if len(data) != before.st_size:
            raise ContractError(f"input byte count changed during read: {path}")
        try:
            visible = os.stat(os.fspath(path), follow_symlinks=False)
        except OSError as exc:
            raise ContractError(f"input pathname disappeared during read: {path}: {exc.strerror}") from exc
        if not stat.S_ISREG(visible.st_mode) or _identity(visible) != _identity(before):
            raise ContractError(f"input generation changed during read: {path}")
        os.lseek(fd, 0, os.SEEK_SET)
        replay = _read_all(fd, max_bytes=max_bytes, path=path)
        replay_stat = os.fstat(fd)
        if replay != data or _stat_fingerprint(replay_stat) != fingerprint:
            raise ContractError(f"input generation changed during read: {path}")
        return data
    finally:
        os.close(fd)


def _load_file(path: Path) -> Any:
    data = _read_bounded_regular(path)
    if data.startswith(b"\xef\xbb\xbf"):
        raise ContractError(f"UTF-8 BOM is not allowed: {path}")
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ContractError(f"input is not strict UTF-8: {path}") from exc
    return loads_strict(text)
